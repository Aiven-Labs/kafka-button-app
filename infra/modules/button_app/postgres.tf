resource "aiven_pg" "pg_button_app" {
  project      = var.aiven_project_name
  cloud_name   = var.cloud_name
  plan         = "startup-4"
  service_name = "pg-button-app-${random_string.suffix.result}"

  tag {
    key   = "application"
    value = var.tag_application_value
  }

  pg_user_config {
    pg_version = var.pg_version
  }
}

output "PG_SERVICE_URI" {
  description = "the service uri for the aiven for postgresql instance"
  value       = aiven_pg.pg_button_app.service_uri
  sensitive   = true
}
