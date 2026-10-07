import type { HealthApiClient } from "@personal-health/api-client";

import type { SessionSnapshot } from "../../auth/sessionStore";
import { checkpointKey } from "./checkpointKey";
import type { CheckpointStore } from "./checkpoint";
import type { HealthKitConsentStore } from "./consent";
import type {
  HealthKitBatchBody,
  HealthKitBatchResult,
  HealthKitCheckpoint,
  HealthKitResourceType,
} from "./types";

type HealthKitSyncApi = Pick<HealthApiClient, "importHealthKitBatch">;
type SessionSource = { getSnapshot(): SessionSnapshot };
type GuardedApiFactory = (guard: () => Promise<void>) => HealthKitSyncApi;

export type SyncAuthorization = {
  ownerId: string;
  deviceInstallationId: string;
  resourceType: HealthKitResourceType;
  policyVersion: "healthkit-v1";
  sessionEpoch: number;
  consentVersion: number;
  expectedAnchor: string | null;
};

export type SyncBatchInput = {
  authorization: SyncAuthorization;
  request: HealthKitBatchBody;
  nextAnchor: string | null;
  now?: () => Date;
};

export type SyncBatchResult =
  | { status: "saved"; receipt: HealthKitBatchResult }
  | {
      status: "acknowledged_checkpoint_pending";
      receipt: HealthKitBatchResult;
    };

export class HealthKitSyncAuthorizationError extends Error {
  constructor(message = "HealthKit sync authorization is no longer current.") {
    super(message);
    this.name = "HealthKitSyncAuthorizationError";
  }
}

export class HealthKitCheckpointConflictError extends Error {
  constructor() {
    super(
      "The HealthKit checkpoint changed. Prepare the sync again from its current anchor.",
    );
    this.name = "HealthKitCheckpointConflictError";
  }
}

type PendingCheckpoint = {
  checkpoint: HealthKitCheckpoint;
  key: string;
  receipt: HealthKitBatchResult;
};

const scopeTails = new Map<string, Promise<void>>();

export class HealthKitSyncCoordinator {
  private readonly pendingCheckpoints = new Map<string, PendingCheckpoint>();

  constructor(
    private readonly apiForGuard: GuardedApiFactory,
    private readonly checkpoints: CheckpointStore,
    private readonly sessions: SessionSource,
    private readonly consents: HealthKitConsentStore,
  ) {}

  async captureAuthorization(input: {
    ownerId: string;
    deviceInstallationId: string;
    resourceType: HealthKitResourceType;
    policyVersion?: "healthkit-v1";
  }): Promise<SyncAuthorization> {
    const policyVersion = input.policyVersion ?? "healthkit-v1";
    const snapshot = this.sessions.getSnapshot();
    if (snapshot.status !== "signed_in" || snapshot.userId !== input.ownerId) {
      throw new HealthKitSyncAuthorizationError(
        "Sign in to the account that granted HealthKit consent before syncing.",
      );
    }
    const consentVersion = this.consents.version(
      input.ownerId,
      input.resourceType,
    );
    if (!(await this.consents.isEnabled(input.ownerId, input.resourceType))) {
      throw new HealthKitSyncAuthorizationError(
        "HealthKit sync consent is required.",
      );
    }
    if (
      this.consents.version(input.ownerId, input.resourceType) !==
        consentVersion ||
      this.sessions.getSnapshot().epoch !== snapshot.epoch
    ) {
      throw new HealthKitSyncAuthorizationError();
    }
    const key = checkpointKey(
      input.ownerId,
      input.deviceInstallationId,
      input.resourceType,
      policyVersion,
    );
    const checkpoint = await this.checkpoints.load(key);
    if (
      checkpoint !== null &&
      (checkpoint.ownerId !== input.ownerId ||
        checkpoint.deviceInstallationId !== input.deviceInstallationId ||
        checkpoint.resourceType !== input.resourceType ||
        checkpoint.policyVersion !== policyVersion)
    ) {
      throw new HealthKitSyncAuthorizationError(
        "The saved HealthKit checkpoint scope is invalid.",
      );
    }
    await this.assertAuthorization({
      ownerId: input.ownerId,
      deviceInstallationId: input.deviceInstallationId,
      resourceType: input.resourceType,
      policyVersion,
      sessionEpoch: snapshot.epoch,
      consentVersion,
      expectedAnchor: checkpoint?.anchor ?? null,
    });
    return {
      ownerId: input.ownerId,
      deviceInstallationId: input.deviceInstallationId,
      resourceType: input.resourceType,
      policyVersion,
      sessionEpoch: snapshot.epoch,
      consentVersion,
      expectedAnchor: checkpoint?.anchor ?? null,
    };
  }

