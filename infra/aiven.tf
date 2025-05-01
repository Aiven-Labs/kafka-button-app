terraform {
  required_version = ">= 1.0.0"
}

module "aiven_services_dev" {
  source = "./modules/button_app/"

  # Required parameters
  aiven_api_token    = var.aiven_api_token
  aiven_project_name = var.aiven_project_name
  cloud_name         = var.cloud_name
  pg_version         = "17"

}

# Kafka Outputs
output "kafka_service_name" {
  value = module.aiven_services_dev.kafka_service_name
}

output "kafka_service_uri" {
  value     = module.aiven_services_dev.kafka_service_uri
  sensitive = true
}

output "topic_name" {
  value = module.aiven_services_dev.kafka_topic
}

output "schema_registry_uri" {
  value     = module.aiven_services_dev.kafka_schema_registry_uri
  sensitive = true
}

# PG Outputs
output "pg_service_uri" {
  value     = module.aiven_services_dev.PG_SERVICE_URI
  sensitive = true
}

# Clickhouse Outputs
output "clickhouse_service_name" {
  value = module.aiven_services_dev.clickhouse_service_name
}

output "clickhouse_service_uri" {
  value     = module.aiven_services_dev.clickhouse_service_uri
  sensitive = true
}

output "ch_host" {
  value = module.aiven_services_dev.clickhouse_service_host
}

output "ch_port" {
  value = module.aiven_services_dev.clickhouse_port
}

output "ch_https_port" {
  value = module.aiven_services_dev.clickhouse_https_port
}

output "ch_user" {
  value = module.aiven_services_dev.clickhouse_user
}

output "ch_password" {
  value     = module.aiven_services_dev.clickhouse_pwd
  sensitive = true
}
