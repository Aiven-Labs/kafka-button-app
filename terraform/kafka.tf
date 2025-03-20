resource "aiven_kafka" "kafka_button_app" {
  project      = data.aiven_project.button_app.project
  service_name = "${var.kafka_service_name}-${random_string.suffix.result}"
  cloud_name   = var.cloud_name
  plan         = "business-4"

  kafka_user_config {
    kafka_rest      = true
    kafka_connect   = true
    schema_registry = true
    kafka_version   = "3.8"

    kafka {
      group_max_session_timeout_ms = 70000
      log_retention_bytes          = 1000000000
    }

    public_access {
      kafka_rest    = true
      kafka_connect = true
    }
  }
}