  async commitBatch(input: SyncBatchInput): Promise<SyncBatchResult> {
    const authorization = input.authorization;
    if (
      input.request.device_installation_id !==
        authorization.deviceInstallationId ||
      input.request.resource_type !== authorization.resourceType ||
      input.request.policy_version !== authorization.policyVersion
    ) {
      throw new HealthKitSyncAuthorizationError(
        "HealthKit batch does not match its authorized checkpoint scope.",
      );
    }
    const scope = checkpointKey(
      authorization.ownerId,
      authorization.deviceInstallationId,
      authorization.resourceType,
      authorization.policyVersion,
    );
    return this.withScopeLock(scope, async () => {
      const pending = this.pendingCheckpoints.get(scope);
      if (pending !== undefined) {
        try {
          await this.assertAuthorization(authorization);
          await this.checkpoints.save(pending.key, pending.checkpoint);
          this.pendingCheckpoints.delete(scope);
        } catch {
          return {
            status: "acknowledged_checkpoint_pending",
            receipt: pending.receipt,
          };
        }
        throw new HealthKitCheckpointConflictError();
      }

      await this.assertAuthorization(authorization);
      const current = await this.checkpoints.load(scope);
      if (
        current !== null &&
        (current.ownerId !== authorization.ownerId ||
          current.deviceInstallationId !== authorization.deviceInstallationId ||
          current.resourceType !== authorization.resourceType ||
          current.policyVersion !== authorization.policyVersion)
      ) {
        throw new HealthKitSyncAuthorizationError(
          "The saved HealthKit checkpoint scope is invalid.",
        );
      }
      if ((current?.anchor ?? null) !== authorization.expectedAnchor) {
        throw new HealthKitCheckpointConflictError();
      }

      const guard = () => this.assertAuthorization(authorization);
      const receipt = await this.apiForGuard(guard).importHealthKitBatch(
        input.request,
      );
      const checkpoint: HealthKitCheckpoint = {
        ownerId: authorization.ownerId,
        deviceInstallationId: authorization.deviceInstallationId,
        resourceType: authorization.resourceType,
        policyVersion: authorization.policyVersion,
        anchor: input.nextAnchor,
        savedAt: (input.now ?? (() => new Date()))().toISOString(),
      };
      try {
        await guard();
        await this.checkpoints.save(scope, checkpoint);
        return { status: "saved", receipt };
      } catch {
        this.pendingCheckpoints.set(scope, { checkpoint, key: scope, receipt });
        return { status: "acknowledged_checkpoint_pending", receipt };
      }
    });
  }

  private async assertAuthorization(
    authorization: SyncAuthorization,
  ): Promise<void> {
    const snapshot = this.sessions.getSnapshot();
    if (
      snapshot.status !== "signed_in" ||
      snapshot.userId !== authorization.ownerId ||
      snapshot.epoch !== authorization.sessionEpoch ||
      this.consents.version(
        authorization.ownerId,
        authorization.resourceType,
      ) !== authorization.consentVersion
    ) {
      throw new HealthKitSyncAuthorizationError();
    }
    if (
      !(await this.consents.isEnabled(
        authorization.ownerId,
        authorization.resourceType,
      ))
    ) {
      throw new HealthKitSyncAuthorizationError(
        "HealthKit sync consent was disabled.",
      );
    }
    const current = this.sessions.getSnapshot();
    if (
      current.status !== "signed_in" ||
      current.userId !== authorization.ownerId ||
      current.epoch !== authorization.sessionEpoch ||
      this.consents.version(
        authorization.ownerId,
        authorization.resourceType,
      ) !== authorization.consentVersion
    ) {
      throw new HealthKitSyncAuthorizationError();
    }
  }

  private async withScopeLock<T>(
    scope: string,
    operation: () => Promise<T>,
  ): Promise<T> {
    const previous = scopeTails.get(scope) ?? Promise.resolve();
    let release = (): void => undefined;
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    const current = previous.then(() => gate);
    scopeTails.set(scope, current);
    await previous;
    try {
      return await operation();
    } finally {
      release();
      if (scopeTails.get(scope) === current) scopeTails.delete(scope);
    }
  }
}
