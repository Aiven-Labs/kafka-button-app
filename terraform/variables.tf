variable "aiven_api_token" {
  description = "The api token for the aiven service"
  type        = string
}

variable "aiven_project_name" {
  description = "The aiven project"
  type        = string
}

variable "cloud_name" {
  description = "The cloud provider and region for Aiven services. Example: google-us-east-1"
  type        = string
}

variable "clickhouse_service_name" {
  description = "The service name for the Aiven for Clickhouse Instance"
  type        = string
}

variable "pg_service_name" {
  description = "The service name for the Aiven for postgreSQL Instance"
  type        = string
}

variable "kafka_service_name" {
  description = "The service name for the Aiven for Apache Kafka Instance"
  type        = string
}
