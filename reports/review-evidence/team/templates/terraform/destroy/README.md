# `terraform/destroy`

Guarded teardown of a Terraform-managed environment. Destruction runs **only** when
`destroy_enabled: "true"`; otherwise the job is a no-op and `terraform destroy` never runs.
Persistent environments (`uat`, `prod` by default) additionally require a typed `confirm_destroy`
token matching the environment name **and** a manual run. Managed Identity auth; refuses
`ARM_CLIENT_SECRET`. What is destroyed is what was reviewed — the job saves a `-destroy` plan,
renders it, then applies that saved plan.

```yaml
include:
  - component: $CI_SERVER_FQDN/kaas/pipelines/components/terraform/destroy@0.1.0
    inputs:
      job_name: tf-destroy
      environment: dev
      tf_root: examples/basic
      destroy_enabled: "true"      # master switch — default "false" (no-op)
```

For a persistent environment, also pass a matching confirmation (via a protected/manual variable):

```yaml
      environment: prod
      destroy_enabled: "true"
      confirm_destroy: "prod"      # must equal the environment name
```

| Input | Required | Default | Description |
|---|---|---|---|
| `job_name` | no | `tf-destroy` | Job name. |
| `stage` | no | `destroy` | Stage. |
| `environment` | **yes** | — | State key + GitLab environment + gate strictness. |
| `tf_root` | **yes** | — | Terraform root to destroy. |
| `destroy_enabled` | no | `"false"` | **Master switch.** Destroy runs only when `"true"`; any other value is a no-op. |
| `persistent_environments` | no | `uat prod` | Env-name prefixes requiring typed confirmation + manual run. |
| `confirm_destroy` | no | `""` | For persistent envs: must equal `environment` to authorize. Never default this in the repo. |
| `tf_root_lock_timeout` | no | `300s` | State lock timeout. |
| `arm_environment` | no | `AzureUSGovernment` | azurerm cloud. |

**Authorization model (STR-299 Rec 2 / Appendix C A3):**
- **Disabled by default** — `destroy_enabled` must be explicitly `"true"`; otherwise no destroy
  command runs.
- **Disposable** (`sandbox`/`dev`/`test`) — runs on the branch once enabled; safe cleanup after a
  failed deploy/test.
- **Persistent** (`uat`/`prod`) — `when: manual` **and** a `confirm_destroy` token matching the env
  name; mismatch or empty ⇒ `exit 1`.

Story: STR-299 (closes the destruction-control gap — no guarded destroy component existed). Pair
with `compliance-gates/terraform-gate` for the approval decision before this job.
