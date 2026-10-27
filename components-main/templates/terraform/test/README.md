# `terraform/test`

Python-driven Terraform exercise + plan-JSON assertions. A **bridge to Terratest**: runs
`fmt/init/validate/plan`, then evaluates a declarative `tftest.yaml` against `terraform show -json`.
Default `plan` mode needs **no** Azure credentials and is safe on every MR.

```yaml
- component: $CI_SERVER_FQDN/kaas/pipelines/components/terraform/test@0.1.0
  inputs:
    job_name: tf-test
    tf_root: examples/basic
    spec_file: tftest.yaml
```

| Input | Required | Default | Description |
|---|---|---|---|
| `tf_root` | no | `.` | Terraform root under test. |
| `spec_file` | no | `tftest.yaml` | Assertion spec, relative to `tf_root`. |
| `mode` | no | `plan` | `plan` only. Provision and destroy through the audited components. |
| `environment` | no | `test` | Retained for compatibility; test job does not provision or destroy. |
| `terraform_image` / `_version` | no | internal azterraform | Image bundling Terraform + Python 3. |

## `tftest.yaml` schema (version 1)

```yaml
version: 1
plan:
  var_file: terraform.tfvars        # optional
  vars: { environment: dev }        # optional inline -var
assertions:
  resources_present: [azurerm_resource_group.example]
  resource_counts:
    azurerm_resource_group: { min: 1 }      # or { exact: 1 }
  required_tags: [environment, managed-by, cost-center, application-id, platform]
  forbidden_types: [azurerm_public_ip]
  attribute_equals:
    - resource: azurerm_resource_group.example
      path: location                 # dotted path into the resource's planned "values"
      allowed: [usgovvirginia, usgovtexas]
      # denied: [...]                 # optional
  outputs_present: [fixture_id]
```

Each assertion becomes one JUnit testcase (`reports/tftest-junit.xml`), so failures show per-check in
the MR. A machine-readable `reports/tftest-report.json` is also produced.

## How the runner is sourced

The component template fetches its **pinned** `tf_test.py` from the `components` repo at
`$[[ component.sha ]]` (the exact revision of the component version you included), so the runner
always matches the component version — self-contained and reproducible. (A consumer can override by
committing their own `tf_test.py`, but that is discouraged.)

> `TODO(pair)`: confirm the component image has `python3`; the azterraform image is Terraform-first.
> If Python 3 is absent, pin a combined Terraform+Python image or add a `pip`-free python layer.

## Terratest migration

`tftest.yaml` maps 1:1 to Terratest: `resources_present`/`resource_counts` → plan-struct resource
checks; `attribute_equals` → resource attribute asserts; `outputs_present` → `OutputRequired`. Keep
`tftest.yaml` as the source of truth and port the Go asserts from it when Terratest lands.

Story: `epic-01-infrastructure-pipeline/E01-S10`.
