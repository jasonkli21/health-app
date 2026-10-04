terraform {
  required_version = ">= 1.8.0, < 2.0.0"

  backend "gcs" {}

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "= 8.2.0"
    }
  }
}

provider "google" {
  project = var.gcp_project_id
  region  = var.region
}
