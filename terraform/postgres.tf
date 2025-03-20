resource "aiven_pg" "pg_button_app" {
  project      = data.aiven_project.button_app.project
  cloud_name   = var.cloud_name
  plan         = "hobbyist"
  service_name = "pg-button-app-${random_string.suffix.result}"

}
