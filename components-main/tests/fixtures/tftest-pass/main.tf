terraform {
  required_version = ">= 1.5.0"
}

variable "environment" {
  type    = string
  default = "dev"
}

resource "terraform_data" "example" {
  input = "kaas-${var.environment}"
}

output "fixture_id" {
  value = terraform_data.example.id
}
