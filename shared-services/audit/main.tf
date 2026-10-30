terraform {
  required_version = ">= 1.6.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.80.0"
    }
  }
  # Configure a dedicated shared-services backend at deployment time.
  backend "azurerm" {}
}
provider "azurerm" {
  features {}
  subscription_id     = var.subscription_id
  environment         = var.azure_environment
  storage_use_azuread = true
}
variable "subscription_id" { type = string }
variable "azure_environment" {
  type    = string
  default = "usgovernment"
}
variable "resource_group_name" { type = string }
variable "location" { type = string }
variable "storage_account_name" { type = string }
variable "state_storage_account_name" { type = string }
# Additional Terraform state account names to assert separation against (set-based check).
# Defaults to empty so existing callers keep working with only the single-name check.
variable "state_storage_account_names" {
  type    = list(string)
  default = []
}
variable "runner_identity_principal_id" { type = string }
variable "reviewer_principal_id" { type = string }
variable "runner_subnet_ids" { type = list(string) }
# Subnet for the audit storage account's private endpoint NIC (REQ-INT-26).
variable "private_endpoint_subnet_id" { type = string }
# Private DNS zone IDs for the blob private endpoint. For Azure Gov the blob private
# DNS zone is `privatelink.blob.core.usgovcloudapi.net` and must be supplied by the
# deploying environment. Left empty when DNS is managed centrally.
variable "private_dns_zone_ids" {
  type    = list(string)
  default = []
}

resource "azurerm_resource_group" "audit" {
  name     = var.resource_group_name
  location = var.location
  lifecycle { prevent_destroy = true }
}
resource "azurerm_storage_account" "audit" {
  name                            = var.storage_account_name
  resource_group_name             = azurerm_resource_group.audit.name
  location                        = azurerm_resource_group.audit.location
  account_tier                    = "Standard"
  account_replication_type        = "GRS"
  account_kind                    = "StorageV2"
  min_tls_version                 = "TLS1_2"
  shared_access_key_enabled       = false
  default_to_oauth_authentication = true
  allow_nested_items_to_be_public = false
  # REQ-INT-26: disable public network access; access is via the private endpoint only.
  public_network_access_enabled = false
  # Secondary control: with public access disabled these VNet rules are belt-and-suspenders.
  network_rules {
    default_action             = "Deny"
    bypass                     = ["None"]
    virtual_network_subnet_ids = var.runner_subnet_ids
  }
  lifecycle {
    prevent_destroy = true
    precondition {
      condition = (
        lower(var.storage_account_name) != lower(var.state_storage_account_name) &&
        !contains([for s in var.state_storage_account_names : lower(s)], lower(var.storage_account_name))
      )
      error_message = "Audit storage must be separate from Terraform state storage."
    }
  }
}
resource "azurerm_private_endpoint" "audit" {
  name                = "${var.storage_account_name}-blob-pe"
  resource_group_name = azurerm_resource_group.audit.name
  location            = azurerm_resource_group.audit.location
  subnet_id           = var.private_endpoint_subnet_id
  private_service_connection {
    name                           = "${var.storage_account_name}-blob-psc"
    private_connection_resource_id = azurerm_storage_account.audit.id
    subresource_names              = ["blob"]
    is_manual_connection           = false
  }
  # Only wire a DNS zone group when IDs are supplied; some environments manage DNS centrally.
  dynamic "private_dns_zone_group" {
    for_each = length(var.private_dns_zone_ids) > 0 ? [1] : []
    content {
      name                 = "${var.storage_account_name}-blob-dns"
      private_dns_zone_ids = var.private_dns_zone_ids
    }
  }
  lifecycle { prevent_destroy = true }
}
resource "azurerm_storage_container" "audit" {
  name                  = "audit"
  storage_account_id    = azurerm_storage_account.audit.id
  container_access_type = "private"
  lifecycle { prevent_destroy = true }
}
resource "azurerm_storage_container_immutability_policy" "audit" {
  storage_container_resource_manager_id = azurerm_storage_container.audit.id
  immutability_period_in_days           = 730
  locked                                = false # DRAFT: legal approval required; no lock automation.
  protected_append_writes_enabled       = false
  protected_append_writes_all_enabled   = false
  lifecycle { prevent_destroy = true }
}
resource "azurerm_role_definition" "writer" {
  name  = "${var.storage_account_name}-audit-writer"
  scope = azurerm_resource_group.audit.id
  permissions {
    actions      = []
    data_actions = ["Microsoft.Storage/storageAccounts/blobServices/containers/blobs/write"]
  }
  assignable_scopes = [azurerm_resource_group.audit.id]
}
resource "azurerm_role_assignment" "writer" {
  scope              = azurerm_storage_container.audit.id
  role_definition_id = azurerm_role_definition.writer.role_definition_resource_id
  principal_id       = var.runner_identity_principal_id
}
resource "azurerm_role_assignment" "reader" {
  scope                = azurerm_storage_container.audit.id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = var.reviewer_principal_id
}
output "audit_storage_account" { value = azurerm_storage_account.audit.name }
output "audit_container" { value = azurerm_storage_container.audit.name }
output "policy_id" { value = azurerm_storage_container_immutability_policy.audit.id }
output "private_endpoint_id" { value = azurerm_private_endpoint.audit.id }
