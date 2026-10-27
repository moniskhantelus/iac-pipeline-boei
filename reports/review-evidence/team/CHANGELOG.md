# Changelog

All notable changes to the KaaS CI/CD components. Format: [Keep a Changelog](https://keepachangelog.com/).
Components are versioned together; a release tag publishes every component at its current spec.

## [0.1.0] - MIGRATION POINT - new location `kaas/pipelines/components` - TODO(pair): tag date 10/22/2026
### Migrated
- **Repo move.** The component catalog moved from the POC repo
  `kaas/pipelines/strata-components` to its permanent home `kaas/pipelines/components`.
  All component source, self-tests, fixtures, and config were carried over verbatim except for
  the repo-name rewrite below.
- **All components baselined at `0.1.0`.** Every component in this repo is now published at
  `0.1.0` — the catalog's version column and every `include: component:@<version>` example were
  reset from their POC spec numbers (`1.0.0`/`1.1.0`) to the single migration baseline. Pinned
  tool/image versions inside each `template.yml` (e.g. the Terraform image tag, checkov, buildah,
  cosign) are **out of scope** for this numbering — those are external versions the components
  *consume*, not the component version itself, and were left unchanged.
- **Repo-name rewrite.** Every self-reference to the old project was updated
  `strata-components` → `components`, including consumer `include: component:` examples
  (`$CI_SERVER_FQDN/kaas/pipelines/components/<group>/<name>@<version>`) and the GitLab API
  self-fetch paths in `security/policy-eval` and `terraform/test`
  (`.../projects/kaas%2Fpipelines%2Fcomponents/repository/files/...`). "Strata" as the platform
  name (KaaS/Strata) is unchanged.
### Versioning lifecycle (POC → dev/pre-prod → release)
The version number tracks the catalog's maturity stage, not just a running increment:
- **POC (done, old repo).** Early proof-of-concept in `kaas/pipelines/strata-components`. The
  `1.0.0`/`1.1.0` numbers used there were provisional spec markers, not a stability promise. Those
  entries are retained below as **history/provenance only** — they are **not** tags in this repo.
- **dev / pre-prod (now, `0.x`).** This repo starts at **`0.1.0`** and stays in the `0.x` range
  while the catalog is hardened toward being **pre-prod ready**. The API is explicitly **not yet
  stable**: within `0.x`, changes (including breaking ones) bump the **minor** version. Consumers
  pin to a `0.x` tag (e.g. `@0.1.0`); they must **not** pin to a `1.x` tag in this repo.
- **release (future, `1.0.0`).** `1.0.0` is cut only once the remaining pre-prod-readiness work is
  complete. From then on the catalog follows standard semver (breaking → major bump).
### Pipeline / CI (`.gitlab-ci.yml`)
- **Branch pushes now auto-run.** Added a `$CI_COMMIT_BRANCH` rule to `workflow:rules`, so a push
  to any branch creates a pipeline. The POC repo deliberately omitted this rule (to avoid
  dispatching to the saturated `gitlabrunner-prod` runner), which is why pushes previously produced
  no pipeline. The STR-221 history is retained in an in-file comment.
- **Cleanup.** Removed a duplicated `terraform/apply|destroy|drift` self-test include trio and moved
  stranded `# gitops` / `# onboarding` include comments out of the `workflow:` block back into the
  `include:` list.
- **TEMP — run UNTAGGED (runner DNS outage).** The tagged dind runners (dev `#44142` offline;
  sandbox `#44028`) failed the built-in repo checkout with
  `fatal: ... Could not resolve host: git.web.boeing.com` — a DNS failure on those runner devices,
  before any job script, unfixable from job YAML. Disabled the `default: tags:` block so jobs run
  untagged and GitLab schedules them on the healthy OCP instance runners
  (`#15568/#15554/#15507/#15499`). All currently-enabled self-tests are hermetic (shell+grep; the
  injected build/apply jobs are dormant `when: manual`), so none need dind. Re-tag only when a live
  container build is enabled and a healthy dind runner with working DNS exists. [STR-221]
- **Fix — `terraform/plan` cache key broke on the default.** The `cache_key` input defaulted to
  `"tfplan-$[[ inputs.environment ]]"`, but GitLab does **not** interpolate `$[[ inputs.* ]]` inside
  an input's default value, so the literal string reached the runner and the cache step failed with
  `archive_cache: ... syntax error ... (error token is "[ inputs.environment ]")`. This broke any
  consumer that didn't override `cache_key` (the plan self-test was the first to hit it). The default
  is now a static slash-free literal (`tfplan-default`) with the constraint documented; consumers
  should set `cache_key` per environment. The plan self-test now passes `cache_key: tfplan-test`
  explicitly, mirroring the consumer pattern.
- **TEMP — runner routing to the dev dind runner.** While `gitlabrunner-prod` is unusable (setup
  incomplete / Secrets quota — STR-221, being handled by the platform team elsewhere), the whole
  pipeline is routed to a healthy online dev/sandbox runner via a global
  `default: tags: [kaas-dev, dind]` (targets runner `#44142 cdp-kaas-dev...dind-executor`). dind is
  needed by `supply-chain/build-image` and is harmless for the shell+grep contract tests and the
  terraform jobs. **Revert when prod is healthy** (remove the `default:` block or retag).
- **TEMP — centralized `ASSERT_IMAGE`.** Added a top-level `variables: ASSERT_IMAGE` default
  (the `amp` terraform image already in use) so every `image: "${ASSERT_IMAGE}"` self-test uses one
  dev-runner-pullable image, with a single override point if the runner's registry entitlements
  differ. [STR-214]
- **TEMP — hand-rolled `secret_detection` gate replaces the broken shared component.** The shared
  `components/secret-detection/secret-detection@1` fails on our runner with
  `Error: unknown command "sh" for "gitleaks"` — it runs the `gitleaks` image whose ENTRYPOINT is
  `gitleaks`, so GitLab's injected shell collides with it. Replaced the `include: component:` with a
  local `secret_detection` job that clears the image entrypoint (`entrypoint: [""]`) and runs
  `gitleaks dir . --config .gitleaks.toml --no-banner --redact --verbose`. It is a **blocking**
  gate (no `allow_failure`): any finding fails the pipeline. Still uses the repo-local
  `.gitleaks.toml` (default + Azure/Terraform rules), so coverage is unchanged. [STR-226]
- **Fix — validate self-tests missed jobs due to jobs-API pagination.** `verify-validate-job-present`
  and `verify-validate-fmt-fails` queried the GitLab jobs API with a single un-paginated `curl`. The
  API returns only 20 jobs per page by default, but the full pipeline has 30+ jobs, so the looked-up
  job (`test-terraform-validate-bad-fmt`) sat on a later page and the exact-name lookup returned
  `null` regardless of timing. Both lookups now **paginate** (`per_page=100` + page loop, merging all
  pages with a POSIX-sh-safe `jq --argjson`); `verify-validate-fmt-fails` also retains a terminal-
  status poll. The validate fmt gate itself was correct (the fixture is genuinely mis-formatted) — a
  latent self-test bug that only surfaced once the complete pipeline ran server-side. [STR-215]

### Known follow-ups
- Consumer `strata-pipeline-vnext` must be repointed from `kaas/pipelines/strata-components` to
  `kaas/pipelines/components@0.1.0`.
- Any outstanding work on a POC branch (partner's in-flight changes) is to be migrated into this
  repo later, before `1.0.0`.
- **Revert the TEMP runner routing** (`default: tags:` + centralized `ASSERT_IMAGE`) once
  `gitlabrunner-prod` is confirmed healthy, so CI runs on the intended prod runner.
- **Confirm dev-runner image pullability.** If jobs fail at "Preparing environment … pull access
  denied", override `ASSERT_IMAGE` to an image the dev runner can pull (the hermetic contract tests
  need only shell + grep; `terraform/validate` and `terraform/plan` need a terraform image). [STR-214]
- **Pin / confirm the gated job images** before cutting a release tag: `cleanup-stale-artifacts`
  (`curl-jq`) and `create-release` (`glab-cli`) still carry `ecs-catalog` images marked
  `# TODO(pair): pin`.
- **Re-adopt the shared `secret-detection` component** once it no longer overrides the image
  entrypoint (tracking the `unknown command "sh"` bug upstream), replacing the local
  `secret_detection` job. [STR-226]

## [STR-299 Unreleased - ECS Pipeline Comparison]
### Added
- `terraform/destroy` — guarded teardown component (STR-299 Rec 2 / Appendix C A3). Destruction runs
  only when `destroy_enabled: "true"` (default `"false"` is a no-op; the command never runs).
  Persistent environments (`uat`/`prod`, configurable) additionally require a typed `confirm_destroy`
  token matching the environment name and a manual run; disposable environments auto-run once enabled.
  Managed Identity auth with an `ARM_CLIENT_SECRET` guard; reviews a saved `-destroy` plan then
  applies it. Closes the gap that no first-class, guarded destroy component existed.
- `tests/terraform/destroy-test.yml` — injection + configuration contract self-test for
  `terraform/destroy` (no live destroy); asserts the stop event, master switch, persistent-env
  confirmation, MSI-only auth, and saved destroy-plan apply. Wired into `.gitlab-ci.yml`.
- `tests/compliance-gates/terraform-gate-test.yml` — rewritten as a full injection + configuration
  contract self-test for `terraform/gate` (STR-222). Asserts all acceptance criteria statically:
  sandbox/dev auto-approve with logged env, uat/prod manual pause, uat `>=MIN_APPROVALS_UAT` via the
  GitLab approvals API, prod `>=MIN_APPROVALS_PROD` approvals + ServiceNow change-record pattern with
  per-condition messages, fail-closed on API error, the audit-trail record, and absence of the
  placeholder stub. **Wired and ENABLED in `.gitlab-ci.yml`** (hermetic: shell+grep asserts, injected
  gate job dormant). Replaces the prior stub-only test that checked only for the `ls -la` placeholder.
### Changed
- `compliance-gates/terraform-gate` — add a uniform audit trail (STR-222 audit-trail AC). Every gate
  decision now emits an `[AUDIT] gate_decision ...` record with environment, approvals found,
  change-record presence, and outcome (APPROVED/BLOCKED) on all paths: dev/sandbox auto-approve,
  uat pass/block, prod pass/block, and every fail-closed API-error branch. No change to gate
  behavior; closes the audit-logging acceptance criterion.
- `terraform/apply` — **fix broken artifact capture** (STR-230): `terraform apply` output is now
  `tee`'d to `apply.log` (written on success AND failure via `PIPESTATUS`), and the declared
  artifact is reliably produced. Retention raised to 90 days, `when: always`.
- `terraform/plan` — **fix artifact capture** (STR-230): adds `plan.log` (raw run output) and
  `plan.txt` (human-readable `terraform show -no-color` diff) as reliably-written artifacts;
  retention 90 days, `when: always`.

### Added (STR-230 — tamper-proof audit record)
- `compliance-gates/audit-record` — writes a structured **11-field** JSON record
  (`actor, commit_sha, plan_hash, timestamp, environment, module, outcome, pipeline_id, job_id,
  project_path, mr_ref`) to an **immutable (WORM)** Azure blob container after **every** apply,
  success or failure (`when: always`). Managed Identity only (`ARM_CLIENT_SECRET` guard); reads the
  plan hash from `plan.tfplan.sha256`; fails closed if the record is not 11 fields or the immutable
  write fails. Blob path `<env>/<module>/<YYYY/MM/DD>/...` for queryability.
- `compliance-gates/audit-record/query_audit.py` — compliance query tool: search the audit store by
  environment, module, date range, actor, or outcome (`--source azure` via MSI, or `--source local`
  for offline/downloaded records). JSON or table output.
- `tests/compliance-gates/audit-record-test.yml` + `tests/fixtures/audit-records/` — contract
  self-test (when:always, MSI-only, 11-field validation, plan-hash source, WORM upload, fail-closed)
  plus a hermetic functional check of `query_audit.py` against fixture records. **Wired + ENABLED**
  in `.gitlab-ci.yml`.
- NOTE: the WORM storage account (shared-services, separate from state; draft then locked to 730
  days after legal confirmation) is a **repo/module-plane** deliverable consumed by this component,
  not built here. See the component README "Dependencies".

### Added (STR-225 — cost estimation from the internal registry)
- `finops/infracost` — Terraform cost estimation sourced from the **Boeing-internal registry at a
  pinned version** (`registry.web.boeing.com/ecs-catalog/infracost/infracost:v0.10.39`) — no Docker
  Hub, no `:latest` (PRD REQ-SVC-13). Consumes `plan.tfplan.json`; advisory (`allow_failure: true`).
  Per the story's fallback (AC 4), `infracost_skip` **defaults to `Y`**: the step is disabled by
  default (logs the reason + the STR-225 tracking ticket and exits 0) so the pipeline keeps working
  until the internal mirror is onboarded; set `infracost_skip: "N"` to enable.
- `tests/finops/infracost-test.yml` — contract self-test asserting internal-registry path, pinned
  tag, no Docker Hub reference, the default-skip fallback + STR-225 reference, and advisory
  behavior. **Wired + ENABLED** in `.gitlab-ci.yml`.
- NOTE: mirroring `infracost/infracost` into the internal registry is a one-time **platform /
  ECS-Catalog** task (docker pull/tag/push) documented in the component README; until confirmed,
  keep the default `infracost_skip: "Y"`.
- `terraform/validate`, `terraform/plan`, `terraform/apply`, `terraform/test` — remove the
  `GIT_SSL_NO_VERIFY: "true"` Git TLS-verification bypass (STR-299 Rec 5). The bypass is commented
  out with a do-not-reinstate marker and replaced with `GIT_SSL_NO_VERIFY: "false"`; the
  Boeing-internal Terraform image trusts the corporate CA, so HTTPS clone/fetch verifies normally.
- `terraform/test` — complete `apply-ephemeral` mode (STR-299 Rec 6 / Appendix C A8): stands up a
  throwaway environment, runs post-apply assertions against the applied state, and ALWAYS tears it
  down via an `EXIT` trap (registered before apply, so a failed apply/assertion still destroys — no
  orphaned resource group). Replaces the prior TODO/WARN placeholder so required tests cannot
  silently skip.
- `terraform/test` runner (`tf_test.py`) — add `--post-apply` mode and a state-JSON normalizer so
  the same `tftest.yaml` assertions evaluate against real applied state (`terraform show -json`),
  not only the plan.

## [1.1.0] - TODO(pair): release date
### Added
- `terraform/test` — **bridge to Terratest**: Python runner exercises fmt/init/validate/plan and
  asserts a declarative `tftest.yaml` against the plan JSON. Plan mode needs no credentials.
- `security/policy-eval` — **bridge to Kyverno/OPA**: Python engine evaluates Kyverno-shaped YAML
  policies against manifests and Terraform plan JSON. `mode: Audit|Enforce`. Ships a seeded policy set.
- `terraform/drift` — scheduled drift detection with `-detailed-exitcode` and ops alert.
- `security/policy-promote` — Dev→Audit→Enforce lifecycle via GitOps MR.
- `supply-chain/scan-image` — Critical/High gate + CAIRO routing (wraps shared Twistlock).
- `supply-chain/sign-image` — Cosign `azurekms://` signing.
- `supply-chain/sbom` — Syft CycloneDX + `cosign attest`.
- `gitops/bootstrap-validate` — App-of-Apps + sync-wave ordering validation.
- `compliance-gates/change-control-gate` — change-class approval enforcement.
### Changed
- `terraform/plan` 1.0.0 → 1.1.0 — adds JSON plan artifact + sha256 for apply integrity.
- `compliance-gates/terraform-gate` 1.0.0 → 1.1.0 — environment-aware enforcement replaces the manual stub.
- `security/checkov` 1.0.0 → 1.1.0 — gate decision no longer governed by `--soft-fail`; HIGH/CRITICAL and null-severity findings now fail the job (STR-223, amends S006).

## [1.0.0] - 2026-10-16
### Added
- `terraform/validate` (STR-215) — versioned, self-contained component running
  `terraform fmt -check`, `terraform init -backend=false`, and `terraform validate` as a single
  reusable job with six validated inputs (`job_name`, `stage`, `tf_root`, `fail_on_fmt`,
  `terraform_image`, `terraform_version`). Runs with no backend credentials so it is safe on any
  merge request; `job_name` is interpolated into the job key so the component can be included more
  than once. Replaces the legacy `include: project:/file:` validate reference.
- `terraform/plan`, `terraform/apply` — plan/apply split, saved-plan apply,
  removes `-auto-approve` (closes GAP-015/006).
- `security/checkov` (initial), `compliance-gates/policy-gate`.
- `supply-chain/build-image`.
- `gitops/manifest-update`.
- `onboarding/readiness-check`, `onboarding/golden-path-request`.
