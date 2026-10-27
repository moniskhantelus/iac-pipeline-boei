# `compliance-gates/change-control-gate`

Classifies a GitOps-repo MR from the paths it touches (Standard / Normal / High-risk) and enforces
the matching approval count; High-risk also requires a ServiceNow CHG reference. Fails closed.

```yaml
- component: $CI_SERVER_FQDN/kaas/pipelines/components/compliance-gates/change-control-gate@0.1.0
  inputs:
    job_name: change-control-gate
```

| Input | Required | Default | Description |
|---|---|---|---|
| `high_risk_globs` | no | rbac/netpol/policy/clusterrole | High-risk path globs. |
| `normal_globs` | no | platform-services/clusters | Normal path globs. |
| `chg_pattern` | no | `CHG[0-9]{7}` | TODO(pair): confirm (OQ-02). |

Complements (does not replace) GitLab branch protection + approval rules. Story: `E06-S03`.
