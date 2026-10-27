# Known HIGH finding: public network access enabled on a storage account.
resource "azurerm_storage_account" "bad" {
  name                          = "kaasbadfixture"
  resource_group_name           = "rg-fixture"
  location                      = "usgovvirginia"
  account_tier                  = "Standard"
  account_replication_type      = "LRS"
  public_network_access_enabled = true # <-- Checkov flags this
}
