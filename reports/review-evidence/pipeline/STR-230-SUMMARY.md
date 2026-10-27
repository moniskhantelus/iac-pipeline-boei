# STR-230 — Tamper-Proof Record of Every Infrastructure Change

**Approach: consume the official KaaS component for the pipeline logic; provision the WORM
store ourselves (the one piece the component does not provide).**

Per platform guidance, the audit-record pipeline logic is satisfied by referencing the
published component `compliance-gates/audit-record@0.1.2` from `kaas/pipelines/components`
rather than hand-rolling a runtime. The WORM storage account the component writes to is a
dependency the component explicitly leaves to the "repo/module plane" — so we keep providing
it as Terraform.

## Two parts

### 1. Audit-record pipeline logic → the component (replaces our custom runtime)
- `template-workflow/.iac_module_template.yml` includes
  `compliance-gates/audit-record@0.1.2` with inputs: `environment=$DEPLOY_ENV`,
  `module=$CI_PROJECT_NAME`, `apply_job=iac_apply_job`, `plan_job=iac_init_job`, `tf_root=.`,
  `audit_storage_account=$AUDIT_STORAGE_ACCOUNT`.
- The component writes the immutable 11-field record after every apply (success OR failure,
  `when: always`) via Managed Identity, and ships its own `query_audit.py` + contract test.
- **Removed (superseded):** `scripts/audit.py`, `iac/.audit_runtime.yml`, `tests/test_audit.py`,
  and the custom `AUDIT_USE_MANAGED_IDENTITY`/upload wiring.

### 2. WORM storage account → we still provide it (component dependency)
- `shared-services/audit/` (split layout: `provider.tf`, `variables.tf`, `main.tf`,
  `outputs.tf`, `backend.hcl.example`, `terraform.tfvars.example`) provisions the dedicated
  WORM storage account, separate from Terraform state, with a 730-day immutability policy
  left **unlocked/draft** (locked manually only after legal sign-off). The component consumes
  this account by name via `$AUDIT_STORAGE_ACCOUNT`.

## Pipeline wiring for the component's inputs
- `iac/.iac_tf_init.yml` now also emits `plan.tfplan.sha256` at the repo root (the plan hash
  the component reads).
- `iac/.iac_tf_apply.yml` now runs a real apply and writes `apply.log` at the repo root (the
  component derives the outcome from it), preserving the real apply exit code; `when: always`.

## Prerequisites / open items
- **WORM storage account** provisioned (shared-services/audit) and locked to 730 days after
  legal sign-off.
- **Managed Identity** with `Storage Blob Data Contributor` on the audit container.
- **Component version**: pinned `@0.1.2` (latest published); confirm the published
  version with the platform team (the audit-record README showed `@<version>`).
- Record field set is the component's 11 fields (`actor, commit_sha, plan_hash, timestamp,
  environment, module, outcome, pipeline_id, job_id, project_path, mr_ref`).

Jira: STR-230.
