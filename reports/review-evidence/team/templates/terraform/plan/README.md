# `terraform/plan`

MSI-authenticated `terraform plan` that produces `plan.tfplan` (binary), `plan.tfplan.json`
(for the policy gate), and `plan.tfplan.sha256` (for `terraform/apply` integrity verification).

```yaml
include:
  - component: $CI_SERVER_FQDN/kaas/pipelines/components/terraform/plan@0.1.0
    inputs:
      job_name: tf-plan
      environment: dev
      tf_root: examples/basic
      var_file: terraform.tfvars
```

| Input | Required | Default | Description |
|---|---|---|---|
| `job_name` | no | `tf-plan` | Job name. |
| `stage` | no | `plan` | Stage. |
| `environment` | **yes** | — | Scopes state key + GitLab environment. |
| `tf_root` | no | `.` | Terraform root. |
| `backend` | no | `azurerm` | `azurerm` or `local` (self-test). |
| `var_file` | no | `` | Optional tfvars. |
| `arm_environment` | no | `AzureUSGovernment` | azurerm cloud. |

Consumer must commit `backend.<env>.hcl` (RG, storage account, container). The component overrides
only the state `key`. Story: `E01-S02`. Jira: STR-216.
