resource "aiven_service_integration" "clickhouse_kafka_integration" {
  project                  = data.aiven_project.button_app.project
  destination_service_name = aiven_clickhouse.ch_button_app.service_name
  integration_type         = "clickhouse_kafka"
  source_service_name      = aiven_kafka.kafka_button_app.service_name
}
