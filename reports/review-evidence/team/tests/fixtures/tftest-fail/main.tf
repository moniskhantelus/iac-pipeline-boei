terraform {
  required_version = ">= 1.5.0"
}

resource "terraform_data" "example" {
  input = "kaas"
}
# Intentionally: no 'fixture_id' output, so outputs_present assertion fails.
