# `terraform/drift`

Schedule-only drift detection. Runs `terraform plan -detailed-exitcode`; on exit code 2 (drift) it
writes `drift-report.txt` and posts an ops alert. Never auto-applies.

```yaml
# In the consumer repo, create a 4-hour pipeline SCHEDULE per environment.
include:
  - component: $CI_SERVER_FQDN/kaas/pipelines/components/terraform/drift@0.1.0
    inputs:
      job_name: tf-drift
      environment: dev
      tf_root: examples/basic
```

| Input | Required | Default | Description |
|---|---|---|---|
| `environment` | **yes** | — | Environment to check. |
| `tf_root` | no | `.` | Terraform root. |
| `alert_webhook` | no | `$DRIFT_ALERT_WEBHOOK` | Protected CI var holding the Teams/Slack webhook. |

Story: `E01-S08` Part B (GAP-003).
