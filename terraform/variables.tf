variable "aiven_api_token" {
  description = "The api token for the aiven service"
  type        = string
}

variable "aiven_project_name" {
  description = "The aiven project"
  type        = string
}

variable "cloud_name" {
  description = "The cloud provider and region for Aiven services. Example: google-us-east1"
  type        = string
}
