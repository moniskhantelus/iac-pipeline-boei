# Review — audit/main.tf hardening (FedRAMP-High WORM audit store)

Scope: single file `shared-services/audit/main.tf`, azurerm ~> 4.80.0, AzureUSGovernment.
Two approved changes only. Verdict: **APPROVED** — no blocking findings.

## FIX 1 — REQ-INT-26 (private endpoint + no public access)

1. PASS — `azurerm_storage_account.audit` has `public_network_access_enabled = false`.
2. PASS — New `variable "private_endpoint_subnet_id" { type = string }`. Existing `runner_subnet_ids`
   variable unchanged; `network_rules` block unchanged and annotated as a belt-and-suspenders
   secondary control.
3. PASS — `azurerm_private_endpoint.audit`:
   - `resource_group_name = azurerm_resource_group.audit.name`, `location = ...audit.location` (audit RG + location).
   - `subnet_id = var.private_endpoint_subnet_id`.
   - `private_service_connection` with `private_connection_resource_id = azurerm_storage_account.audit.id`,
     `subresource_names = ["blob"]`, `is_manual_connection = false`.
   - Deterministic name `"${var.storage_account_name}-blob-pe"`.
   - `lifecycle { prevent_destroy = true }`.
4. PASS — New `variable "private_dns_zone_ids" { type = list(string); default = [] }`.
   `private_dns_zone_group` wired via `dynamic` block with
   `for_each = length(var.private_dns_zone_ids) > 0 ? [1] : []`, so it omits cleanly on the empty default.
   Comment notes the Gov blob zone `privatelink.blob.core.usgovcloudapi.net` must be supplied by the
   deploying environment.
5. PASS — `output "private_endpoint_id" { value = azurerm_private_endpoint.audit.id }` present.

## FIX 2 — strengthen separation precondition

1. PASS — New `variable "state_storage_account_names" { type = list(string); default = [] }`;
   existing `state_storage_account_name` retained.
2. PASS — Precondition:
   `lower(var.storage_account_name) != lower(var.state_storage_account_name) && !contains([for s in var.state_storage_account_names : lower(s)], lower(var.storage_account_name))`.
   Same `error_message` intent ("Audit storage must be separate from Terraform state storage.").
   With the default empty list, `contains([], ...)` is `false` and its negation `true`, so the check
   still passes (reduces to the single-name comparison). Correct.

## Constraints

- PASS — `locked = false`, `immutability_period_in_days = 730`, role definition/assignments,
  container name `"audit"`, and all `prevent_destroy` settings are unchanged.
- PASS — Attribute names are valid for azurerm ~> 4.80.0
  (`public_network_access_enabled`, `azurerm_private_endpoint`, `private_service_connection`,
  `private_connection_resource_id`, `subresource_names`, `is_manual_connection`,
  `private_dns_zone_group` / `private_dns_zone_ids`).
- PASS — Change confined to `main.tf` plus the `.agents/` note. The audit module tree is an untracked
  (newly extracted) directory; the `D` entries in git status belong to the separate `iac_module_pipeline\`
  git repo and are pre-existing extraction state, not writes made by this edit.

## Verification evidence (from .agents/verification.md)

- Terraform v1.9.2, azurerm v4.80.0 pinned by existing lock file.
- `terraform fmt -check` clean (exit 0).
- `terraform init -backend=false` succeeded; lock remains `4.80.0` / `~> 4.80.0`.
- `terraform validate` → "Success! The configuration is valid."
- `plan`/`apply` intentionally skipped (no credentials) — documented, acceptable.

Required verification is present and passing. No reachable correctness, security, or data-integrity
blocker identified.
