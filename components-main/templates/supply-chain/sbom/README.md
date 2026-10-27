# `supply-chain/sbom`

Generates a CycloneDX SBOM with Syft and attaches it to the signed image via `cosign attest`.

```yaml
- component: $CI_SERVER_FQDN/kaas/pipelines/components/supply-chain/sbom@0.1.0
  inputs:
    job_name: sbom
    sign_job: sign-image
    signing_key_uri: $SIGNING_KEY_URI
```

| Input | Required | Default | Description |
|---|---|---|---|
| `image_ref` | no | `$IMAGE_REF` | Image to document. |
| `sign_job` | no | `sign-image` | Upstream (needs:). |
| `signing_key_uri` | **yes** | — | KMS key for the attestation. |

Story: `E08-S04`.
