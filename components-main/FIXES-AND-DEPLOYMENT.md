# Fixed STR-222 / STR-230 implementation

This package replaces the broken plan/apply/gate integration with one tested runtime shared by the component and pipeline repositories. It is source code ready for configuration and server acceptance, not evidence of deployed compliance. Nothing has been deployed or locked by this change.

## What changed

| Review issue | Code fix |
|---|---|
| B1 unresolved .str230_runtime | Removed; every controlled CI job embeds the versioned runtime. No checkout of scripts from another branch or runtime download. |
| B2 different saved-plan paths | One control-evidence/plan.tfplan; SHA-256 and manifest bound to commit, pipeline, project, target, state key, policy file and operation. Verified at gate and immediately before apply. |
| B3 environment bypass | Protected external configuration maps exact branches to targets. Empty, contradictory, ambiguous and unknown environments block. Lower env policy cannot authorize prod. |
| B4 wrong MR / token / independent approvals | Commit-associated merged promotion MR, exact target/project and merge/squash SHA binding, read_api credential, strict response types, distinct active eligible humans, author exclusion and required project approval-reset/committer protections. |
| B5 DAG bypass | Apply needs both plan and gate, neither optional. Apply rechecks approvals immediately before mutation. Prod/UAT gate is manual; destroy always has its own manual gate. |
| B6 wrong audit account / lock claims | No sandbox account default. Trusted config rejects every known state account. Runtime checks actual 730-day policy and requires Locked for UAT/prod. Terraform defaults unlocked with a guarded explicit legal-lock input. |
| B7 unreliable outcome / missing failures | Actual Terraform exit code; durable immutable intent before init/apply; terminal result and 11-field audit record in finally; retry-safe conditional writes, replay utility, and unresolved-intent monitor. |
| B8 unverified S010 | Explicit provisional-v1 JSON schema and field/value validation; deployment blocks until the S010 owner confirms that mapping. Owner approval is an external process, not created by a boolean. |
| Other findings | Strict CHG token boundaries; Git TLS verification restored; digest-pinned job images; committed provider locks retained; destroy uses separately planned and gated saved plan; query rejects malformed records, requests all pages and fixes inclusive date boundaries. |

The canonical runtime is runtime/control.py. tools/build_templates.py regenerates embedded copies; --check detects drift. Both repository packages contain identical runtime bytes. The risk-only change-control-gate is now an alias of the environment gate and uses its new interface.

## Required setup

