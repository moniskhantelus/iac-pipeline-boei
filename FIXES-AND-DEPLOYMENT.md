# STR-222 / STR-230: pipeline-only implementation

## Scope

Only `iac-pipeline-boei` is fixed. The team's components source and release remain unchanged. `components-main.zip` is restored byte-for-byte to the supplied archive. The original review and original team source remain under `reports/` as evidence, not active CI code.

The previous commit expanded the scope into a corrected component library. This follow-up removes that library and its publication instructions. Those earlier chat ZIPs proposing component changes are superseded for this request.

## How the pipeline uses the existing components

The workflow includes the existing `compliance-gates/terraform-gate@0.1.2` and `compliance-gates/audit-record@0.1.2` using the original component interfaces and job names. Local includes come afterward and define **consumer-side job overrides in this repository**:

| Existing component / integration | Pipeline-owned override | Purpose |
|---|---|---|
| terraform-gate / iac_gates_job | iac/.iac_gates_job.yml | Use a validated target environment, commit-bound merged MR, independent eligible approvals, strict change-number validation and fail-closed API handling. |
| audit-record / iac_audit_record | iac/.iac_audit_record.yml | Deliver/recheck actual terminal evidence instead of inferring outcome from a log string. |
| Legacy plan | iac/.iac_tf_init.yml | Produce one saved plan and a target/commit/pipeline/policy-bound manifest. |
| Legacy apply | iac/.iac_tf_apply.yml | Require both plan and gate, verify exact saved plan, recheck authorization, and synchronously write immutable intent/result/audit evidence. |
| Destroy | iac/.iac_destroy_plan.yml, iac/.iac_destroy_gate.yml, iac/.iac_tf_destroy.yml | Separate saved destroy plan, manual gate and audited application. Disabled by default; teardown mode skips normal apply. |

These overrides intentionally replace the affected jobs' scripts, rules, dependencies and related settings. Merely including the unchanged components would preserve the defects documented in the review. This is a pipeline-level adapter, not a claim that the team's component implementation was fixed. The gate's optional approval-minimum inputs cannot weaken the pipeline runtime's fixed policy floors.

`runtime/control.py` is this repository's canonical adapter. Generated copies are embedded in its job templates, so a consumer never downloads scripts from an unrelated branch. `python3 tools/build_templates.py --check` detects drift; run without `--check` after changing the runtime.

The uploaded archive identifies source bytes but does not prove what the private catalog published as `0.1.2`. Verify that release on the actual GitLab server. If your organization requires a commit pin, replace both component references with the already-published, verified team commit SHA. No team source changes or new component release are requested.

## Required configuration

1. Publish this pipeline repository's reviewed commit. The sample `examples/consumer.gitlab-ci.yml` includes its workflow by project and immutable commit SHA. Nested local includes resolve in the pipeline library at that same ref.
2. Set protected `CONTROL_IMAGE` to an approved image pinned by digest, such as `registry/path@sha256:<64 hex characters>`. It must include Python >=3.9, reviewed Terraform, Azure CLI supporting `az login --identity --client-id`, required storage commands, corporate CA certificates and the approved provider mirror. Initialization preserves committed locks with `-lockfile=readonly`.
3. Fill in `control-config.example.json` and store the actual JSON as protected GitLab **file variable `CONTROL_CONFIG_FILE`**, managed outside application branches. It defines exact branch-to-environment mapping, project/API identity, root/module, subscription, backend/state key, distinct plan/apply identity client IDs, eligible approver IDs and dedicated audit storage. Reuse the existing reviewed state keys; do not accidentally create new state paths.
4. Current legacy workflow branches are exactly `sandbox`, `dev`, `uat`, `main`, mapping to sandbox/dev/uat/prod. Empty, unknown, contradictory or ambiguous targets block. Protect these branches. Restrict pipeline-variable overrides of predefined metadata, protected policy, runner selection and credentials. Enforce template/CODEOWNERS or pipeline-execution-policy control outside application-editable CI. Code alone cannot stop an administrator or an authorized policy editor from replacing its own enforcement.
5. Configure masked, protected `GITLAB_APPROVAL_TOKEN` with the least privilege needed for the deployed server's `read_api` endpoints. Scope it to `uat`/`prod` deployment environments, not wildcard scope. Gate and apply jobs use those environment names. Plan jobs use `plan/<environment>` and refuse to receive the approval token. Do not substitute `CI_JOB_TOKEN` for an unverified approvals-API capability.
6. Enable reset of approvals on pushes, prohibit author/committer approvals, and prohibit per-MR approval-rule overrides. Populate authorized human reviewer IDs in the protected policy. UAT requires one distinct active eligible reviewer. Production requires two plus a whole `CHG` token with seven digits. Resolve exactly one merged promotion MR associated with the deployed merge/squash commit and expected target/project. Direct pushes, ambiguous associations and unsupported fast-forward-only evidence fail closed.
7. Set up protected apply runners tagged `kaas-control-sandbox`, `kaas-control-dev`, `kaas-control-uat`, `kaas-control-prod`. Each exposes only its own environment's apply identity with appropriately scoped Azure RBAC. Plan runners use corresponding `kaas-plan-<environment>` tags and only the separate read-only infrastructure identity plus narrow state/lease permissions. Never expose the apply identity on a plan runner: arbitrary Terraform providers/external data programs can execute before the approval gate. Configure protected GitLab deployment environments and allowed deployers.
8. The consumer Terraform root must exist and contain its reviewed provider configuration, `backend "azurerm" {}`, variables and committed `.terraform.lock.hcl`. Plan and apply identity IDs are supplied through execution-time environment variables rather than persisted into backend configuration; the saved plan must not pin the read-only identity for later application. Cloud permissions and provider configuration must prevent cross-environment access.
9. Deploy this repository's `shared-services/audit` separately. Configure dedicated audit storage distinct from every Terraform state account, private endpoint/DNS, a reviewer identity, and `runner_identity_principal_ids` mapping the stable environment names to **apply MI principal/object IDs**. Client IDs in the runtime policy are different from the principal IDs in role assignments. The writer has blob read/write for verified retries, no delete or policy-management access, and read-only policy inspection. If previously deployed with the singular writer assignment, review/migrate its state address to `writer["primary"]` before planning.
10. Keep `lock_retention=false` initially. The draft policy is 730 days. Only after actual legal confirmation, make a separately reviewed change setting `lock_retention=true` and `legal_approval_reference`. Locking is irreversible; this work does not execute a lock operation. Reconcile Terraform state/config and retain approval evidence. UAT/prod runtime requires an actual Locked 730-day policy. Sandbox/dev draft acceptance can explicitly opt in with `audit.allow_draft_lower_env=true`; that is not final administrator-proof compliance.
11. Confirm S010's authoritative field mapping and the ServiceNow number format with their owners. The protected policy must explicitly record `schema_approved=true` and `change_pattern_confirmed=true` only after confirmation. Those booleans do not create approval. The provisional schema is `runtime/audit-record.schema.json`; if the authoritative mapping differs, update this repository's adapter/schema/tests before deployment.

