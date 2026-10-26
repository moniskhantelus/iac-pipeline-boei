output "storage_account_id" {
  description = "Resource ID of the WORM audit storage account."
  value       = azurerm_storage_account.audit.id
}

output "storage_account_name" {
  description = "Name of the WORM audit storage account."
  value       = azurerm_storage_account.audit.name
}

output "container_name" {
  description = "Name of the audit-records blob container."
  value       = azurerm_storage_container.audit.name
}

output "immutability_locked" {
  description = "Whether the container immutability policy is locked (false = draft/unlocked)."
  value       = azurerm_storage_container_immutability_policy.audit.locked
}

output "retention_days" {
  description = "Configured WORM retention period in days."
  value       = azurerm_storage_container_immutability_policy.audit.immutability_period_in_days
}
