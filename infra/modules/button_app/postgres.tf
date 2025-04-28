resource "aiven_pg" "pg_button_app" {
  project      = var.aiven_project_name
  cloud_name   = var.cloud_name
  plan         = "hobbyist"
  service_name = "pg-button-app-${random_string.suffix.result}"

  pg_user_config {
    pg_version = var.pg_version
  }
}
