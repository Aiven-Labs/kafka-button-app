terraform {
  required_version = ">= 1.0.0"


  required_providers {
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }

    aiven = {
      source  = "aiven/aiven"
      version = ">= 4.0.0, < 5.0.0"
    }
  }
}

provider "aiven" {
  api_token = var.aiven_api_token
}

data "aiven_project" "button_app" {
  project = var.aiven_project_name
}

resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}
