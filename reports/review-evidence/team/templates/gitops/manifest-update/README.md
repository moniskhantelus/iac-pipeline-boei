# `gitops/manifest-update`

The CI→CD hand-off. Bumps the image **digest** in a GitOps overlay and opens an MR via a scoped
deploy key. Refuses mutable tags and contains **no** `kubectl apply` — the agent reconciles.

```yaml
- component: $CI_SERVER_FQDN/kaas/pipelines/components/gitops/manifest-update@0.1.0
  inputs:
    job_name: gitops-update
    sbom_job: sbom
    gitops_repo: $GITOPS_REPO
    overlay_path: overlays/$DEPLOY_ENV
    environment: $DEPLOY_ENV
```

| Input | Required | Default | Description |
|---|---|---|---|
| `image_ref` | no | `$IMAGE_REF` | Must be `repo@sha256:...`. |
| `gitops_repo` | **yes** | — | GitOps repo to open the MR against. |
| `overlay_path` | no | `overlays/dev` | Kustomize overlay. |
| `dry_run` | no | `false` | Self-test. |

Requires `GITOPS_DEPLOY_KEY`. Overlay must use a Kustomize `images:` block. Story: `E06-S01`.
