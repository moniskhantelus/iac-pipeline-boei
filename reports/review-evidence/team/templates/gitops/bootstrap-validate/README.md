# `gitops/bootstrap-validate`

Validates the platform GitOps bootstrap: schema-checks every kustomization and asserts sync-wave
(Argo CD) / dependsOn (Flux) ordering matches the required platform-service dependency chain.

```yaml
- component: $CI_SERVER_FQDN/kaas/pipelines/components/gitops/bootstrap-validate@0.1.0
  inputs:
    job_name: bootstrap-validate
    agent: argocd
```

| Input | Required | Default | Description |
|---|---|---|---|
| `agent` | no | `argocd` | `argocd` or `flux`. TODO(pair): AD-2 bake-off. |
| `bootstrap_path` | no | `clusters` | App-of-Apps path. |
| `platform_services_path` | no | `platform-services` | Child apps. |
| `expected_order` | no | namespaces→…→app-namespaces | Dependency order. |

Consumed by the `platform-gitops` repo CI. Story: `E06-S02`.

> Note: the embedded Python heredoc is indented to sit inside the YAML `|` block. If your editor
> reflows it, keep the `PY ... PY` delimiters and the body at the same indentation shown here.
