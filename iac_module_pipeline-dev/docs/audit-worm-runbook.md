# WORM Audit Store — Operations Runbook

Manual prerequisites, provisioning, legal-gated lock, verification, and query usage for the
immutable (write-once, read-many) infrastructure-change audit store. Covers the steps that cannot
live in code. Story: amends S010 (tamper-proof record of every infrastructure change) under
FedRAMP High / DoD SRG IL4-5.

> Scope note: this story does **not** modify `template-workflow/.iac_module_template.yml`. The
> STR_230 TEMP TEST SCAFFOLDING exists only in the user's main working tree; it is **not** present
> in this worktree and this story does not touch the template file.

---

## 1. Prerequisites

- Provision (or confirm) the pipeline runner's identity — today a per-environment Service Principal;
  a **managed identity** in the target environment — and grant it **Storage Blob Data Contributor**
  on the `strataaudit` storage account (RBAC data-plane role). Uploads use
  `az storage blob upload --auth-mode login`, which reuses the job's already-authenticated `az`
  session; no second login and no account keys are involved.
- Confirm the runner image (`TERRAFORM_IMAGE`) provides `az`, `terraform`, `jq`, `sha256sum`,
  `curl`, and a `date` supporting `-u`/ISO-8601.
- Confirm `AZ_LOGIN_CSP_TYPE=AzureUSGovernment` in `variables/.variables.yml` so the `az` session
  targets the Gov cloud. This is the authoritative cloud selector; the previously referenced
  (undefined) `AZ_CSP_TYPE` has been removed from the jobs.

## 2. Provision the store

The audit store is a standalone Terraform root applied **out-of-band** (not by consumer pipelines):

```bash
cd iac/audit-store
cp backend.hcl.example backend.hcl           # edit: point at a NON-WORM state location
cp terraform.tfvars.example terraform.tfvars

terraform init -backend-config=backend.hcl
terraform plan
terraform apply
```

Confirm the policy is provisioned **unlocked (draft)**:

```bash
terraform output immutability_locked   # expect: false
terraform output retention_days        # expect: 730
```

The audit stack's **own** tfstate must live in a **non-WORM** location (the `backend.hcl.example`
comment explains this): Terraform rewrites its state blob on every apply and a locked immutable
container would reject those rewrites.

## 3. Legal sign-off gate

Obtain written legal confirmation of the exact retention period (expected **730 days**) **before**
locking. Until legal confirms, leave the policy **unlocked**. The lock is irreversible.

## 4. Manual lock step (post sign-off — IRREVERSIBLE)

Do **not** lock from Terraform (there is intentionally no variable to flip it). Lock manually:

```bash
# Retrieve the current policy etag:
az storage container immutability-policy show \
  --account-name strataaudit --container-name audit-records --auth-mode login

# Lock it (irreversible):
az storage container immutability-policy lock \
  --account-name strataaudit --container-name audit-records \
  --if-match <etag> --auth-mode login
```

**Once locked, the retention period cannot be shortened and records cannot be modified or deleted
for 730 days — not even by an administrator.**

## 5. Verify tamper-proofing

```bash
export AUDIT_STORAGE_ACCOUNT=strataaudit
export AUDIT_CONTAINER=audit-records
scripts/audit/verify_immutability.sh
```

The script attempts an overwrite and a delete of an existing record and asserts both are rejected
with an Azure immutability error. It **only truly PASSES against the LOCKED store** (step 4). Run
against the unlocked/draft store it will correctly report **FAIL / not-yet-immutable**, which is
expected before the lock.

## 6. Query usage

```bash
export AUDIT_STORAGE_ACCOUNT=strataaudit
export AUDIT_CONTAINER=audit-records

scripts/audit/query_audit.sh --help
scripts/audit/query_audit.sh --environment dev
scripts/audit/query_audit.sh --environment dev --module my-module
scripts/audit/query_audit.sh --from 2025-01-01 --to 2025-03-31
scripts/audit/query_audit.sh --actor jdoe
scripts/audit/query_audit.sh --environment uat --download ./audit-export
```

The query tool sanitizes `--environment`/`--module` with the **identical** rule the writer uses
(`[A-Za-z0-9._-]`, any other character → `-`) so sanitized record paths are still matched.

## 7. Retry / collision semantics

Blob names include `CI_JOB_ID`
(`<env>/<module>/<timestamp>-<pipeline_id>-<job_id>.json`), so a retried apply reuses the pipeline
ID but gets a new job ID and writes a **new** blob per attempt rather than overwriting a prior
(locked, immutable) one. Each attempt's outcome is preserved; against a locked store a write to a
new path always succeeds (write-once).

## 8. Script delivery and the one known gap

The apply job fetches `scripts/audit/*.sh` from this template project's raw endpoint
(`AUDIT_SCRIPTS_BASE_URL`, pinned to the consumer's include `ref`) into `/tmp/scripts/audit` at
runtime, then arms the audit `trap`. **Known gap:** if that `curl` fetch fails **before** the trap
is armed (a pre-Terraform failure — nothing has been planned or applied yet), **no audit record is
written for that run**, and the apply job fails early. Mitigation: bake `scripts/audit/*.sh` into
`TERRAFORM_IMAGE` under `/tmp/scripts/audit` so the scripts are always present and the trap is
always armable. Once the trap is armed, every subsequent failure (init, plan, apply) produces a
record, and the builder's own failure is swallowed with a `[WARN]` so audit tooling never changes
the apply's exit code.

## 9. RBAC troubleshooting

An `AuthorizationPermissionMismatch` / "unauthorized" error on upload or list means the runner
identity lacks **Storage Blob Data Contributor** on `strataaudit`. Grant the role and allow for RBAC
propagation (can take several minutes). `--auth-mode login` requires a data-plane RBAC role; the
account has `shared_access_key_enabled = false`, so account keys are not an option.

## 10. Retention separation

- **Pipeline artifacts** (plan/apply output) expire in **90 days** — operational convenience.
- **WORM audit store** retains **730 days** — the compliance record of truth.

These are independent. The 730-day value is the single authoritative source in the audit-store
Terraform `retention_days` variable; it is deliberately **not** duplicated as a CI variable.

## 11. plan_hash vs applied_plan_hash

- `plan_hash` — SHA-256 of the **reviewed** plan rendered in the init stage, handed to the apply
  job via a `reports:dotenv` artifact.
- `applied_plan_hash` — SHA-256 of the plan the apply job actually re-plans and applies (computed in
  the apply job itself, independent of the dotenv hand-off).

A mismatch is **logged and recorded, not failed** — this story records drift for after-the-fact
auditability; enforcing a pre-apply gate is out of scope. If the init-stage hand-off is missing or
empty, the record is still written with `plan_hash:""` plus a grep-able
`[AUDIT-WARN] plan_hash empty …` log marker (never a fabricated value); `applied_plan_hash` remains
populated as an integrity anchor. Therefore the "non-empty `plan_hash`" acceptance criterion is only
fully satisfiable when the init-stage plan succeeds and its dotenv propagates to the apply stage.

## 12. Pending S010 reconciliation

Four record fields are marked **pending S010 reconciliation** — their exact names/semantics await
confirmation against the authoritative S010 field list and may be renamed in a follow-up:

- `pipeline_id`
- `pipeline_url`
- `terraform_version`
- `schema_version`
