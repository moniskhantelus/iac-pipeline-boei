# Minimal fixture: provider-free, local backend, no cloud calls.
terraform {
  required_version = ">= 1.5.0"
}

resource "terraform_data" "fixture" {
  input = "kaas-vnext-plan-fixture"
}

output "fixture_id" {
  value = terraform_data.fixture.id
}
