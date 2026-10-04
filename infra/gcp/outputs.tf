output "api_url" {
  description = "Public HTTPS URL. Domain routes require Firebase bearer auth."
  value       = var.deploy_api_service ? google_cloud_run_v2_service.api[0].uri : null
}

output "gcs_bucket_name" {
  description = "Private owner-namespaced object bucket."
  value       = google_storage_bucket.private_objects.name
}

output "runtime_service_account" {
  description = "Workload identity for the serving API."
  value       = google_service_account.runtime.email
}

output "migration_job_name" {
  description = "One-off Alembic Cloud Run Job name."
  value       = google_cloud_run_v2_job.migration.name
}
