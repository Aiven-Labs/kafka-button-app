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

resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}
