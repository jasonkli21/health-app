#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 4 ]]; then
  echo "Usage: $0 GCP_PROJECT_ID REGION ARTIFACT_REGISTRY_REPOSITORY IMAGE_TAG" >&2
  exit 64
fi

project_id="$1"
region="$2"
repository="$3"
tag="$4"

if [[ ! "$project_id" =~ ^[a-z][a-z0-9-]{4,28}[a-z0-9]$ ]]; then
  echo "GCP_PROJECT_ID is not a valid project ID." >&2
  exit 64
fi
if [[ ! "$region" =~ ^[a-z0-9]+(-[a-z0-9]+)+$ ]]; then
  echo "REGION must be an explicit Google Cloud region identifier." >&2
  exit 64
fi
if [[ ! "$repository" =~ ^[a-z][a-z0-9-]{3,62}$ ]]; then
  echo "ARTIFACT_REGISTRY_REPOSITORY is not a valid repository ID." >&2
  exit 64
fi
if [[ ! "$tag" =~ ^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$ ]]; then
  echo "IMAGE_TAG contains unsupported characters." >&2
  exit 64
fi

image_uri="${region}-docker.pkg.dev/${project_id}/${repository}/health-api:${tag}"
echo "Submitting the API image build to the explicitly supplied project and region."
gcloud builds submit \
  --project "$project_id" \
  --region "$region" \
  --config infra/gcp/cloudbuild.yaml \
  --substitutions "_IMAGE_URI=${image_uri}" \
  .
echo "Built image: ${image_uri}"