## Evidence, outages and recovery

Plan and apply output are actually written under `control-evidence/`, retained for 90 days and downloadable by project Developers and higher. Review project membership and sensitive plan content. The plan manifest binds the binary hash to commit, project, pipeline, root/module, environment, state account/key, operation and protected policy bytes. Apply needs both plan and gate and rechecks the hash after initialization. Its actor comes from the triggering plan; the apply execution actor is also captured separately.

Each actual apply or destroy attempt writes a unique immutable `intent.json` **before Terraform init/apply**. An unavailable audit store at that point blocks mutation. A handled successful or failed command writes `result.json` with the actual exit code and log hash, then the queryable 11-field `audit.json`. Audit failure after mutation fails the job; it does not claim infrastructure rolled back.

Writes are conditional block-blob creates (`if-none-match=*`, `overwrite=false`). A lost successful upload response is reconciled by downloading and comparing existing bytes. Different bytes cannot replace the original. Local terminal evidence remains an artifact for recovery. Delivery and replay validate the record against the real exit code, apply-log hash, job/attempt identity and project/pipeline storage path. Missing terminal evidence fails delivery rather than returning success.

Use an authorized identity in the correct Azure cloud to replay trusted terminal evidence without rerunning Terraform:

```sh
python3 runtime/replay_terminal.py --config /trusted/control-config.json \
  --evidence /downloaded/control-evidence --expected-job-id 12345
```

Run the read-only completeness monitor independently of deployment runners, and connect its nonzero status to the organization's incident/alert process:

```sh
python3 runtime/reconcile.py --account ACTUAL_AUDIT_ACCOUNT --container audit --older-than-minutes 30
```

It enumerates all pages, detects intents missing terminal/audit records, reports outcome `unknown` and exits nonzero. A killed runner cannot guarantee a final success/failure record. Operators must investigate the job and Terraform state, recover trusted terminal artifacts where available and preserve a reviewed resolution for unknown outcomes. Do not infer success from a job status or automatically reapply infrastructure to repair an audit gap. Installing/testing this operational process remains required for “every apply” acceptance. No monitor schedule or external notification has been created here.

## Queries and real WORM verification

`runtime/query_audit.py` filters environment/module/actor/date/outcome, requests all Azure list pages, rejects malformed records and excludes the following day's midnight from an inclusive end date. It reads queryable audit records, not intent/result envelopes. Supply an existing reviewer login in the correct cloud:

```sh
python3 runtime/query_audit.py --account ACTUAL_AUDIT_ACCOUNT --environment prod \
  --module network --from 2026-10-01 --to 2026-10-31
```

After legal approval, run the negative acceptance test only on an already locked, approved test container with an operator who can actually write/delete blobs:

```sh
python3 runtime/verify_worm.py --account ACTUAL_AUDIT_ACCOUNT --resource-group ACTUAL_RG \
  --subscription ACTUAL_SUBSCRIPTION --container audit --evidence worm-acceptance.json
```

The test checks Locked/730-day policy, creates a unique record, requests actual overwrite and deletion, requires `BlobImmutableDueToPolicy` for both, verifies unchanged bytes and saves evidence. Authorization/network errors are not proof of WORM. The acceptance record remains retained for the policy period. The script never locks or unlocks a policy.

## Validation and remaining acceptance

The root CI runs this pipeline repository's tests. Run locally:

```sh
python3 -m unittest discover -s tests/control -v
python3 tools/build_templates.py --check
```

Behavioral and local command-flow tests use controlled fakes for Azure/Terraform; they are not proof of deployed service behavior. See `VALIDATION.md` and `test-results.txt` for recorded results. `reports/STR-222-STR-230-compliance-review.md` is the original pre-fix assessment, including independent findings about the unchanged team components. Those findings remain relevant to any other consumers that use the components without these overrides.

Before production sign-off, retain actual merged GitLab CI lint showing the team component plus local job overrides, verify the published component revision and manual/DAG rules, real API authentication and approval settings, live success/failure/destroy/cancellation and replay/reconciliation, MI/RBAC/private networking, exact plan linkage, artifact downloads/retention/access, S010/legal confirmation, locked-store negative tests and multi-page queries. Provider initialization could not complete here because registry.terraform.io DNS was unavailable; full provider schema validation and reviewed deployment planning remain necessary.

This change does not fix or publish any components repository, promise other consumers are protected, deploy infrastructure or lock retention.
