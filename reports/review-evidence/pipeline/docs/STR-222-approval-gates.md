# STR-222 — Environment-Specific Approval Gate

**Satisfied by consuming the official KaaS CI/CD component, not a hand-rolled gate.**

The KaaS platform ships a versioned, contract-tested approval gate in the components catalog
(`kaas/pipelines/components`). Per platform guidance, pipelines **reference the component**
rather than reinventing gate logic per repo.

## Component

`compliance-gates/terraform-gate@0.1.2`

Behavior (from the component):
- **sandbox / dev** → auto-approve
- **uat** → manual; requires ≥1 MR approval
- **prod** → manual; requires ≥2 MR approvals **and** a ServiceNow `CHG#######` in the MR description
- Fail-closed if the GitLab API is unreachable
- Full audit trail (`[AUDIT] gate_decision ...`)

## How it is wired here

`template-workflow/.iac_module_template.yml` includes the component (components use the
`component:` include syntax, included at the pipeline root):

```yaml
include:
  - component: $CI_SERVER_FQDN/kaas/pipelines/components/compliance-gates/terraform-gate@0.1.2
    inputs:
      job_name: iac_gates_job
      stage: iac_approval          # runs before iac_apply
      environment: $DEPLOY_ENV     # sandbox|dev|uat|prod
```

`$DEPLOY_ENV` is declared in `variables/.variables.yml` (empty default; set per run/project).

## Inputs (component)

| Input | Required | Default | Notes |
|---|---|---|---|
| `job_name` | no | `tf-gate` | Set to `iac_gates_job` here |
| `stage` | no | `approve` | Set to `iac_approval` (before apply) |
| `environment` | **yes** | — | Drives strictness; from `$DEPLOY_ENV` |
| `min_approvals_prod` | no | `2` | |
| `min_approvals_uat` | no | `1` | |
| `chg_pattern` | no | `CHG[0-9]{7}` | **OQ-02: confirm ServiceNow format with the process owner** |

## Prerequisites

- **MR Approval Rules** configured in the consumer project (so approvals are recorded).
- The gate uses the built-in `CI_JOB_TOKEN` to read approvals via the GitLab API.

## What was removed

The earlier hand-rolled gate (`scripts/approval_gate.py`, its unit tests, and the custom
`APPROVAL_GATE_*` / `SERVICENOW_CHANGE_PATTERN` CI variables) has been removed — it is
superseded by the shared component. `iac/.iac_gates_job.yml` is now a pointer/README only.

## Open item

- **OQ-02 / ServiceNow format:** the component defaults `chg_pattern` to `CHG[0-9]{7}`. A
  sample we were given was `INC8747347` (an Incident). Confirm whether prod gating requires a
  Change Request (`CHG`) or Incident (`INC`), then set `chg_pattern` accordingly.

Jira: STR-222 (E01-S04, GAP-016).
