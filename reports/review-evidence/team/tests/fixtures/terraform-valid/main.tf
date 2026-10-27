terraform {
  required_version = ">= 1.5.0"
}

variable "name" {
  type    = string
  default = "kaas"
}

output "name" {
  value = var.name
}
