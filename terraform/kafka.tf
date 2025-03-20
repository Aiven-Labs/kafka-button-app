resource "aiven_kafka" "kafka_button_app" {
  project      = data.aiven_project.button_app.project
  service_name = "kafka-button-app-${random_string.suffix.result}"
  cloud_name   = var.cloud_name
  plan         = "business-4"

  kafka_user_config {
    kafka_rest      = true
    kafka_connect   = true
    schema_registry = true
    kafka_version   = "3.8"

    tiered_storage {
      enabled = true
    }

    kafka {
      group_max_session_timeout_ms = 70000
      log_retention_bytes          = 1000000000
      auto_create_topics_enable    = true
    }

    public_access {
      kafka_rest    = true
      kafka_connect = true
    }
  }
}

resource "aiven_kafka_topic" "button_app" {
  project                = data.aiven_project.button_app.project
  service_name           = aiven_kafka.kafka_button_app.service_name
  topic_name             = "button_presses"
  partitions             = 3
  replication            = 2
  termination_protection = true

  config {
    cleanup_policy        = "delete"
    remote_storage_enable = true
    local_retention_ms    = 30000
  }

  timeouts {
    create = "1m"
    read   = "5m"
  }
}


output "kafka_service_name" {
  value = aiven_kafka.kafka_button_app.service_name
}
