terraform {
  required_version = ">= 1.9.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# The AWS provider, pointed at LocalStack instead of real AWS.
provider "aws" {
  region     = "us-east-1"
  access_key = "test" # LocalStack accepts any credentials
  secret_key = "test"

  # Skip checks that only work against real AWS.
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  # Use http://localstack:4566/<bucket>, not http://<bucket>.localstack:4566,
  # because the second form does not resolve on the Docker network.
  s3_use_path_style = true

  endpoints {
    s3  = "http://localstack:4566"
    iam = "http://localstack:4566"
    sts = "http://localstack:4566"
  }
}

variable "domains" {
  description = "Each domain gets a landing and a curated bucket. Add a name here to add a domain."
  type        = set(string)
  default     = ["finance", "marketing"]
}

module "data_domain" {
  source   = "./modules/data_domain"
  for_each = var.domains

  domain = each.key
}