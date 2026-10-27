# `supply-chain/sign-image`

Cosign-signs the scanned image with an HSM-backed KMS key via Managed Identity. Only runs after the
scan job passes (`needs:`).

```yaml
- component: $CI_SERVER_FQDN/kaas/pipelines/components/supply-chain/sign-image@0.1.0
  inputs:
    job_name: sign-image
    scan_job: scan-image
    signing_key_uri: $SIGNING_KEY_URI   # azurekms://... / awskms://... / gcpkms://...
```

| Input | Required | Default | Description |
|---|---|---|---|
| `image_ref` | no | `$IMAGE_REF` | Digest reference to sign. |
| `scan_job` | no | `scan-image` | Upstream gate (needs:). |
| `signing_key_uri` | **yes** | — | KMS key URI. TODO(pair): dev + prod key URIs. |

Runner identity needs `Key Vault Crypto User` on the signing key. Story: `E08-S03`.
