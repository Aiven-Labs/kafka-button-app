
resource "aiven_service_integration" "clickhouse_kafka_integration" {
  project                  = data.aiven_project.button_app.project
  destination_service_name = aiven_clickhouse.ch_button_app.service_name
  integration_type         = "clickhouse_kafka"
  source_service_name      = aiven_kafka.kafka_button_app.service_name
  clickhouse_kafka_user_config {
    tables {
      name        = "button_presses_from_kafka"
      data_format = "AvroConfluent"
      group_name  = "button_presses_from_kafka_consumer"

      topics {
        name = "button_presses"
      }

      columns {
        name = "session_id"
        type = "UUID"
      }
      columns {
        name = "timestamp"
        type = "DateTime64(6)"
      }
      columns {
        name = "action"
        type = "String"
      }
      columns {
        name = "country_name"
        type = "String"
      }
      columns {
        name = "country_code"
        type = "FixedString(2)"
      }
      columns {
        name = "subdivision_name"
        type = "String"
      }
      columns {
        name = "subdivision_code"
        type = "String"
      }
      columns {
        name = "city_name"
        type = "String"
      }
      columns {
        name = "cohort"
        type = "Nullable(Smallint)"
      }
    }
  }
}
