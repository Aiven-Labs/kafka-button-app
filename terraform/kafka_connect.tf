locals {
  username_pwd        = "${aiven_kafka.kafka_button_app.service_username}:${aiven_kafka.kafka_button_app.service_password}"
  modified_schema_url = replace(aiven_kafka.kafka_button_app.kafka[0].schema_registry_uri, "/^https:\\/\\/[^@]+@/", "https://")
}

resource "aiven_kafka_connector" "kafka_pg_connector" {
  project        = data.aiven_project.button_app.project
  service_name   = aiven_kafka.kafka_button_app.service_name
  connector_name = "sink_button_presses_avro_karapace"

  depends_on = [
    aiven_kafka.kafka_button_app,
    aiven_kafka_topic.button_app,
    aiven_kafka_schema.button-app-schema,
    aiven_pg.pg_button_app,
  ]

  config = {
    "name"                                                 = "sink_button_presses_avro_karapace"
    "topics"                                               = aiven_kafka_topic.button_app.topic_name
    "connector.class"                                      = "io.aiven.connect.jdbc.JdbcSinkConnector"
    "connection.url"                                       = "jdbc:postgresql://${aiven_pg.pg_button_app.service_host}:${aiven_pg.pg_button_app.service_port}/${aiven_pg.pg_button_app.pg[0].dbname}?ssl_mode=${aiven_pg.pg_button_app.pg[0].sslmode}"
    "connection.user"                                      = aiven_pg.pg_button_app.service_username
    "connection.password"                                  = aiven_pg.pg_button_app.service_password
    "tasks.max"                                            = "1"
    "auto.create"                                          = "false"
    "auto.evolve"                                          = "false"
    "insert.mode"                                          = "insert"
    "delete.enabled"                                       = "false"
    "pk.mode"                                              = "none"
    "key.converter"                                        = "io.confluent.connect.avro.AvroConverter"
    "key.converter.schema.registry.url"                    = local.modified_schema_url
    "key.converter.basic.auth.credentials.source"          = "USER_INFO"
    "key.converter.schema.registry.basic.auth.user.info"   = local.username_pwd
    "value.converter"                                      = "io.confluent.connect.avro.AvroConverter"
    "value.converter.schema.registry.url"                  = local.modified_schema_url
    "value.converter.basic.auth.credentials.source"        = "USER_INFO"
    "value.converter.schema.registry.basic.auth.user.info" = local.username_pwd
  }

}


