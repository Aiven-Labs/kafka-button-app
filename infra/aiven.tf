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

output "clickhouse_service_name" {
  value = module.aiven_services_dev.clickhouse_service_name
}

output "kafka_service_name" {
  value = module.aiven_services_dev.kafka_service_name
}