1. Review the code and publish the library/component revision. Include an immutable 40-character commit SHA in the consumer. Do not publish over the existing 0.1.2 tag. The pipeline's nested includes resolve in its own repository/ref; no STR_230 remote includes remain.
2. Provide an approved Linux image containing Python >=3.9, the reviewed Terraform version, Azure CLI supporting --client-id MI login and the storage flags used here, and corporate CA certificates. Set protected CONTROL_IMAGE to registry/path@sha256:<64 hex characters>. Verify the image's binaries and certificate trust. No TLS verification bypass or public package download was added. Set up an approved Terraform provider mirror in that image/runner; this package does not delete lock files or change mirrors.
3. Start from control-config.example.json, substitute actual values, and store the resulting JSON as a **protected GitLab file variable CONTROL_CONFIG_FILE**, managed outside application branches. Do not commit production policy or set schema_approved/change_pattern_confirmed until the owners confirm the specified schema and CHG format. Current format is the whole token CHG plus seven digits; change code/schema/tests together if the process owner specifies another format.
4. Set masked, protected, environment-scoped GITLAB_APPROVAL_TOKEN for the uat/prod deployment environment names only (never wildcard scope) with the least privilege required for read_api on the deployment project. Validate the installed server's API/license and endpoint behavior. The code deliberately does not use CI_JOB_TOKEN for approval APIs. Plan jobs declare environment plan/<env>, run on isolated read-only runners, and refuse an inherited approval token; gate/apply declare the deployment environment. This prevents Terraform planning code from receiving the approval API credential.
5. Protect sandbox/dev/uat/main deployment refs. Block direct pushes to UAT/main, require reviewed MRs, reset approvals on pushes, prohibit author and committer approvals, and prohibit per-MR approval-rule overrides. Populate eligible_approver_ids with the authorized human reviewer IDs in the protected policy. Restrict pipeline-variable overrides, including overrides of predefined CI metadata, protected config, credentials, runner selection and environment controls. Use GitLab roles/settings to prevent application developers from overriding those values. Required checks and protected configuration must be enforced outside modifiable application YAML (for example a protected pipeline execution policy and CODEOWNERS on the template source).
6. Register protected environment-specific runners tagged kaas-control-sandbox, kaas-control-dev, kaas-control-uat and kaas-control-prod. Apply runners must expose only their assigned user-assigned managed identity, with infrastructure permissions scoped to their own target. Plans use separate runners tagged kaas-plan-sandbox/dev/uat/prod (one full tag per environment), exposing only plan_identity_client_id with read-only infrastructure permissions and narrowly scoped backend state/lease permissions. Never attach the apply identity to a plan runner: arbitrary Terraform providers or external data programs can execute during planning, before the approval gate. The runtime selects the plan identity for planning and the apply identity only after the gate. Configure protected GitLab deployment environments and allowed deployers. A runner with all environment identities or broad subscription permissions defeats isolation even if the gate code is correct. Arbitrary Terraform provider configuration must not be able to obtain cross-environment access; enforce Azure RBAC and code ownership.
7. Configure subscription/backend/root/module per environment. The consumer root must exist, contain backend "azurerm" {}, use the reviewed provider configuration, and commit its .terraform.lock.hcl. Initialization uses -lockfile=readonly. Identity client IDs are supplied through the execution environment, not persisted into backend configuration, so the saved plan does not pin the read-only plan identity for the apply job. Existing hardcoded dev credentials, backend overrides and test accounts are no longer used. This is an intentional migration: retain reviewed backend/state keys when filling the policy to avoid accidental new state locations.
8. Deploy shared-services/audit separately with the correct MI principal and reviewer IDs, private endpoint/DNS and independent state-account names. Set runner_identity_principal_ids to a stable-keyed map of all apply-runner principal IDs (for example dev/uat/prod); the optional singular runner_identity_principal_id is retained as the primary entry. If this module was already deployed, review/migrate the existing writer role-assignment state address to writer["primary"] before planning, to avoid replacement. The writer has blob read/write for exact retry verification, no delete or retention-management permission, and read-only policy inspection. Identity **client ID** in policy differs from identity **principal/object ID** in Terraform RBAC inputs. Grant the MI only the audited account's required permissions and test both clouds/subscriptions. The storage account and reviewer/runner networking must actually be deployed.
9. Initially keep lock_retention=false. Lower sandbox/dev acceptance runs can explicitly set audit.allow_draft_lower_env=true; these are visibly draft and not administrator-proof compliance. UAT/prod require an actual locked 730-day policy. After legal confirmation, a separately approved Terraform change may set lock_retention=true with legal_approval_reference. **Locking is irreversible; this package never runs a lock operation.** Preserve legal evidence and reconcile state/config after locking.
10. Run the server acceptance checklist below. The root .gitlab-ci.yml in each library runs the behavioral tests; it deliberately does not apply a nonexistent examples/basic root. The team's previous root CI is retained as .gitlab-ci.before-control-fix.yml for merging its unrelated tests/releases back into the team's CI. It is not included automatically, because its old component injections use the replaced interfaces.

## Consumer integration

For the pipeline library, use examples/consumer.gitlab-ci.yml and replace the example ref with the reviewed published SHA. Existing consumers expecting .iac_tf_init.yml/.iac_tf_apply.yml keep the job names, but must supply the new protected configuration/image/identity prerequisites. Supported legacy workflow branches are exactly sandbox, dev, uat, main; branch suffix aliases are intentionally removed. Component consumers can configure other exact branch names in the protected mapping.

For components, use examples/components-consumer.gitlab-ci.yml. New components require environment, use protected CONTROL_CONFIG_FILE for root/backend/module, and no longer accept tf_root/backend/var_file as independent untrusted target inputs. Default named jobs are tf-plan, tf-gate, tf-apply, audit-record. The apply component must consume both plan_job and gate_job. Stage ordering and DAG dependencies are both explicit. There is no separate post-apply log parser: synchronous immutable delivery is part of the actual apply job; audit-record is an idempotent delivery/recovery check.

The old terraform/test apply-ephemeral mode is removed because its direct apply/EXIT-trap destroy bypassed gates and immutable audit. Its mode input now permits only plan. For ephemeral integration tests, provision through the audited components, run post-apply assertions, and use the separately gated destroy flow.

Destruction is disabled by default. To enable it, deliberately configure CONTROL_DESTROY_ENABLED=true in the protected pipeline policy or supply destroy_enabled: "true" to the destroy plan/gate/apply components. Add a separate plan component with operation: destroy, a separate terraform-gate with operation: destroy, then terraform/destroy pointing at those two jobs. All three components must receive destroy_enabled: "true". The legacy workflow already provides these jobs and skips its normal apply path when destroy mode is enabled, so a teardown pipeline does not provision infrastructure first. A destroy plan is generated **before** the manual gate; the apply step executes only that saved destroy plan, with the same approvals, CHG and audit policy. No job runs terraform destroy directly.

## Audit and interrupted-job recovery

Each apply attempt creates a unique path including environment/module/date/project/pipeline/job/UUID:

