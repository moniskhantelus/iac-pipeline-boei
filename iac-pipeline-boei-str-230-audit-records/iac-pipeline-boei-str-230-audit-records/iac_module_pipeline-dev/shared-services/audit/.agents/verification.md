# Verification — audit/main.tf hardening

Date: first iteration. Host: Windows, pwsh. Terraform v1.9.2, azurerm v4.80.0 (pinned by existing `.terraform.lock.hcl`).

## Changes made (main.tf only)

FIX 1 — REQ-INT-26 (private endpoint + no public access):
- `azurerm_storage_account.audit`: added `public_network_access_enabled = false` with a comment that the existing `network_rules` VNet block is now a belt-and-suspenders secondary control.
- New variable `private_endpoint_subnet_id` (type string).
- New variable `private_dns_zone_ids` (type list(string), default []).
- New resource `azurerm_private_endpoint.audit`: name `"${var.storage_account_name}-blob-pe"`, in the audit RG + location, `subnet_id = var.private_endpoint_subnet_id`, `private_service_connection` targeting `azurerm_storage_account.audit.id` with `subresource_names = ["blob"]` and `is_manual_connection = false`; `dynamic "private_dns_zone_group"` wired only when `private_dns_zone_ids` is non-empty; `lifecycle { prevent_destroy = true }`.
- New output `private_endpoint_id = azurerm_private_endpoint.audit.id`.

FIX 2 — set-based separation check:
- New variable `state_storage_account_names` (type list(string), default []). Existing `state_storage_account_name` retained for backward compatibility.
- Precondition rewritten to assert audit name (lowercased) `!=` single `state_storage_account_name` (lowercased) AND not a member of `[for s in var.state_storage_account_names : lower(s)]` via `contains()`. Same error_message. Passes with the default empty list (single-name check only).

Not touched (per constraints): `locked = false`, 730-day retention, role definition/assignments, container name "audit", all `prevent_destroy` settings, the precondition's intent.

## Command output (verbatim)

### terraform version
```
Terraform v1.9.2
on windows_amd64
+ provider registry.terraform.io/hashicorp/azurerm v4.80.0
```

### terraform fmt  (PASS — reformatted nothing after apply; fmt -check clean, exit 0)
```
---FMT---
---FMT-CHECK---
(exit code 0, no files listed)
```

### terraform init -backend=false  (PASS)
```
Initializing provider plugins...
- Reusing previous version of hashicorp/azurerm from the dependency lock file
- Installing hashicorp/azurerm v4.80.0...
- Installed hashicorp/azurerm v4.80.0 (signed by HashiCorp)
Terraform has made some changes to the provider dependency selections recorded
in the .terraform.lock.hcl file. ...
Terraform has been successfully initialized!
```
Note: init added hash entries to `.terraform.lock.hcl` but the pinned version remains `4.80.0` with constraint `~> 4.80.0` — unchanged. Provider mirror was reachable; nothing had to be skipped offline.

### terraform validate  (PASS)
```
Success! The configuration is valid.
```

## Could not be verified offline
- Nothing material. `terraform plan`/`apply` and live Azure were intentionally not run (no credentials, per instructions). Attribute names for `azurerm_private_endpoint` (incl. `private_service_connection`, `private_dns_zone_group`, `private_connection_resource_id`, `subresource_names`, `is_manual_connection`) and `public_network_access_enabled` on `azurerm_storage_account` were confirmed valid by `terraform validate` against azurerm 4.80.0.

## Manual values the deploying environment must now supply
- `private_endpoint_subnet_id` (REQUIRED, string) — subnet for the private endpoint NIC.
- `private_dns_zone_ids` (optional, list(string)) — blob private DNS zone `privatelink.blob.core.usgovcloudapi.net` for Azure Gov; omit if DNS is managed centrally.
- `state_storage_account_names` (optional, list(string)) — additional state account names to enforce separation against.

## Cleanup
`.terraform/` removed. Folder left with only `main.tf` and the existing `.terraform.lock.hcl`.
