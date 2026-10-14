import { useEffect, useState } from "react";
import { Text, TextInput, View } from "react-native";
import { HealthApiClient, type components } from "@personal-health/api-client";

import { apiBaseUrl } from "../../../auth/apiConfig";
import { mobileFetch } from "../../../auth/mobileFetch";
import { sessionStore } from "../../../auth/sessionStore";
import { newProfileId, type ProfileItem } from "../model";
import { ActionButton } from "./Ui";

const api = new HealthApiClient(apiBaseUrl, mobileFetch);
type Status = components["schemas"]["SourceTaskStatus"];

export function ShoppingTaskCard({ item }: { item: ProfileItem }) {
  const [enabled, setEnabled] = useState(false);
  const [recent, setRecent] = useState(false);
  const [choices, setChoices] = useState<{ id: string; label: string }[]>([]);
  const [choice, setChoice] = useState("");
  const [project, setProject] = useState("");
  const [revision, setRevision] = useState("");
  const [command, setCommand] = useState("");
  const [resume, setResume] = useState("");
  const [status, setStatus] = useState<Status | null>(null);
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [error, setError] = useState("");
  const [confirmation] = useState(newProfileId);
  useEffect(() => {
    let active = true;
    const owner = sessionStore.getSnapshot();
    const isCurrent = () =>
      active && sessionStore.getSnapshot().epoch === owner.epoch;
    void api
      .getShoppingTaskCapabilities()
      .then((value) => {
        if (isCurrent()) {
          setEnabled(value.enabled === true);
          setRecent(value.recent_authentication === true);
        }
      })
      .catch(() => undefined);
    const unsubscribe = sessionStore.subscribe(() => {
      if (!isCurrent()) {
        setEnabled(false);
        setStatus(null);
        setCommand("");
        setChoices([]);
      }
    });
    return () => {
      active = false;
      unsubscribe();
    };
  }, []);
  async function run(work: () => Promise<void>) {
    if (busy) return;
    const owner = sessionStore.getSnapshot();
    setBusy(true);
    setError("");
    try {
      await work();
    } catch {
      if (sessionStore.getSnapshot().epoch === owner.epoch)
        setError(
          "The request could not be confirmed. Keep the original command ID and check its result.",
        );
    } finally {
      if (sessionStore.getSnapshot().epoch === owner.epoch) setBusy(false);
    }
  }
  async function observe(id: string) {
    const value = await api.getShoppingSourceCommandStatus({ command_id: id });
    setCommand(id);
    setStatus(value);
    setUncertain(false);
  }
  if (!enabled || item.profile.key !== "ergonomic_constraints") return null;
  const shared =
    item.status === "active" &&
    item.permissions.ai_use_allowed &&
    item.permissions.cross_domain_use_allowed;
  return (
    <View style={{ gap: 12, paddingVertical: 16 }}>
      <Text accessibilityRole="header">
        Share ergonomic constraints with Shopping
      </Text>
      <Text>
        Append only this shared constraint as a project note. Review the preview
        before confirming.
      </Text>
      {!shared && (
        <Text>
          Allow AI use and use by other apps on this active Profile item first.
        </Text>
      )}
      {!recent && (
        <Text>Authenticate again to review and apply a Shopping task.</Text>
      )}
      <ActionButton
        label="Load granted sources"
        disabled={busy || !!command || !recent}
        onPress={() =>
          void run(async () => {
            const result = await api.listShoppingTaskChoices();
            const raw = result.choices;
            if (!Array.isArray(raw)) throw new Error("Invalid choices");
            setChoices(
              raw.flatMap((value) =>
                value &&
                typeof value === "object" &&
                "id" in value &&
                typeof value.id === "string" &&
                "category_label" in value &&
                typeof value.category_label === "string"
                  ? [{ id: value.id, label: value.category_label }]
                  : [],
              ),
            );
          })
        }
      />
      {choices.map((value) => (
        <ActionButton
          key={value.id}
          label={`${choice === value.id ? "Selected: " : "Select: "}${value.label}`}
          disabled={busy || !!command}
          onPress={() => setChoice(value.id)}
        />
      ))}
      <TextInput
        accessibilityLabel="Shopping project ID"
        placeholder="Shopping project ID"
        value={project}
        editable={!busy && !command}
        onChangeText={setProject}
      />
      <TextInput
        accessibilityLabel="Current project revision"
        placeholder="Current project revision"
        inputMode="numeric"
        value={revision}
        editable={!busy && !command}
        onChangeText={setRevision}
      />
      <ActionButton
        label="Prepare Shopping task"
        disabled={
          busy ||
          !!command ||
          !recent ||
          !shared ||
          !choice ||
          !project ||
          !Number.isSafeInteger(Number(revision)) ||
          Number(revision) < 1
        }
        onPress={() =>
          void run(async () => {
            const id = newProfileId();
            setCommand(id);
            setUncertain(true);
            await api.createShoppingSourceCommand({
              command_id: id,
              object_id: item.id,
              expected_source_version: `health-object-v1:r${item.revision}:schema-${item.schema_version}`,
              context_choice_id: choice,
              shopping_project_id: project,
              expected_project_revision: Number(revision),
            });
            setStatus(
              await api.submitShoppingSourceCommand({ command_id: id }),
            );
            setUncertain(false);
          })
        }
      />
      {command && <Text selectable>Recovery command ID: {command}</Text>}
      {status && (
        <Text accessibilityRole="text">
          {status.state}: {status.preview ?? status.outcome_code ?? ""}
        </Text>
      )}
      <ActionButton
        label="Validate and preview"
        disabled={busy || uncertain || !recent || status?.state !== "proposed"}
        onPress={() =>
          void run(async () => {
            setStatus(
              await api.controlShoppingSourceCommand(
                {
                  command_id: command,
                  action: "validate",
                },
                null,
              ),
            );
          })
        }
      />
      <ActionButton
        label="Confirm and apply this note"
        disabled={
          busy ||
          uncertain ||
          !recent ||
          !(status?.state === "validated" || status?.state === "confirmed")
        }
        onPress={() =>
          void run(async () => {
            if (!status) return;
            const body = {
              confirmation_id: status.confirmation_id ?? confirmation,
              binding: status.binding,
            };
            setUncertain(true);
            if (status.state !== "confirmed")
              await api.controlShoppingSourceCommand(
                { command_id: command, action: "confirm" },
                body,
              );
            setStatus(
              await api.controlShoppingSourceCommand(
                { command_id: command, action: "apply" },
                body,
              ),
            );
            setUncertain(false);
          })
        }
      />
      <ActionButton
        label="Check original result"
        disabled={busy || !command || !recent}
        onPress={() => void run(() => observe(command))}
      />
      <ActionButton
        label="Reconcile original task"
        disabled={busy || !command || !recent}
        onPress={() =>
          void run(async () => {
            setStatus(
              await api.controlShoppingSourceCommand(
                {
                  command_id: command,
                  action: "reconcile",
                },
                null,
              ),
            );
            setUncertain(false);
          })
        }
      />
      <ActionButton
        label="Recover original submission"
        disabled={busy || !command || !!status || !uncertain || !recent}
        onPress={() =>
          void run(async () => {
            setStatus(
              await api.submitShoppingSourceCommand({ command_id: command }),
            );
            setUncertain(false);
          })
        }
      />
      <TextInput
        accessibilityLabel="Resume command ID"
        placeholder="Resume command ID"
        value={resume}
        editable={!busy && !command}
        onChangeText={setResume}
      />
      <ActionButton
        label="Resume original task"
        disabled={
          busy || !!command || !recent || !/^[0-9a-f-]{36}$/i.test(resume)
        }
        onPress={() => void run(() => observe(resume))}
      />
      {uncertain && (
        <Text accessibilityRole="alert">
          An acknowledgement is missing. Check this command before creating
          another task.
        </Text>
      )}
      {error && <Text accessibilityRole="alert">{error}</Text>}
    </View>
  );
}
