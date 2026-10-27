# `supply-chain/scan-image`

Vulnerability gate + CAIRO routing. Blocks on Critical (always) and High (unless a tracked waiver).
Three modes:

- `trivy` (default) — run Trivy directly.
- `prisma` — run `twist-cli` directly.
- `twistlock-shared` — **do not** run a scanner; read the company `components/twistlock-scan`
  job's JSON report and only apply the KaaS gate + CAIRO routing. Preferred when the shared
  component is already in the pipeline, so we don't duplicate scanning.

```yaml
# Use the shared company scanner, then gate + route with this component:
include:
  - component: $CI_SERVER_FQDN/components/twistlock-scan@1          # TODO(pair): confirm
  - component: $CI_SERVER_FQDN/kaas/pipelines/components/supply-chain/scan-image@0.1.0
    inputs:
      job_name: scan-image
      scan_tool: twistlock-shared
      shared_scan_job: twistlock-scan      # TODO(pair): match the shared component's job name
      shared_report_path: twistlock-report.json   # TODO(pair): confirm artifact path
      esat_id: $ESAT_ID
      app_id: $APP_ID
      support_group: $SUPPORT_GROUP
      namespace: $K8S_NAMESPACE
      environment: $DEPLOY_ENV
      cairo_endpoint: $CAIRO_ENDPOINT
```

| Input | Required | Default | Description |
|---|---|---|---|
| `scan_tool` | no | `trivy` | `trivy` / `prisma` / `twistlock-shared`. |
| `esat_id` | **yes** | — | CAIRO routing. |
| `app_id` | **yes** | — | CAIRO routing. |
| `support_group` | **yes** | — | CAIRO routing. |
| `high_waiver` | no | `false` | Allow High with a tracked waiver. |
| `cairo_endpoint` | no | `` | Empty = payload artifact only. |

Story: `E08-S02`.
