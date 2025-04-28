resource "aiven_clickhouse" "ch_button_app" {
  project      = var.aiven_project_name
  cloud_name   = var.cloud_name
  plan         = "startup-16"
  service_name = "ch-button-app-${random_string.suffix.result}"
}


output "clickhouse_service_name" {
  value = aiven_clickhouse.ch_button_app.service_name
}
