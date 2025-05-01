resource "aiven_kafka" "kafka_button_app" {
  project      = var.aiven_project_name
  service_name = "kafka-button-app-${random_string.suffix.result}"
  cloud_name   = var.cloud_name
  plan         = var.kafka_plan

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
      auto_create_topics_enable    = false
    }

    public_access {
      kafka_rest    = true
      kafka_connect = true
    }
  }
}

resource "aiven_kafka_topic" "button_app" {
  project                = var.aiven_project_name
  service_name           = aiven_kafka.kafka_button_app.service_name
  topic_name             = "button_presses"
  partitions             = 3
  replication            = 2
  termination_protection = false

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

output "kafka_service_uri" {
  value     = aiven_kafka.kafka_button_app.service_uri
  sensitive = true
}

output "kafka_schema_registry_uri" {
  value     = aiven_kafka.kafka_button_app.kafka[0].schema_registry_uri
  sensitive = true
}

output "kafka_topic" {
  value = aiven_kafka_topic.button_app.topic_name
}
