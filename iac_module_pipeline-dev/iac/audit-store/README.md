# Audit Store (WORM) — Terraform

Standalone Terraform root that provisions the immutable (write-once, read-many) audit store for
infrastructure-change records under FedRAMP High / DoD SRG IL4-5. It is **applied out-of-band** by a
platform operator — **not** by consumer pipelines.

## What it provisions

- Resource group `kaas-shared-audit-rg` (separate from the Terraform state RG).
- Storage account `strataaudit` (AAD/RBAC only — no account keys; private network access; GRS).
- Blob container `audit-records`.
- A **container-level time-based immutability policy**, `immutability_period_in_days = 730`,
  provisioned **UNLOCKED (draft)**. There is **no variable to lock it** — locking is a deliberate
  manual step performed only after legal sign-off (see the runbook).

## Prerequisites

- `terraform >= 1.6.0`, provider `azurerm ~> 4.80`.
- Authenticated `az` session targeting **AzureUSGovernment** with rights to create the RG, storage
  account, and container.
- A **non-WORM** state location for this stack's own tfstate (see `backend.hcl.example`).

## Usage

```bash
cd iac/audit-store
cp backend.hcl.example backend.hcl                 # edit: point at a NON-WORM state location
cp terraform.tfvars.example terraform.tfvars       # adjust names/region if needed

terraform init -backend-config=backend.hcl
terraform plan
terraform apply
```

After apply, confirm the policy is **unlocked**:

```bash
terraform output immutability_locked    # expect: false
terraform output retention_days         # expect: 730
```

## Locking (manual, irreversible — post legal sign-off)

Do **not** lock from Terraform. Lock manually only after legal confirms the retention period. See
`docs/audit-worm-runbook.md` for the exact `az storage container immutability-policy lock` command
and the tamper-proof verification step.

## Provider-version note

The immutability-policy resource is wired with the preferred azurerm 4.x attribute
`storage_container_resource_manager_id`. If a specific `azurerm ~> 4.80.x` minor rejects it, the
legacy fallback is the explicit pair `storage_account_name` + `container_name` (every other
attribute unchanged). Never drop the immutability policy to make `terraform validate` pass.
