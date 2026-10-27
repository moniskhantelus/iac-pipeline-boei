# `terraform/apply`

Applies **only** the saved, SHA-256-verified plan from `terraform/plan`. No `-auto-approve`, no
`-var-file`, no re-plan. Managed Identity auth; refuses `ARM_CLIENT_SECRET`.

```yaml
include:
  - component: $CI_SERVER_FQDN/kaas/pipelines/components/terraform/apply@0.1.0
    inputs:
      job_name: tf-apply
      environment: dev
      tf_root: examples/basic
      plan_job: tf-plan
```

| Input | Required | Default | Description |
|---|---|---|---|
| `job_name` | no | `tf-apply` | Job name. |
| `stage` | no | `apply` | Stage. |
| `environment` | **yes** | — | State key + GitLab environment. |
| `tf_root` | **yes** | — | Terraform root to apply. |
| `plan_job` | no | `tf-plan` | Plan job whose artifact is applied. |
| `arm_environment` | no | `AzureUSGovernment` | azurerm cloud. |

Place `tf-apply` **after** `compliance-gates/terraform-gate` in the consumer `needs:` chain. Story: `E01-S01`
(closes GAP-015/006). Jira: STR-220.
