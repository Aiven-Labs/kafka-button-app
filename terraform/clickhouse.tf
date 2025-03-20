resource "aiven_clickhouse" "ch_button_app" {
  project      = data.aiven_project.button_app.project
  cloud_name   = var.cloud_name
  plan         = "startup-16"
  service_name = "ch-button-app-${random_string.suffix.result}"
}


output "clickhouse_service_name" {
  value = aiven_clickhouse.ch_button_app.service_name
}
