# KaaS CI/CD Components (`kaas/pipelines/components`)

Versioned, input-validated GitLab CI/CD components for the Boeing KaaS (Strata) platform. One
component project, many components, released together by semantic-version tag.

Consume a component with:

```yaml
include:
  - component: $CI_SERVER_FQDN/kaas/pipelines/components/<group>/<name>@<version>
    inputs:
      job_name: my-job
```

## Catalog

| Component | Latest | Purpose |
|---|---|---|
| `terraform/validate` | 0.1.0 | `fmt -check`, `init -backend=false`, `validate` (no creds) |
| `terraform/plan` | 0.1.0 | MSI plan → binary + JSON + sha256 artifacts |
| `terraform/apply` | 0.1.0 | Apply the **saved** plan only (no `-auto-approve`), SHA-256 verified |
| `terraform/test` | 0.1.0 | **Bridge:** Python Terraform exercise + plan-JSON assertions (→ Terratest) |
| `terraform/drift` | 0.1.0 | Scheduled drift detection (`-detailed-exitcode`) |
| `compliance-gates/terraform-gate` | 0.1.0 | Environment-aware approval gate (dev auto / uat 1 / prod 2 + CHG) |
| `compliance-gates/policy-gate` | 0.1.0 | Kyverno/conftest against the platform policy library |
| `compliance-gates/change-control-gate` | 0.1.0 | Change-class approvals + ServiceNow CHG |
| `compliance-gates/audit-record` | 0.1.0 | Tamper-proof 11-field audit record to immutable WORM store on every apply (success/failure) + query tool |
| `security/checkov` | 0.1.0 | IaC scan; HIGH/CRITICAL + null-severity block |
| `security/policy-eval` | 0.1.0 | **Bridge:** Python policy engine, Kyverno-shaped YAML (→ Kyverno/OPA) |
| `security/policy-promote` | 0.1.0 | Dev→Audit→Enforce via GitOps MR |
| `supply-chain/build-image` | 0.1.0 | Buildah rootless, approved-base enforced, digest capture |
| `supply-chain/scan-image` | 0.1.0 | Vuln gate (Critical/High) + CAIRO routing (wraps shared Twistlock) |
| `supply-chain/sign-image` | 0.1.0 | Cosign `azurekms://` signing |
| `supply-chain/sbom` | 0.1.0 | Syft CycloneDX + `cosign attest` |
| `finops/infracost` | 0.1.0 | Cost estimation from internal registry (pinned); default-skip fallback (STR-225) |
| `gitops/manifest-update` | 0.1.0 | Digest bump + MR (no `kubectl apply`) |
| `gitops/bootstrap-validate` | 0.1.0 | App-of-Apps + sync-wave ordering |
| `onboarding/readiness-check` | 0.1.0 | 10-point onboarding checklist gate |
| `onboarding/golden-path-request` | 0.1.0 | Request → provisioning MR (5 archetypes) |

Shared company components (secret-detection, hadolint, twistlock-scan, shellcheck, markdownlint,
renovate, sonarqube, coverity, …) are **consumed, not re-implemented**. See
[`../COMPANY-COMPONENTS.md`](../COMPANY-COMPONENTS.md).

## Authoring rules

Binding standard in [`../../_conventions/component-authoring-standard.md`](../../_conventions/component-authoring-standard.md):
no global keywords in `template.yml`; inputs over variables; required inputs have no default; job
name is an input; zero static credentials; internal pinned images only; self-tested; released by tag.

## Repo layout

```
templates/<group>/<name>/template.yml   # the only file consumers see
templates/<group>/<name>/README.md
tests/<group>/<name>-test.yml           # self-test fragment
tests/fixtures/...                       # fixtures the components act on
.gitlab-ci.yml                           # test + release
```

## Versioning

This catalog lives at `kaas/pipelines/components` and is **pre-1.0** (`0.x`). It starts at `0.1.0`;
the API is not yet stable and a `1.0.0` tag will only be cut once the pipeline is at least
**pre-prod ready**. Pin consumers to a `0.x` tag (e.g. `@0.1.0`) — do **not** pin to `1.x` here; the
`1.x` entries in `CHANGELOG.md` are retained history from the former POC repo
(`kaas/pipelines/strata-components`) and are not tags in this repo.

Pin consumers to `@MAJOR.MINOR.PATCH`. `@MAJOR.MINOR` / `@MAJOR` opt into forward patches. Never
`@main` in a consumer. Breaking change → (pre-1.0) minor bump + `CHANGELOG.md` + migration note;
(post-1.0) major bump + `CHANGELOG.md` + migration note.
