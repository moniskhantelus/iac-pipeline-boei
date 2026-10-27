# `compliance-gates/policy-gate`

Validates Kubernetes manifests (or a Terraform plan JSON) against the platform policy library,
in CI, using the same policies that run at admission. Engine-pluggable (Kyverno or conftest).

```yaml
# Validate manifests
- component: $CI_SERVER_FQDN/kaas/pipelines/components/compliance-gates/policy-gate@0.1.0
  inputs: { job_name: policy-manifests, manifest_dir: k8s, policy_ref: v1.0.0 }

# Validate a terraform plan JSON (IaC policy)
- component: $CI_SERVER_FQDN/kaas/pipelines/components/compliance-gates/policy-gate@0.1.0
  inputs: { job_name: policy-iac, input_type: tfplan, tfplan_json: examples/basic/plan.tfplan.json }
```

| Input | Required | Default | Description |
|---|---|---|---|
| `engine` | no | `kyverno` | `kyverno` or `conftest`. |
| `input_type` | no | `manifests` | `manifests` or `tfplan`. |
| `manifest_dir` | no | `k8s` | Manifest dir. |
| `tfplan_json` | no | `plan.tfplan.json` | Plan JSON path. |
| `policy_repo` | no | `kaas/platform/policy-library` | Policy library repo. |
| `policy_ref` | no | `v1.0.0` | Pinned policy version. |

Depends on the policy library repo (E07-S02). Story: `E07-S01`.
