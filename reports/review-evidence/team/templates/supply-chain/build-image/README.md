# `supply-chain/build-image`

Rootless Buildah build from an approved pre-qualified base, pushed to the team ACR repo. Captures the
immutable **digest** into `image.env` (dotenv) for the scan/sign/sbom/gitops chain.

```yaml
- component: $CI_SERVER_FQDN/kaas/pipelines/components/supply-chain/build-image@0.1.0
  inputs:
    job_name: build-image
    team: $TEAM_ID
    app: $APP_NAME
    registry_url: $REGISTRY_URL
    base_image_registry: $BASE_IMAGE_REGISTRY
```

| Input | Required | Default | Description |
|---|---|---|---|
| `team` | **yes** | — | ACR repo namespace. |
| `app` | **yes** | — | ACR repo name. |
| `registry_url` | no | `kaasappacr.azurecr.us` | Per-cloud registry. |
| `base_image_registry` | no | `kaasbaseacr.azurecr.us` | Enforced base registry. |

Alternative: the company `components/docker-build` + `components/docker-push` can replace this if
base enforcement + digest capture are handled elsewhere (see COMPANY-COMPONENTS.md). Story: `E08-S01`.
