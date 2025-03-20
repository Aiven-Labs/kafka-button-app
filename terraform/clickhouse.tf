resource "aiven_clickhouse" "ch_button_app" {
  project      = data.aiven_project.button_app.project
  cloud_name   = var.cloud_name
  plan         = "startup-16"
  service_name = "${var.clickhouse_service_name}-${random_string.suffix.result}"
}
