# `security/checkov`

IaC static analysis that blocks on HIGH/CRITICAL. Unlike the legacy job, it does **not** use
`--soft-fail` for the gate decision and routes `severity == null` into the blocking bucket
(fail-safe).

```yaml
include:
  - component: $CI_SERVER_FQDN/kaas/pipelines/components/security/checkov@0.1.0
    inputs:
      job_name: checkov
      scan_dir: examples/basic
```

| Input | Required | Default | Description |
|---|---|---|---|
| `scan_dir` | no | `.` | Directory to scan. |
| `skip_path` | no | `examples` | Paths to skip. |
| `frameworks` | no | tf/cfn/k8s/docker | Checkov frameworks. |
| `treat_null_severity_as_blocking` | no | `true` | Null severity blocks. |
| `checkov_image_version` | no | `0.9.0` | Pinned tag. |

Story: `E01-S05` (GAP-017). Jira: STR-223.
