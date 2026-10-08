resource "google_project_service" "required" {
  for_each = toset([
    "serviceusage.googleapis.com",
    "run.googleapis.com",
    "storage.googleapis.com",
    "secretmanager.googleapis.com",
    "iam.googleapis.com",
    "artifactregistry.googleapis.com",
  ])

  project            = var.gcp_project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_project_service" "firebase_auth" {
  project            = var.firebase_project_id
  service            = "identitytoolkit.googleapis.com"
  disable_on_destroy = false
}

resource "google_storage_bucket" "private_objects" {
  project                     = var.gcp_project_id
  name                        = var.gcs_bucket_name
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  depends_on = [google_project_service.required]
}

resource "google_service_account" "runtime" {
  project      = var.gcp_project_id
  account_id   = "health-api-runtime"
  display_name = "Health API runtime"
}

resource "google_service_account" "migrator" {
  project      = var.gcp_project_id
  account_id   = "health-api-migrator"
  display_name = "Health API schema release job"
}

resource "google_storage_bucket_iam_member" "runtime_objects" {
  bucket = google_storage_bucket.private_objects.name
  role   = "roles/storage.objectUser"
  member = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_secret_manager_secret_iam_member" "runtime_database" {
  project   = var.gcp_project_id
  secret_id = var.runtime_database_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_secret_manager_secret_iam_member" "migration_database" {
  project   = var.gcp_project_id
  secret_id = var.migration_database_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.migrator.email}"
}

resource "google_project_iam_member" "runtime_firebase_user_read" {
  project = var.firebase_project_id
  role    = "roles/firebaseauth.viewer"
  member  = "serviceAccount:${google_service_account.runtime.email}"
}

resource "google_cloud_run_v2_service" "api" {
  count = var.deploy_api_service ? 1 : 0

  project             = var.gcp_project_id
  name                = local.api_name
  location            = var.region
  deletion_protection = true
  ingress             = "INGRESS_TRAFFIC_ALL"
  # Mobile sends Firebase ID tokens, not Cloud Run IAM identity tokens. The
  # application verifies bearer identity on every owner-scoped route.
  invoker_iam_disabled = true
  # Cloud Run readiness probes are currently a preview feature.
  launch_stage         = "BETA"

  template {
    service_account                  = google_service_account.runtime.email
    timeout                          = "300s"
    max_instance_request_concurrency = 8
    scaling {
      min_instance_count = 0
      max_instance_count = var.cloud_max_instances
    }

    containers {
      image = var.api_image_uri
      ports {
        container_port = 8080
      }
      startup_probe {
        timeout_seconds   = 5
        period_seconds    = 10
        failure_threshold = 6

        http_get {
          path = "/readyz"
          port = 8080
        }
      }
      readiness_probe {
        timeout_seconds   = 5
        period_seconds    = 10
        failure_threshold = 3
        success_threshold = 1

        http_get {
          path = "/readyz"
          port = 8080
        }
      }
      liveness_probe {
        timeout_seconds   = 5
        period_seconds    = 30
        failure_threshold = 3

        http_get {
          path = "/healthz"
          port = 8080
        }
      }
      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name  = "APP_ENV"
        value = "cloud"
      }
      env {
        name  = "AUTH_MODE"
        value = "firebase"
      }
      env {
        name  = "OBJECT_STORAGE_BACKEND"
        value = "gcs"
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.gcp_project_id
      }
      env {
        name  = "FIREBASE_PROJECT_ID"
        value = var.firebase_project_id
      }
      env {
        name  = "GCS_BUCKET"
        value = google_storage_bucket.private_objects.name
      }
      env {
        name  = "CLOUD_MAX_INSTANCES"
        value = tostring(var.cloud_max_instances)
      }
      env {
        name  = "DATABASE_CONNECTION_BUDGET"
        value = tostring(var.database_connection_budget)
      }
      env {
        name  = "DATABASE_POOL_SIZE"
        value = tostring(var.database_pool_size)
      }
      env {
        name  = "DATABASE_MAX_OVERFLOW"
        value = tostring(var.database_max_overflow)
      }
      env {
        name = "DATABASE_URL"
        value_source {
          secret_key_ref {
            secret  = var.runtime_database_secret_id
            version = var.runtime_database_secret_version
          }
        }
      }
    }
  }

  depends_on = [
    google_project_service.required,
    google_storage_bucket_iam_member.runtime_objects,
    google_secret_manager_secret_iam_member.runtime_database,
    google_project_iam_member.runtime_firebase_user_read,
    google_project_service.firebase_auth,
  ]
}

resource "google_cloud_run_v2_job" "migration" {
  project             = var.gcp_project_id
  name                = "health-api-migrate"
  location            = var.region
  deletion_protection = true

  template {
    parallelism = 1
    task_count  = 1
    template {
      service_account = google_service_account.migrator.email
      max_retries     = 0
      timeout         = "600s"

      containers {
        image   = var.migration_image_uri
        command = ["alembic"]
        args    = ["upgrade", "head"]

        env {
          name  = "APP_ENV"
          value = "cloud"
        }
        env {
          name = "MIGRATION_DATABASE_URL"
          value_source {
            secret_key_ref {
              secret  = var.migration_database_secret_id
              version = var.migration_database_secret_version
            }
          }
        }
      }
    }
  }

  depends_on = [
    google_project_service.required,
    google_secret_manager_secret_iam_member.migration_database,
  ]
}
