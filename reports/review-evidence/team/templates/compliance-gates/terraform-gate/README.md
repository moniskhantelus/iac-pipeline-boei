# `compliance-gates/terraform-gate`

Environment-aware approval gate. `sandbox`/`dev` auto-pass; `uat` requires ≥1 MR approval; `prod`
requires ≥2 approvals **and** a ServiceNow `CHG#######` in the MR description. Fails closed if the
GitLab API is unreachable.

```yaml
include:
  - component: $CI_SERVER_FQDN/kaas/pipelines/components/compliance-gates/terraform-gate@0.1.0
    inputs:
      job_name: tf-gate
      environment: $DEPLOY_ENV
```

| Input | Required | Default | Description |
|---|---|---|---|
| `job_name` | no | `tf-gate` | Job name. |
| `stage` | no | `approve` | Must sit before the apply stage. |
| `environment` | **yes** | — | Drives strictness. |
| `min_approvals_prod` | no | `2` | Prod approval count. |
| `min_approvals_uat` | no | `1` | UAT approval count. |
| `chg_pattern` | no | `CHG[0-9]{7}` | ServiceNow CHG regex. TODO(pair): confirm format (OQ-02). |

Requires MR Approval Rules configured in the consumer project. Story: `E01-S04` (GAP-016). Jira: STR-222.
