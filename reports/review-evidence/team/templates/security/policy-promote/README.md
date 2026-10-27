# `security/policy-promote`

Promotes a policy through the Dev → Audit → Enforce lifecycle by raising a GitOps MR that flips the
policy action in the target overlay. No direct cluster write.

```yaml
- component: $CI_SERVER_FQDN/kaas/pipelines/components/security/policy-promote@0.1.0
  inputs:
    job_name: promote-require-resources
    policy_name: require-resources
    target_env: staging
    action: Enforce
```

| Input | Required | Default | Description |
|---|---|---|---|
| `policy_name` | **yes** | — | ClusterPolicy/constraint name. |
| `target_env` | **yes** | — | Overlay to update. |
| `action` | **yes** | — | `Audit` or `Enforce`. |
| `gitops_repo` | no | `kaas/platform/platform-gitops` | GitOps repo. |
| `dry_run` | no | `false` | Self-test mode. |

Requires `GITOPS_DEPLOY_KEY`. Story: `E07-S03`.
