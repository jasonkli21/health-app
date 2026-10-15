import { useEffect, useRef, useState } from "react";
import { Text, View } from "react-native";
import * as SecureStore from "expo-secure-store";
import { HealthApiClient, type components } from "@personal-health/api-client";

import { apiBaseUrl } from "../../../auth/apiConfig";
import { mobileFetch } from "../../../auth/mobileFetch";
import { sessionStore } from "../../../auth/sessionStore";
import { newProfileId, type ProfileItem } from "../model";
import {
  clearShoppingTaskRecord,
  loadShoppingTaskRecord,
  phaseAfterTaskFailure,
  phaseForTaskStatus,
  saveShoppingTaskRecord,
  type ShoppingTaskPhase,
  type ShoppingTaskRecord,
} from "../shoppingTaskRecovery";
import { ActionButton } from "./Ui";
import { ShoppingProjectPicker } from "./ShoppingProjectPicker";

const api = new HealthApiClient(apiBaseUrl, mobileFetch);
type Status = components["schemas"]["SourceTaskStatus"];
type CreateRequest = Parameters<typeof api.createShoppingSourceCommand>[0];

export function ShoppingTaskCard({ item }: { item: ProfileItem }) {
  const [enabled, setEnabled] = useState(false);
  const [recent, setRecent] = useState(false);
  const [choices, setChoices] = useState<{ id: string; label: string }[]>([]);
  const [projects, setProjects] = useState<
    { project_id: string; label: string; revision: number }[]
  >([]);
  const [choice, setChoice] = useState("");
  const [projectId, setProjectId] = useState("");
  const [record, setRecord] = useState<ShoppingTaskRecord | null>(null);
  const [phase, setPhase] = useState<ShoppingTaskPhase>("draft");
  const [status, setStatus] = useState<Status | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const ownerId = sessionStore.getSnapshot().userId;
  const previousOwner = useRef(ownerId);

  useEffect(() => {
    let active = true;
    const restore = async (owner: string | null, epoch: number) => {
      if (!owner || sessionStore.getSnapshot().status !== "signed_in") return;
      const saved = await loadShoppingTaskRecord(SecureStore, owner).catch(
        () => null,
      );
      if (
        !active ||
        sessionStore.getSnapshot().epoch !== epoch ||
        sessionStore.getSnapshot().userId !== owner ||
        !saved
      ) {
        return;
      }
      setRecord(saved);
      setPhase(saved.phase);
      setChoice(String(saved.create_request.context_choice_id ?? ""));
      setProjectId(String(saved.create_request.shopping_project_id ?? ""));
      if (
        !["creating_command", "command_created", "submitting"].includes(
          saved.phase,
        )
      ) {
        void api
          .getShoppingSourceCommandStatus({ command_id: saved.command_id })
          .then((current) => {
            if (
              active &&
              sessionStore.getSnapshot().epoch === epoch &&
              sessionStore.getSnapshot().userId === owner
            ) {
              setStatus(current);
              const recovered = {
                ...saved,
                phase: phaseForTaskStatus(current.state),
                confirmation_id:
                  current.confirmation_id ?? saved.confirmation_id,
              };
              setPhase(recovered.phase);
              setRecord(recovered);
              void saveShoppingTaskRecord(SecureStore, recovered);
            }
          })
          .catch(() => undefined);
      }
    };
    const applySnapshot = (owner: string | null, epoch: number) => {
      if (previousOwner.current && previousOwner.current !== owner) {
        void clearShoppingTaskRecord(SecureStore);
        setRecord(null);
        setStatus(null);
        setPhase("draft");
        setChoice("");
        setProjectId("");
        setChoices([]);
        setProjects([]);
      }
      previousOwner.current = owner;
      void restore(owner, epoch);
    };
    const owner = sessionStore.getSnapshot();
    applySnapshot(owner.userId, owner.epoch);
    const unsubscribe = sessionStore.subscribe(() => {
      const current = sessionStore.getSnapshot();
      applySnapshot(current.userId, current.epoch);
      if (current.status !== "signed_in") {
        setEnabled(false);
        setStatus(null);
        setRecord(null);
        setPhase("draft");
      }
    });
    const current = sessionStore.getSnapshot();
    const isCurrent = () =>
      active && sessionStore.getSnapshot().epoch === current.epoch;
    void api
      .getShoppingTaskCapabilities()
      .then((value) => {
        if (isCurrent()) {
          setEnabled(value.enabled === true);
          setRecent(value.recent_authentication === true);
        }
      })
      .catch(() => undefined);
    return () => {
      active = false;
      unsubscribe();
    };
  }, []);

  async function run(work: (epoch: number, owner: string) => Promise<void>) {
    if (busy || !ownerId) return;
    const snapshot = sessionStore.getSnapshot();
    setBusy(true);
    setError("");
    try {
      await work(snapshot.epoch, ownerId);
    } catch {
      if (sessionStore.getSnapshot().epoch === snapshot.epoch) {
        setError(
          "The task could not be confirmed. Check the original command before starting another.",
        );
      }
    } finally {
      if (sessionStore.getSnapshot().epoch === snapshot.epoch) setBusy(false);
    }
  }

  async function persist(
    next: ShoppingTaskRecord,
    epoch: number,
  ): Promise<boolean> {
    const current = sessionStore.getSnapshot();
    if (current.epoch !== epoch || current.userId !== next.owner_id)
      return false;
    await saveShoppingTaskRecord(SecureStore, next);
    if (
      sessionStore.getSnapshot().epoch !== epoch ||
      sessionStore.getSnapshot().userId !== next.owner_id
    ) {
      await clearShoppingTaskRecord(SecureStore);
      return false;
    }
    setRecord(next);
    setPhase(next.phase);
    return true;
  }

  async function acceptStatus(
    nextStatus: Status,
    current: ShoppingTaskRecord,
    epoch: number,
  ) {
    const next = {
      ...current,
      phase: phaseForTaskStatus(nextStatus.state),
      confirmation_id: nextStatus.confirmation_id ?? current.confirmation_id,
    };
    setStatus(nextStatus);
    await persist(next, epoch);
  }

  async function submitOriginal(current: ShoppingTaskRecord, epoch: number) {
    const submitting = { ...current, phase: "submitting" as const };
    if (!(await persist(submitting, epoch))) return;
    try {
      const nextStatus = await api.submitShoppingSourceCommand({
        command_id: submitting.command_id,
      });
      await acceptStatus(nextStatus, submitting, epoch);
    } catch (cause) {
      const nextPhase = phaseAfterTaskFailure("submitting", cause);
      await persist({ ...submitting, phase: nextPhase }, epoch);
      setError(
        nextPhase === "terminal"
          ? "Personal AI rejected this source command. Correct the consent or revision, then start a new task."
          : "The source command exists, but submission was not acknowledged. Retry the original submission with the same command ID.",
      );
    }
  }

  async function createAndSubmit(epoch: number, owner: string) {
    const createRequest: CreateRequest = {
      command_id: newProfileId(),
      object_id: item.id,
      expected_source_version: `health-object-v1:r${item.revision}:schema-${item.schema_version}`,
      context_choice_id: choice,
      shopping_project_id: selectedProject!.project_id,
      expected_project_revision: selectedProject!.revision,
    };
    const created: ShoppingTaskRecord = {
      schema_version: 1,
      owner_id: owner,
      command_id: createRequest.command_id,
      create_request: createRequest,
      phase: "creating_command",
      confirmation_id: null,
    };
    if (!(await persist(created, epoch))) return;
    try {
      await api.createShoppingSourceCommand(createRequest);
    } catch (cause) {
      const nextPhase = phaseAfterTaskFailure("creating_command", cause);
      if (nextPhase === "draft") {
        await clearShoppingTaskRecord(SecureStore);
        setRecord(null);
        setPhase("draft");
        setStatus(null);
        setError(
          "Shopping rejected command creation. Review consent, source revision, and project selection before trying again.",
        );
      } else {
        await persist({ ...created, phase: nextPhase }, epoch);
        setError(
          "Command creation may have completed. Retry recovery with the same command ID.",
        );
      }
      return;
    }
    const known = { ...created, phase: "command_created" as const };
    if (await persist(known, epoch)) await submitOriginal(known, epoch);
  }

  async function recoverOriginal(epoch: number) {
    if (!record) return;
    if (record.phase === "creating_command") {
      try {
        await api.createShoppingSourceCommand(
          record.create_request as CreateRequest,
        );
        const known = { ...record, phase: "command_created" as const };
        if (await persist(known, epoch)) await submitOriginal(known, epoch);
      } catch (cause) {
        const nextPhase = phaseAfterTaskFailure("creating_command", cause);
        if (nextPhase === "draft") {
          await clearShoppingTaskRecord(SecureStore);
          setRecord(null);
          setPhase("draft");
          setError(
            "Shopping rejected command creation. Correct the request before retrying.",
          );
        } else {
          await persist({ ...record, phase: nextPhase }, epoch);
          setError(
            "Command creation is still unconfirmed. Keep the same command ID and retry later.",
          );
        }
      }
      return;
    }
    if (["command_created", "submitting"].includes(record.phase)) {
      await submitOriginal(record, epoch);
      return;
    }
    await checkOriginal(epoch);
  }

  async function validate(epoch: number) {
    if (!record) return;
    const validating = { ...record, phase: "validating" as const };
    if (!(await persist(validating, epoch))) return;
    try {
      const nextStatus = await api.controlShoppingSourceCommand(
        { command_id: record.command_id, action: "validate" },
        null,
      );
      await acceptStatus(nextStatus, validating, epoch);
    } catch (cause) {
      const nextPhase = phaseAfterTaskFailure("validating", cause);
      await persist({ ...validating, phase: nextPhase }, epoch);
      setError(
        nextPhase === "terminal"
          ? "Shopping rejected validation. Review the current source and target before starting a new task."
          : "Validation was not acknowledged. Check the original task before retrying.",
      );
    }
  }

  async function confirmAndApply(epoch: number) {
    if (!record || !status) return;
    const confirmationId =
      status.confirmation_id ?? record.confirmation_id ?? newProfileId();
    const confirmation = {
      confirmation_id: confirmationId,
      binding: status.binding,
    };
    let currentStatus = status;
    let currentRecord = record;
    if (currentStatus.state !== "confirmed") {
      const confirming = {
        ...currentRecord,
        phase: "confirming" as const,
        confirmation_id: confirmationId,
      };
      if (!(await persist(confirming, epoch))) return;
      try {
        currentStatus = await api.controlShoppingSourceCommand(
          { command_id: record.command_id, action: "confirm" },
          confirmation,
        );
        await acceptStatus(currentStatus, confirming, epoch);
        currentRecord = {
          ...confirming,
          phase: "confirmed",
          confirmation_id: currentStatus.confirmation_id ?? confirmationId,
        };
        if (!(await persist(currentRecord, epoch))) return;
      } catch (cause) {
        const nextPhase = phaseAfterTaskFailure("confirming", cause);
        await persist({ ...confirming, phase: nextPhase }, epoch);
        setError(
          nextPhase === "terminal"
            ? "Shopping rejected confirmation. Review the preview before starting a new task."
            : "Confirmation may have completed. Check the original task to recover its server-issued identity.",
        );
        return;
      }
    }
    const applying = { ...currentRecord, phase: "applying" as const };
    if (!(await persist(applying, epoch))) return;
    try {
      const applied = await api.controlShoppingSourceCommand(
        { command_id: record.command_id, action: "apply" },
        confirmation,
      );
      await acceptStatus(applied, applying, epoch);
    } catch (cause) {
      const nextPhase = phaseAfterTaskFailure("applying", cause);
      await persist({ ...applying, phase: nextPhase }, epoch);
      setError(
        nextPhase === "effect_unknown"
          ? "The destination may have applied this change. Reconcile the original execution; do not create a replacement."
          : "Shopping definitively rejected apply. Review the task and start a new one only after correcting the cause.",
      );
    }
  }

  async function checkOriginal(epoch: number) {
    if (!record) return;
    const current = await api.getShoppingSourceCommandStatus({
      command_id: record.command_id,
    });
    if (["executing", "reconciling", "uncertain"].includes(current.state)) {
      const reconciled = await api.controlShoppingSourceCommand(
        { command_id: record.command_id, action: "reconcile" },
        null,
      );
      await acceptStatus(reconciled, record, epoch);
      return;
    }
    await acceptStatus(current, record, epoch);
  }

  async function reset() {
    await clearShoppingTaskRecord(SecureStore);
    setRecord(null);
    setStatus(null);
    setPhase("draft");
    setError("");
  }

  if (!enabled || item.profile.key !== "ergonomic_constraints") return null;
  const shared =
    item.status === "active" &&
    item.permissions.ai_use_allowed &&
    item.permissions.cross_domain_use_allowed;
  const selectedProject = projects.find(
    (project) => project.project_id === projectId,
  );
  const canStart =
    !busy && !record && recent && shared && !!choice && !!selectedProject;
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
        disabled={busy || !!record || !recent}
        onPress={() =>
          void run(async () => {
            const result = await api.listShoppingTaskChoices();
            setChoices(
              result.choices.map((value) => ({
                id: value.id,
                label: value.category_label,
              })),
            );
          })
        }
      />
      <ActionButton
        label="Load Shopping projects"
        disabled={busy || !!record || !recent}
        onPress={() =>
          void run(async () => {
            const result = await api.listShoppingTaskProjects();
            setProjects(result.choices);
          })
        }
      />
      {choices.map((value) => (
        <ActionButton
          key={value.id}
          label={`${choice === value.id ? "Selected: " : "Select: "}${value.label}`}
          disabled={busy || !!record}
          onPress={() => setChoice(value.id)}
        />
      ))}
      <Text accessibilityRole="header">Shopping project</Text>
      <ShoppingProjectPicker
        choices={projects}
        selectedId={projectId}
        disabled={busy || !!record}
        onSelect={setProjectId}
      />
      <ActionButton
        label="Prepare Shopping task"
        disabled={!canStart}
        onPress={() => void run(createAndSubmit)}
      />
      {record && (
        <Text selectable>Recovery command ID: {record.command_id}</Text>
      )}
      {status && (
        <Text accessibilityRole="text">
          {status.state}: {status.preview ?? status.outcome_code ?? ""}
        </Text>
      )}
      <ActionButton
        label="Recover original command or submission"
        disabled={
          busy ||
          !record ||
          !["creating_command", "command_created", "submitting"].includes(
            phase,
          ) ||
          !recent
        }
        onPress={() => void run(recoverOriginal)}
      />
      <ActionButton
        label="Validate and preview"
        disabled={busy || !recent || phase !== "proposed" || !record}
        onPress={() => void run(validate)}
      />
      <ActionButton
        label="Confirm and apply this note"
        disabled={
          busy ||
          !recent ||
          !record ||
          !status ||
          !["validated", "confirmed"].includes(status.state) ||
          phase === "effect_unknown"
        }
        onPress={() => void run(confirmAndApply)}
      />
      <ActionButton
        label="Check or reconcile original result"
        disabled={busy || !record || !recent}
        onPress={() => void run(checkOriginal)}
      />
      {phase === "effect_unknown" && (
        <Text accessibilityRole="alert">
          The destination may have applied this change. Reconcile the original
          execution; do not create a replacement task.
        </Text>
      )}
      {record && phase === "terminal" && (
        <ActionButton
          label="Start a new task"
          secondary
          disabled={busy}
          onPress={() => void run(async () => reset())}
        />
      )}
      {error && <Text accessibilityRole="alert">{error}</Text>}
    </View>
  );
}
