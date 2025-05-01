resource "aiven_kafka_schema" "button-app-schema" {
  project             = var.aiven_project_name
  service_name        = aiven_kafka.kafka_button_app.service_name
  subject_name        = "button-app-schema1"
  compatibility_level = "FORWARD"
  schema_type         = "AVRO"

  timeouts {
    create = "5m"
  }


  schema = <<EOT
    {
        "doc": "Web app interactions",
        "name": "${aiven_kafka_topic.button_app.topic_name}",
        "type": "record",
        "fields": [
            {"name": "session_id", "type": "string", "logicalType": "uuid"},
            {"name": "timestamp", "type": "long", "logicalType": "timestamp-micros"},
            {"name": "action", "type": "string"},
            {"name": "country_name", "type": "string"},
            {"name": "country_code", "type": "string"},
            {"name": "subdivision_name", "type": "string"},
            {"name": "subdivision_code", "type": "string"},
            {"name": "city_name", "type": "string"},
            {"name": "cohort", "type": ["null", "int"], "default": null}
        ]
    }
    EOT
}

