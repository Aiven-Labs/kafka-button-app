resource "aiven_pg" "pg_button_app" {
  project      = data.aiven_project.button_app.project
  cloud_name   = var.cloud_name
  plan         = "startup-4"
  service_name = "${var.pg_service_name}-${random_string.suffix.result}"

}

output "pg_service_endpoint_uri" {
  value     = aiven_pg.pg_button_app.service_uri
  sensitive = true
}

