variable "gcp_project_id" {
  type        = string
  description = "User-supplied Google Cloud deployment project ID."

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.gcp_project_id))
    error_message = "Supply an explicit Google Cloud project ID."
  }
}

variable "firebase_project_id" {
  type        = string
  description = "Firebase Authentication project whose ID tokens the API accepts."

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{4,28}[a-z0-9]$", var.firebase_project_id))
    error_message = "Supply an explicit Firebase project ID."
  }
}

variable "region" {
  type        = string
  description = "User-selected Cloud Run/GCS/Secret Manager region."

  validation {
    condition     = can(regex("^[a-z0-9]+(-[a-z0-9]+)+$", var.region))
    error_message = "Supply an explicit Google Cloud region."
  }
}

variable "gcs_bucket_name" {
  type        = string
  description = "Existing user-selected private-data bucket name to create."
}

variable "api_image_uri" {
  type        = string
  description = "Immutable serving API image URI pinned by sha256 digest."

  validation {
    condition     = can(regex("^.+@sha256:[0-9a-f]{64}$", var.api_image_uri))
    error_message = "Use an immutable Artifact Registry image URI pinned to sha256 digest."
  }
}

variable "migration_image_uri" {
  type        = string
  description = "Immutable image for the one-off Alembic migration Job."

  validation {
    condition     = can(regex("^.+@sha256:[0-9a-f]{64}$", var.migration_image_uri))
    error_message = "Use an immutable Artifact Registry image URI pinned to sha256 digest."
  }
}

variable "deploy_api_service" {
  type        = bool
  description = "Create/update public Cloud Run ingress only after the migration gate."
  default     = false
}

variable "runtime_database_secret_id" {
  type        = string
  description = "Existing Secret Manager secret ID containing pooled Neon DATABASE_URL."
}

variable "migration_database_secret_id" {
  type        = string
  description = "Existing Secret Manager secret ID containing direct Neon MIGRATION_DATABASE_URL."
}

variable "runtime_database_secret_version" {
  type        = string
  description = "Runtime secret version ID; pin numeric versions for controlled rollout."

  validation {
    condition     = can(regex("^[1-9][0-9]*$", var.runtime_database_secret_version))
    error_message = "Pin a numeric runtime database secret version for this release."
  }
}

variable "migration_database_secret_version" {
  type        = string
  description = "Migration secret version ID; pin numeric versions for release."

  validation {
    condition     = can(regex("^[1-9][0-9]*$", var.migration_database_secret_version))
    error_message = "Pin a numeric migration database secret version for this release."
  }
}

variable "cloud_max_instances" {
  type        = number
  description = "Explicit Cloud Run API instance cap chosen from the approved Neon budget."

  validation {
    condition = (
      var.cloud_max_instances >= 1 &&
      var.cloud_max_instances <= 100 &&
      floor(var.cloud_max_instances) == var.cloud_max_instances
    )
    error_message = "cloud_max_instances must be an integer from 1 through 100."
  }
}

variable "database_connection_budget" {
  type        = number
  description = "Maximum runtime API DB connections reserved in the user-approved Neon budget."

  validation {
    condition = (
      var.database_connection_budget >= 1 &&
      floor(var.database_connection_budget) == var.database_connection_budget
    )
    error_message = "database_connection_budget must be a positive integer."
  }
}

variable "database_pool_size" {
  type        = number
  description = "Per-instance SQLAlchemy pool size."
  default     = 5

  validation {
    condition = (
      var.database_pool_size >= 1 &&
      var.database_pool_size <= 20 &&
      floor(var.database_pool_size) == var.database_pool_size
    )
    error_message = "database_pool_size must be an integer from 1 through 20."
  }
}

variable "database_max_overflow" {
  type        = number
  description = "Per-instance SQLAlchemy pool overflow."
  default     = 0

  validation {
    condition = (
      var.database_max_overflow >= 0 &&
      var.database_max_overflow <= 5 &&
      floor(var.database_max_overflow) == var.database_max_overflow
    )
    error_message = "database_max_overflow must be an integer from 0 through 5."
  }
}

locals {
  api_name = "health-api"
  # Cloud Run can temporarily keep old and new revisions alive together.
  runtime_connections = 2 * var.cloud_max_instances * (var.database_pool_size + var.database_max_overflow)
}

check "database_connection_budget" {
  assert {
    condition     = local.runtime_connections <= var.database_connection_budget
    error_message = "Cloud Run maximum instances multiplied by per-instance pool capacity exceeds the approved DB connection budget."
  }
}
