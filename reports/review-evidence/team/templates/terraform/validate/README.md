# `terraform/validate`

Runs `terraform fmt -check`, `terraform init -backend=false`, and `terraform validate` as one
reusable, versioned job. No backend, no credentials — safe to run on any merge request without
state access. Full backend initialization happens later, in the `terraform/plan` stage.

Pipeline position: **validate** → plan → policy gate → apply → notify

## Usage

```yaml
include:
  - component: $CI_SERVER_FQDN/kaas/pipelines/components/terraform/validate@0.1.0
    inputs:
      job_name: tf-validate
      tf_root: terraform/
```

Include it more than once with distinct `job_name` values to validate multiple roots in one pipeline:

```yaml
include:
  - component: $CI_SERVER_FQDN/kaas/pipelines/components/terraform/validate@0.1.0
    inputs:
      job_name: validate-network
      tf_root: terraform/network
  - component: $CI_SERVER_FQDN/kaas/pipelines/components/terraform/validate@0.1.0
    inputs:
      job_name: validate-identity
      tf_root: terraform/identity
```

## Inputs

| Input | Type | Required | Default | Description |
|---|---|---|---|---|
| `job_name` | string | no | `tf-validate` | CI job name. Set a unique value to include this component more than once and produce distinct jobs. |
| `stage` | string | no | `validate` | Pipeline stage the job runs in. |
| `tf_root` | string | no | `.` | Path to the Terraform root to validate, relative to the repo root. |
| `fail_on_fmt` | string | no | `"true"` | Fail the job on `fmt -check` violations. Set `"false"` for non-blocking. |
| `terraform_image` | string | no | `registry.web.boeing.com/amp/docker-images/terraform/terraform-azure/ubi8minimal-azterraform/v1.9.2` | Boeing-internal Terraform CLI image (no public pulls). |
| `terraform_version` | string | no | `26.04.15` | Tag of the Terraform image. Consumers should override to pin their own version; the default is provided for the initial release only. |

## Behavior

- `terraform fmt -check -recursive -diff` — when `fail_on_fmt` is `"true"` (default), any
  mis-formatted file fails the job. When `"false"`, formatting issues are reported but
  non-blocking.
- `terraform init -backend=false` — initializes providers/modules without a backend, so the job
  needs no Azure (or other) state credentials.
- `terraform validate` — validates configuration correctness against the initialized providers.

Story: STR-215. Epic: Infrastructure Pipeline (IaC Automation and GitOps Provisioning).
