> SUPERSEDED: see FIXES-AND-DEPLOYMENT.md for the corrected implementation and remaining acceptance steps.

# STR-222 Implementation Summary — Environment-Specific Approval Gate

**Approach: consume the official KaaS component, not a custom gate.**

Per platform guidance, STR-222 is satisfied by referencing the published, versioned,
contract-tested component `compliance-gates/terraform-gate@0.1.2` from
`kaas/pipelines/components` — the paved road — instead of hand-rolling gate logic.

## What the pipeline does now

- `template-workflow/.iac_module_template.yml` includes the component via `component:`
  syntax, wiring `job_name: iac_gates_job`, `stage: iac_approval` (before apply), and
  `environment: $DEPLOY_ENV`.
- `variables/.variables.yml` declares `DEPLOY_ENV` (set per run/project).
- `iac/.iac_gates_job.yml` is now a pointer/README documenting the component usage.

## Gate behavior (provided by the component)

- sandbox/dev → auto-approve
- uat → ≥1 MR approval
- prod → ≥2 MR approvals + ServiceNow `CHG#######` in the MR description
- fail-closed on API errors; full audit trail

## Removed (superseded by the component)

- `scripts/approval_gate.py` (hand-rolled gate)
- `tests/test_approval_gate.py` (its unit tests — the component ships its own contract test)
- Custom `APPROVAL_GATE_*` and `SERVICENOW_CHANGE_PATTERN` CI variables

## Prerequisites / open items

- Consumer project must have **MR Approval Rules** configured.
- The component uses `CI_JOB_TOKEN` for the approvals API.
- **OQ-02 (ServiceNow format):** component default `chg_pattern` is `CHG[0-9]{7}`. Confirm
  whether prod requires a Change Request (`CHG`) or the `INC` sample we were shown, then set
  the `chg_pattern` input accordingly.

Jira: STR-222 (E01-S04, GAP-016).
