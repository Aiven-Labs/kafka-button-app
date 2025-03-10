variable "aiven_kafka_service_name" {
  type = string
}

resource "aiven_kafka" "kafka_1" {
  project                 = data.aiven_project.example_project.project
  cloud_name              = "google-europe-west1"
  plan                    = "business-4"
  service_name            = var.aiven_kafka_service_name

  kafka_user_config {
    kafka_rest      = true
    kafka_connect   = true
    schema_registry = true
    kafka_version   = "3.8.1"

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

resource "aiven_kafka_topic" "kafka_1_topic" {
  project                = data.aiven_project.example_project.project
  service_name           = aiven_kafka.example_kafka.service_name
  topic_name             = "click_interactions"
  partitions             = 1
  replication            = 1
  termination_protection = true

  config {
    flush_ms       = 10
    cleanup_policy = "compact,delete"
  }

variable "aiven_pg_service_name" {
  type = string
}

resource "aiven_pg" "ps1" {
  project      = data.aiven_project.langchain_demo.project
  cloud_name   = "google-us-east1"
  plan         = "startup-4"
  service_name = var.aiven_pg_service_name

}

output "pg_service_endpoint_uri" {
  value     = aiven_pg.ps1.service_uri
  sensitive = true
}