- intent.json is durably uploaded before Terraform init/apply. An audit outage at this point blocks infrastructure mutation.
- result.json contains the real exit code, log hash, execution actor, operation and canonical 11-field record.
- audit.json contains the approved field mapping for compliance queries. Its job_id is the apply job ID. actor is the trigger captured in the plan manifest; the result/intent also carry the execution actor.

Upload uses block blobs, if-none-match=* and overwrite=false. If an upload's success response is lost, retry downloads existing bytes and accepts only an exact hash match; different bytes never replace an existing record. Failed terminal delivery fails the job but does not pretend infrastructure was rolled back. Local evidence remains a protected-project 90-day artifact (downloadable by project Developers and higher; review membership and sensitive plan data); use runtime/replay_terminal.py to deliver trusted saved terminal artifacts without rerunning Terraform:

```sh
# Log in using the authorized identity in the correct cloud first.
python3 runtime/replay_terminal.py --config /trusted/control-config.json \
  --evidence /downloaded/control-evidence --expected-job-id 12345
```

Schedule runtime/reconcile.py from an independent protected monitor using a reviewer/read-only identity, separate from the deployment runner:

```sh
python3 runtime/reconcile.py --account ACTUAL_AUDIT_ACCOUNT --container audit --older-than-minutes 30
```

It lists all pages, finds intents lacking result/audit, emits outcome unknown and exits nonzero. Connect that failure to the organization's alert/incident process. No external messages or schedules have been created by this code package. A killed runner cannot guarantee a final success/failure record; the durable intent ensures the attempt remains discoverable. An operator must examine the job and Terraform state, recover trusted terminal artifacts where available, and record a separately reviewed resolution when the final outcome is unknown. Never infer success from job status or automatically reapply to repair evidence. This remaining operational reconciliation/alert process must be installed and tested before claiming “every apply” acceptance. Pre-mutation failures without an intent are blocked controls rather than executed infrastructure changes; their diagnostics remain CI artifacts.

## Query and WORM acceptance

runtime/query_audit.py (or templates/compliance-gates/audit-record/query_audit.py in the component tree) supports environment/module/actor/date/outcome filters. Supply an existing reviewer Azure login in the correct cloud. It requests --num-results "*" so a 5,000-record page is not mistaken for the entire store, and rejects malformed records rather than silently returning incomplete evidence. It queries audit.json/legacy audit-*.json records and excludes intent/result envelopes.

```sh
python3 runtime/query_audit.py --account ACTUAL_AUDIT_ACCOUNT --environment prod \
  --module network --from 2026-10-01 --to 2026-10-31
```

After legal lock approval, run the test on an **already locked approved test container** with an operator authorized to write/delete blobs:

```sh
python3 runtime/verify_worm.py --account ACTUAL_AUDIT_ACCOUNT --resource-group ACTUAL_RG \
  --subscription ACTUAL_SUBSCRIPTION --container audit --evidence worm-acceptance.json
```

The verifier refuses unlocked/non-730-day policies, uploads a unique acceptance blob, requests actual overwrite and deletion, requires BlobImmutableDueToPolicy for each, downloads and compares original bytes, and saves evidence. Authorization/network failures do not count as WORM protection. The test blob remains retained for the full policy period. It does not lock or unlock anything.

## Local verification and remaining acceptance

Run `python3 -m unittest discover -s tests/control -v` and `python3 tools/build_templates.py --check` in either corrected repository. Tests cover control decisions, failed applies, actual command-wrapper execution against fake Azure/Terraform executables, idempotent delivery, policy checks and recovery behavior. Fakes do not prove Azure/GitLab behavior. Inspect the supplied VALIDATION.md/test-results.txt for the actual run.

Before sign-off, retain evidence of: merged consumer GitLab CI lint; manual gate/DAG scheduling on the installed version; real GitLab token and project-approval settings; promotion merge/squash binding (fast-forward-only and direct-push promotion intentionally fail closed); live success/partial-failure/destroy and canceled-run tests; correct MI/cloud/subscription/RBAC/private networking; exact saved-plan hash; real artifact downloads and access/90-day retention; legal and S010 sign-off; real locked-store negative tests; terminal-write outage/replay; independent reconciliation alerts; and query over a multi-page store. GitLab settings/administrator powers are external dependencies and are not created by this source archive.

Provider initialization/validation could not complete on this host because registry.terraform.io DNS was unavailable. Terraform formatting checks passed. Full provider schema validation and a reviewed deployment plan remain required; no Azure resources were deployed.

Primary API references: https://docs.gitlab.com/api/commits/ ; https://docs.gitlab.com/api/merge_request_approvals/ ; https://docs.gitlab.com/ci/yaml/#needs ; https://learn.microsoft.com/en-us/cli/azure/storage/blob ; https://learn.microsoft.com/en-us/azure/storage/blobs/immutable-policy-configure-container-scope . Installed versions must be tested before release.
