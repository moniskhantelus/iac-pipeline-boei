# `compliance-gates/audit-record`

Writes a tamper-proof, structured audit record to an **immutable (WORM) Azure blob store** after
**every** `terraform apply` — success **or** failure — using Managed Identity (no static
credentials). This is the compliance record of truth for "who changed what, when, and what
happened" under FedRAMP High. (STR-230.)

The GitLab artifact copy is for operational convenience (90 days); the WORM store is the durable,
non-deletable record with its own retention policy.

```yaml
include:
  - component: $CI_SERVER_FQDN/kaas/pipelines/components/compliance-gates/audit-record@<version>
    inputs:
      job_name: audit-record
      environment: prod
      module: network
      apply_job: tf-apply          # the terraform/apply job whose outcome is recorded
      plan_job: tf-plan            # the terraform/plan job that produced plan.tfplan.sha256
      tf_root: environments/prod
      audit_storage_account: $AUDIT_STORAGE_ACCOUNT   # WORM account name (see "Dependencies")
```

Place `audit-record` **after** `tf-apply` in the `needs:`/stage order. Because it runs with
`when: always`, it records failed applies too.

## Inputs

| Input | Required | Default | Description |
|---|---|---|---|
| `job_name` | no | `audit-record` | Job name. |
| `stage` | no | `apply` | Stage (place after apply). |
| `environment` | **yes** | — | Environment the apply acted on (query dimension). |
| `module` | **yes** | — | Module / Terraform root the change applied to (query dimension). |
| `apply_job` | no | `tf-apply` | Apply job whose outcome + `apply.log` is recorded. |
| `plan_job` | no | `tf-plan` | Plan job that produced `plan.tfplan.sha256` (the plan hash). |
| `tf_root` | no | `.` | Path where plan/apply wrote their artifacts. |
| `audit_storage_account` | no | `$AUDIT_STORAGE_ACCOUNT` | WORM storage account **name** (never a secret). |
| `audit_container` | no | `audit` | Immutable blob container. |
| `arm_environment` | no | `AzureUSGovernment` | az CLI cloud. |

## The record (11 fields)

Written as `<env>/<module>/<YYYY/MM/DD>/audit-<env>-<pipeline>-<job>.json`:

`actor`, `commit_sha`, `plan_hash`, `timestamp` (UTC ISO-8601), `environment`, `module`,
`outcome` (`success`|`failure`|`unknown`), `pipeline_id`, `job_id`, `project_path`, `mr_ref`.

The job fails closed if the record does not have exactly 11 fields or if the immutable write fails.

## Compliance query tool

`query_audit.py` searches the store for a compliance reviewer:

```bash
# From the immutable store (Managed Identity):
query_audit.py --account $AUDIT_STORAGE_ACCOUNT --container audit --environment prod --format table
query_audit.py --account $AUDIT_STORAGE_ACCOUNT --module network --from 2026-10-01 --to 2026-10-31
query_audit.py --account $AUDIT_STORAGE_ACCOUNT --actor jdoe

# Offline, against downloaded pipeline artifacts or a local export:
query_audit.py --source local --path ./audit --environment prod --outcome failure
```

Filters: `--environment`, `--module`, `--actor`, `--outcome`, `--from`/`--to`. Formats: `json`, `table`.

## Dependencies (out of scope for this component)

- **WORM storage account** — a dedicated storage account in the **shared-services** environment,
  **separate from Terraform state storage**, with an immutability (WORM) policy. Provisioned in the
  **repo/module plane** (a Terraform module, like the backend-state account), not by this pipeline
  component. The policy is created in **draft/unlocked** state and **locked to 730 days only after
  legal confirmation** of the retention period. This component consumes the account by name.
- **Managed Identity** — the runner's UAMI needs `Storage Blob Data Contributor` on the audit
  container to upload (append/create only; immutability prevents modification/deletion).
- **Plan hash** — produced by `terraform/plan` as `plan.tfplan.sha256`.

## Tamper-proof verification (acceptance test)

With the WORM policy locked, attempting to delete or overwrite a committed record is rejected by
Azure with an immutability error — confirm as an acceptance test in a real environment (cannot run
hermetically in CI). The self-test (`tests/compliance-gates/audit-record-test.yml`) asserts the
component contract statically and exercises the query tool against fixtures.

Story: STR-230. Traceability: PRD compliance/audit requirements; Blueprint BP-6 (audit logging).
