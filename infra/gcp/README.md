# Cloud Run release runbook

This directory contains reviewable infrastructure; it is not a live deployment.
No project, region, Firebase identity, Neon endpoint, bucket, budget or API image
has been selected for this repository. Do not run `terraform apply`, create a
repository/secret, or submit a Cloud Build until the owner supplies those
non-secret inputs and approves the spend. The example variable file contains
deliberate placeholders and cannot pass validation.

## Inputs and trust boundaries

The owner must supply the deployment GCP project, Firebase Auth project, region,
globally unique GCS bucket name, Artifact Registry image digest, Secret Manager
IDs and numeric version IDs for pooled and direct Neon URLs, maximum Cloud Run
instances, and the runtime API connection budget. Select a Neon pooled endpoint
for runtime and a direct endpoint for migrations; both must use
`sslmode=verify-full`. The migration direct connection is short-lived and must
fit separately within Neon plan limits. Set `DATABASE_CONNECTION_BUDGET` to the
approved runtime pool allocation; Terraform and cloud startup check
`2 × max instances × (pool size + overflow)` to allow old and new Cloud Run
revisions to overlap during rollout. The defaults are one worker,
pool 5, overflow 0 and concurrency 8. These are provisional caps, not measured
capacity or a cost estimate.

The Cloud Run service has public HTTPS ingress because a native Firebase client
does not present a Google Cloud Run invoker identity token. This disables Cloud
Run's invoker IAM check; every Profile/daily domain request still requires a
Firebase ID bearer token validated by the API. `/healthz` is intentionally
public, dependency-free process liveness. No other domain route is anonymous.
The runtime service account can read only the pooled DB secret, read Firebase
Auth user records for revocation checks, and use private objects in the one
bucket. The migration account can read only the direct DB secret and cannot
access application objects. No service-account keys are created. Terraform
does not create secrets or write secret values.

Terraform uses the GCS backend. First choose or create a dedicated, access-
restricted, versioned state bucket with public access prevention; state may
contain sensitive infrastructure metadata. Do not use a personal default
project, a repository-local state file, or a shared application-data bucket.
Supply backend configuration explicitly:

```bash
terraform -chdir=infra/gcp init \
  -backend-config="bucket=OWNER_APPROVED_TERRAFORM_STATE_BUCKET" \
  -backend-config="prefix=personal-health/staging"
```

The project must already be selected by the owner and have billing/permissions
approved. Create a dedicated Artifact Registry Docker repository explicitly in
the supplied project/region, and create the two Secret Manager secrets through
the approved secret-management workflow. Add versions without placing values in
command arguments, shell history, Terraform variables, CI logs, or Git. The
runtime value must be a Neon pooled `DATABASE_URL`; the migration value is the
direct `MIGRATION_DATABASE_URL`. Grant the Cloud Build service account writer
access to only the dedicated image repository.

## Build and initial deployment

Use Python 3.12 image `python:3.12.14-slim-bookworm`; Python runtime packages are
installed from `services/api/requirements-runtime.lock` with hash checking and
no dependency resolution. Build using explicit owner-supplied identifiers:

```bash
scripts/build_cloud_image.sh GCP_PROJECT_ID REGION ARTIFACT_REPOSITORY IMAGE_TAG
```

The script invokes Cloud Build and may incur cost. Resolve the pushed tag to an
immutable `...@sha256:...` URI. Use numeric Secret Manager version IDs for a
release. Copy `infra/gcp/release.tfvars.example` to an ignored local
`release.tfvars`, replace every placeholder, and review it without adding it to
Git. Set `deploy_api_service = false` for the first apply. Initialize, format,
and review the provider lock and plan using the explicit variable/backend files:

```bash
terraform -chdir=infra/gcp fmt -check
terraform -chdir=infra/gcp providers lock -platform=darwin_arm64 -platform=linux_amd64
terraform -chdir=infra/gcp validate
terraform -chdir=infra/gcp plan -var-file=release.tfvars -out=phase3.tfplan
```

Commit the generated `.terraform.lock.hcl` after reviewing its versions and
checksums; retain the plan only in approved local secure storage. `plan` is
read-only with respect to GCP, while `apply` creates billable resources and
changes IAM; inspect/approve it under the actual release policy. Initially
apply infrastructure with the API service disabled, then run the migration job:

```bash
terraform -chdir=infra/gcp apply phase3.tfplan
gcloud run jobs execute health-api-migrate --project GCP_PROJECT_ID \
  --region REGION --wait
```

Inspect the job result and migration head before setting
`deploy_api_service=true`. Create and review a new plan/apply to deploy the
serving revision. Publish its HTTPS URL and Firebase public app configuration
through the approved release channel; neither value is a server secret. Keep
`.env` and mobile build configuration out of container images.

## Subsequent compatible schema release

Use two immutable digests. Keep `api_image_uri` at the currently-serving image
and set `migration_image_uri` to the candidate. Apply the Job-only image change,
execute and inspect `health-api-migrate`, then update `api_image_uri` and apply
the serving revision. Migrations must be additive/expand-first and support both
old and new revisions. Do not put migrations in the startup command or let each
replica run them. The alembic environment reads only
`APP_ENV=cloud` and `MIGRATION_DATABASE_URL` for the cloud release Job; it does
not need the runtime DB secret.

## Rollback and failure response

For an API-only regression, set `api_image_uri` back to the previous immutable
digest and apply the reviewed plan. Do not downgrade the database as part of an
image rollback. First verify that the old image remains compatible with the
applied schema. If the migration itself needs repair, ship a corrective
forward-only migration; test recovery on disposable staging and protect health
data before any destructive action. An incompatible schema change requires an
expand/migrate/contract sequence across separately reviewed releases.

On Firebase verifier, Neon, or GCS outage, domain APIs fail closed with
sanitized 503 responses; `/healthz` remains process liveness and does not claim
dependency readiness. Check operational metrics and Cloud Run logs without
logging tokens, request bodies, health values, SQL parameters or secret values.
If the job fails, do not deploy the candidate API revision. Preserve the prior
serving image and investigate only with approved synthetic staging data.

## Current release status

The API/storage/config/auth and mobile lifecycle have offline implementations;
deterministic tests do not prove Firebase, GCS, Neon or Cloud Run behavior. At
the 2026-10-04 checkpoint no `gcloud`, Terraform/OpenTofu, Docker or Podman
executable is available on the implementation host, and no release input set
has been supplied. The Terraform has therefore not been initialized, formatted,
validated or applied; no live Cloud Run job/service, Firebase identity, GCS IAM,
Neon migration, billing, rollback or connection measurement is claimed. See
[`phase-3-release.md`](../../docs/implementation/evidence/phase-3-release.md)
for the explicit evidence boundary.
