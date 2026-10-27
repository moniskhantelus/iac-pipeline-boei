# `onboarding/readiness-check`

Automates the 10-point onboarding readiness checklist and blocks onboarding on any mandatory
failure. Secret scanning uses the company `components/secret-detection` where possible; this
component checks Dockerfile non-root, probes, resource limits, App/ESAT IDs, and request attestations.

```yaml
- component: $CI_SERVER_FQDN/kaas/pipelines/components/onboarding/readiness-check@0.1.0
  inputs:
    job_name: readiness-check
    request_file: onboarding.yaml
    app_dir: .
    manifest_dir: k8s
```

| Input | Required | Default | Description |
|---|---|---|---|
| `request_file` | no | `onboarding.yaml` | Onboarding request. |
| `app_dir` | no | `.` | App source to inspect. |
| `manifest_dir` | no | `k8s` | Manifests to inspect. |
| `allow_exceptions` | no | `` | Comma IDs under an active waiver (warn not block). |

Story: `E12-S01`. See `onboarding.yaml` schema in the `gp-api` scaffold.
