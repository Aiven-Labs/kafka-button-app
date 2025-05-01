resource "aiven_clickhouse" "ch_button_app" {
  project      = var.aiven_project_name
  cloud_name   = var.cloud_name
  plan         = "startup-16"
  service_name = "ch-button-app-${random_string.suffix.result}"
}


output "clickhouse_service_name" {
  value = aiven_clickhouse.ch_button_app.service_name
}

output "clickhouse_service_host" {
  value = aiven_clickhouse.ch_button_app.service_host
}

output "clickhouse_service_uri" {
  value     = aiven_clickhouse.ch_button_app.service_uri
  sensitive = true
}

output "clickhouse_port" {
  value = aiven_clickhouse.ch_button_app.service_port
}

output "clickhouse_user" {
  value = aiven_clickhouse.ch_button_app.service_username
}

output "clickhouse_pwd" {
  value     = aiven_clickhouse.ch_button_app.service_password
  sensitive = true
}

output "clickhouse_https_port" {
  value = aiven_clickhouse.ch_button_app.components[0].port
}
