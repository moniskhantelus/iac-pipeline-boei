resource "azurerm_resource_group" "audit" {
  name     = var.resource_group_name
  location = var.location
  tags     = var.tags
}

resource "azurerm_storage_account" "audit" {
  name                     = var.storage_account_name # strataaudit
  resource_group_name      = azurerm_resource_group.audit.name
  location                 = azurerm_resource_group.audit.location
  account_tier             = "Standard"
  account_replication_type = "GRS" # geo-redundant for compliance durability
  account_kind             = "StorageV2"

  min_tls_version                 = "TLS1_2"
  https_traffic_only_enabled      = true
  public_network_access_enabled   = false # data-plane via private endpoint / trusted network
  shared_access_key_enabled       = false # force AAD (RBAC) auth; no account keys (NFR1)
  allow_nested_items_to_be_public = false

  tags = var.tags

  # NOTE: blob versioning is intentionally NOT enabled for immutability. Container-level
  # time-based retention does not require it; enabling it is an independent operational choice.
}

resource "azurerm_storage_container" "audit" {
  name                  = var.container_name # audit-records
  storage_account_id    = azurerm_storage_account.audit.id
  container_access_type = "private"
}

# WORM: CONTAINER-LEVEL time-based retention, left UNLOCKED (draft).
# locked is INTENTIONALLY false and there is NO variable to flip it (AC2). The lock is a manual
# `az ... immutability-policy lock` step performed only after legal sign-off (see runbook).
resource "azurerm_storage_container_immutability_policy" "audit" {
  # Preferred azurerm 4.x wiring: the container's resource-manager ID. In azurerm ~> 4.80 the
  # container's `.id` IS the resource-manager ID; the older `.resource_manager_id` attribute is
  # deprecated. If a pinned minor rejects this, the legacy fallback is the explicit pair
  # `storage_account_name` + `container_name` (every other attribute unchanged).
  storage_container_resource_manager_id = azurerm_storage_container.audit.id

  immutability_period_in_days         = var.retention_days # 730 — authoritative
  locked                              = false              # DRAFT — never true in code
  protected_append_writes_all_enabled = false              # audit records are whole-file writes
}
