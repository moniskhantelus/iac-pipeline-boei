# `onboarding/golden-path-request`

Renders a chosen archetype's templates with the request values and opens a **single** atomic
provisioning MR in the platform GitOps repo (namespace, RBAC, netpol, GitOps scaffold,
ExternalSecret, observability, CI pipeline).

```yaml
- component: $CI_SERVER_FQDN/kaas/pipelines/components/onboarding/golden-path-request@0.1.0
  inputs:
    job_name: golden-path-request
    archetype: gp-api
    request_file: onboarding.yaml
```

| Input | Required | Default | Description |
|---|---|---|---|
| `archetype` | no | `gp-api` | `gp-api`/`gp-web`/`gp-worker`/`gp-batch`/`gp-stateful`. |
| `request_file` | no | `onboarding.yaml` | Onboarding request. |
| `gitops_repo` | no | `kaas/platform/platform-gitops` | Target GitOps repo. |
| `templates_repo` | no | `kaas/platform/golden-path-templates` | Archetype templates. |
| `templates_ref` | no | `v1.0.0` | Pinned templates version. |
| `dry_run` | no | `false` | Render + validate only. |

Requires `GITOPS_DEPLOY_KEY` and the `golden-path-templates` repo. Story: `E12-S02`.
