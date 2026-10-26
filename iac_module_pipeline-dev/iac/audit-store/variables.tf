variable "location" {
  type        = string
  description = "Azure Government region for the audit store."
  default     = "usgovvirginia"
}

variable "resource_group_name" {
  type        = string
  description = "Resource group for the WORM audit store (separate from the tfstate RG)."
  default     = "kaas-shared-audit-rg"
}

variable "storage_account_name" {
  type        = string
  description = "Dedicated WORM storage account name (globally unique)."
  default     = "strataaudit"
}

variable "container_name" {
  type        = string
  description = "Blob container that holds the immutable JSON audit records."
  default     = "audit-records"
}

variable "retention_days" {
  # AUTHORITATIVE retention value. Provisioned UNLOCKED (draft); locked manually only after legal
  # sign-off (see runbook). This is the single source of truth for 730 — no CI variable duplicates it.
  type        = number
  description = "Immutability (WORM) retention period in days."
  default     = 730
}

variable "tags" {
  type        = map(string)
  description = "Tags applied to the audit-store resources."
  default     = {}
}
