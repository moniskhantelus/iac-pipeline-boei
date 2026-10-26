terraform {
  required_version = ">= 1.6.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.80"
    }
  }

  # Configured via backend.hcl at init time (same pattern as the pipeline jobs). This stack's OWN
  # state MUST live in a NON-WORM location — never the strataaudit container (see backend.hcl.example).
  backend "azurerm" {}
}

provider "azurerm" {
  # AzureUSGovernment — hardcoded ON PURPOSE. This stack is applied out-of-band by a platform
  # operator, NOT by the consumer pipeline, so it must not depend on the CI AZ_LOGIN_CSP_TYPE
  # variable. The two cloud selectors are intentionally independent.
  environment = "usgovernment"
  features {}
}
