# STR-222 / STR-230 code-level compliance review

Review date: October 27, 2026. **Recommendation: FAIL the compliance gate; do not sign off either story for the integrated pipeline.** The team library contains useful functional building blocks, but the submitted pipeline is not a working, evidenced implementation of the acceptance criteria.

## Scope and evidence rules

Reviewed both requested archives, recovered from the referenced conversation's attachment paths because `/mnt/data` is unavailable on this host. The pipeline archive embeds `components-main.zip`; its SHA-256 exactly matches the separately uploaded team archive: `0ae47a2256c7207b1b54971d19351574314751c5de4f82fae15a2d6293fe5d6e`. No alternate team revision was substituted.

Acceptance criteria were retrieved from the complete user message in “Review Story Compliance Gate.” Exact S010 specifications and legal approval were not supplied. This review assesses the stated stories, not organizational accreditation or a complete FedRAMP control assessment. Documentation assertions are not treated as executable controls. No private GitLab configuration, catalog release contents, protected environments, Azure deployments, or live acceptance results were available.

Evidence shorthand: **P** = `review-evidence/pipeline/`; **T** = `review-evidence/team/`. All paths below refer to verbatim extracted source, with one-based source lines. Source files accompany this report. Pass means a specific code-level criterion is implemented; it does not imply deployment acceptance. Partial means implementation exists but is incomplete or unverified. Fail means a defect or absent executable integration prevents meeting the criterion.

## Acceptance matrix

| Story / acceptance criterion | Team components alone | Integrated pipeline | Evidence and assessment |
|---|---|---|---|
| 222: sandbox/dev automatic approval and environment log | Partial | Fail | T `templates/compliance-gates/terraform-gate/template.yml:35–55`: auto and audit logging exist, but branch determines policy rather than supplied target. Environment can be empty or contradictory. |
| 222: UAT manual pause and >=1 MR approval | Partial | Fail | T gate `37–38,59–87`: manual rule and count exist. Wrong MR lookup, unsupported token assumption, and environment mismatch prevent reliable enforcement. |
| 222: prod manual pause, >=2 independent approvals and valid CHG | Partial | Fail | T gate `37–38,70–107`: checks count and regex. No unique/eligible reviewer validation, target-commit binding, or robust CHG token boundaries; policy inputs can reduce minima. |
| 222: API verification failure blocks change | Partial | Partial | T gate `59–75` fails on curl/jq errors with pipefail. Authentication compatibility and response schema are unverified; this control does not cover the team's standalone apply DAG. |
| 222: every decision logs env/count/CHG/outcome | Partial | Partial | T gate `48–54,62–107` logs normal and handled API decisions. UAT records CHG n/a, invalid configuration or unexpected shell exits can omit decision, target env may be blank/misleading. |
| 222: placeholder removed | Pass | Pass (narrow) | P workflow `100–107` includes functional team gate. There is no placeholder gate job in supplied pipeline; unrelated diagnostic `ls` commands are not gate placeholders. |
| 222 dependency: gate precedes all apply paths | Partial | Partial | P workflow `120–123` orders approval before apply; P apply has dependencies, not needs. T apply `49–57` needs only plan, and can bypass earlier gate stages. Destroy also lacks equivalent checks. |
| 230: full plan/apply output downloadable on every completed attempt | Partial | Fail | T plan `88–111`, apply `95–112` capture command output. P plan `154–177` captures output but apply `128` names a different plan; P apply `146` declares an unwritten secondary output file. Setup failures precede log creation. |
| 230: dedicated shared-services WORM storage, draft then legally approved 730-day lock | External dependency | Partial | P `shared-services/audit/main.tf:51–115` implements separate account, separation precondition and draft 730-day policy. No deployment/lock evidence; runtime account explicitly points at sandbox state storage. |
| 230: every apply writes correct structured S010 11-field record | Partial | Fail | T audit `81–117` generates 11 keys but guesses outcome and tolerates unavailable hash; S010 mapping unconfirmed; pipeline configuration and plan integration broken. |
| 230: failed applies recorded | Partial | Fail | T audit `56–69` uses optional needs and when:always; log parsing `81–87` is not authoritative outcome. No durable recovery for canceled/terminated jobs or audit failures. |
| 230: Azure rejects delete/modify under locked retention, proven acceptance test | Fail / unverified | Fail / unverified | T audit README `80–81` requests a future real test. P policy `111` remains unlocked. No executable verifier or test result in archives. |
| 230: query by env/module/date/actor | Pass locally; Azure unverified | Partial | T `templates/compliance-gates/audit-record/query_audit.py:59–76,112–169` provides filters and Azure reads; script not packaged into pipeline archive except nested ZIP. Date boundary and pagination need repair/testing. |
| 230: operational artifacts retained 90 days, compliance separate | Pass for relevant library artifacts | Partial | T plan `110`, apply `111`, audit `145`; P init `176`, apply `143`. Dedicated storage exists as Terraform source but runtime points at state account. |

## Blocking findings and concrete fixes

### B1 — Pipeline has an unresolved GitLab reference (P1)

**Evidence:** P `iac/.iac_tf_init.yml:19` invokes `!reference [.str230_runtime, script]`. No `.str230_runtime` definition exists anywhere in the supplied executable files or the supplied team templates; workflow includes are at P `template-workflow/.iac_module_template.yml:42–111`.

**Impact:** With the supplied contents, merged configuration cannot resolve the reference, so plan/apply/audit acceptance cannot execute. The remote release was not fetched; a hidden remote definition must not be presumed.

**Fix:** Remove the stale reference if the team component replaces it, or restore the intended runtime definition and its include. Validate the fully expanded consumer configuration on the actual GitLab server and archive the merged YAML and CI lint result.

### B2 — Apply does not consume the plan that was generated (P1)

**Evidence:** P init `155` creates `${CI_PROJECT_DIR}/reports/terraform/plan.tfplan`; `159` hashes that file; artifacts `170–175` export it. P apply `128` runs `terraform -chdir=examples/basic apply ... tfplan`, which resolves to `examples/basic/tfplan`. No supplied step creates that path. P apply `136–137` downloads init artifacts, but does not verify their hash. It removes the root lock file at `82` and performs its own initialization at `121`.

**Impact:** Normal apply fails for missing plan. If an unrelated `tfplan` exists in the checkout, apply can use a different plan while audit reports the generated plan's hash. A hash field is not proof of the applied binary.

**Fix:** Apply only the downloaded absolute plan path, validate SHA-256 immediately before use, preserve the reviewed provider lock/override, and export the verified hash and apply exit code together. The team's apply component already has a useful checksum check at T apply `77–87`; adapt that contract to the pipeline's actual paths.

### B3 — Declared production environment can auto-approve (P1, confirmed locally)

**Evidence:** T gate `30` receives GATE_ENV, but `35–38,43,52,79` select scheduling and strictness using CI_COMMIT_BRANCH. P workflow `104` passes `$DEPLOY_ENV`, which defaults to empty at P `variables/.variables.yml:66`. P apply `33–50` selects fixed dev credentials and sandbox state independent of DEPLOY_ENV. Audit simply records supplied environment at T audit `104`.

**Reproduction:** Executed the exact gate script body with branch `dev`, GATE_ENV=`prod`; it returned 0 and logged `environment=prod ... outcome=APPROVED ... auto-approval for dev`. Branch `uat`, GATE_ENV=`prod` also follows UAT policy. Results are saved in `validation-results.json`.

**Fix:** Establish one trusted, validated mapping of deployment target to environment, subscription, backend and root. Reject empty, unknown or conflicting values. Choose both manual scheduling and approval thresholds from this mapping. Protect production credentials and deployment permissions so an edited branch cannot choose a lower policy for a production target. Enforce minimum policy floors independent of consumer inputs; reject zero, negative and nonnumeric minima.

### B4 — Gate queries the wrong MR, with no commit binding and unproven API authorization (P1)

**Evidence:** T gate `59–61` selects the first **open MR whose source branch is the deployment branch**. It does not use CI_MERGE_REQUEST_IID, target branch, project relationship, deployed SHA or merge commit. Workflow runs branch pipelines at P workflow `26–33`; after a feature MR merges into main/uat, that MR is normally merged and its source is the feature branch. T gate `70–75` uses JOB-TOKEN for approvals and description. T gate `71` counts array entries without validating schema, unique reviewers or eligibility.

**Impact:** Legitimate deployment can block because no such open MR exists. Conversely, approval evidence from an unrelated open deployment-branch MR can authorize the current commit. Two array entries alone do not prove two independent eligible reviewers. GitLab's documented job-token endpoint set does not establish support for the approvals endpoint; expect failure unless the installed server explicitly supports and permits it.

**Fix:** Resolve the reviewed MR associated with the deployed commit, enforce expected target/project and commit identity, reject ambiguity, validate response schema and distinct eligible approvers, and check approval reset/rule settings. For post-merge deployments persist trusted approval evidence bound to the reviewed commit/plan and revalidate according to promotion policy. Test with the actual GitLab version and an authorized least-privilege API credential or supported mechanism. Include timeouts and controlled retries; log blocked status on all error paths.

### B5 — Team apply can bypass approval stage; change-control component is not a substitute (P1)

**Evidence:** T `templates/terraform/apply/template.yml:49–57` declares needs only on plan and automatically applies on dev/uat/main. GitLab needs allows jobs to run once listed dependencies finish, ignoring unrelated stage barriers. P apply uses `dependencies` rather than needs, so this particular DAG bypass concerns library adoption, not the supplied legacy apply job. T `templates/compliance-gates/change-control-gate/template.yml:26–27,42–44,55` runs only on MR events and chooses file-risk class, requiring CHG only for high-risk changes. P workflow uses terraform-gate instead.

**Fix:** Make apply require a named, nonoptional successful approval job as well as plan. Align rules so the gate and apply appear on every relevant pipeline. Enforce protected deployment environments and include controls at a level an untrusted application change cannot remove. Keep risk classification supplemental; it does not replace STR-222 environment policy.

### B6 — “Immutable” upload target is sandbox state storage and draft policy is not administrator-proof (P1)

**Evidence:** P variables `49–52` explicitly labels audit account `kaastfssandbox00sa` a test value; P apply `48–50` uses that same account for tfstate. P workflow `56` passes that value directly. The separate Terraform audit account's separation checks `72–78` do not validate the runtime variable. P audit main `108–114` sets 730 days, locked=false. T audit `129–139` uploads successfully without verifying account identity, retention duration or policy status.

**Impact:** A successful upload proves neither separation nor locked retention. Draft is correct for the initial legal-review phase, but does not satisfy administrator-proof final acceptance. Terraform prevent_destroy protects Terraform operations, not direct Azure administration.

**Fix:** Deploy the dedicated shared-services account, wire its verified output into protected runtime configuration, and assert it differs from every state account. Keep draft until legal confirmation; then perform an approved lock operation, reconcile Terraform configuration/state, and retain legal and lock evidence. Test deletion and overwrite with an identity that actually has those data permissions; require an Azure immutability error, not any failure. Read-only or unauthorized identities cannot prove WORM enforcement.

### B7 — Audit record is neither an authoritative outcome nor guaranteed for every apply (P1)

**Evidence:** T audit `81–87` uses grep `Apply complete`, defaulting missing log to failure; `91–94` accepts `unavailable` hash. `56–62` makes apply and plan dependencies optional; `65–69` excludes MRs and restricts branches. T apply `95–104` captures a real exit code but never exports it. T audit `108` records the audit job's ID, not the apply job's ID. Pipeline workflow `50` puts audit in the same stage as apply, with needs (so the stage label itself is not the sequencing guarantee).

**Impact:** Terraform output can contain matching text despite failure; missing or skipped apply is falsely labeled failed apply. Audit identity/actor can refer to the separate recording job and person running/retrying it. Upload failure makes a job red after infrastructure already changed; it does not restore the missing evidence. Manual optional/skipped and failure-dependent DAG behavior require live testing. Cancellation, runner loss and artifact download failures can prevent the writer from running.

**Fix:** Persist a result manifest from the actual apply execution containing exit code, apply job ID, trigger and execution actor, actual environment/root, plan hash and timestamps; write explicit attempted/skipped/setup-failed states. Validate manifest provenance and schema. Use mandatory dependencies compatible with failed-apply artifact delivery, and prove scheduling on the installed GitLab server. Add durable intent/result delivery, retry and external reconciliation for interrupted applies and failed writes. Ensure missing terminal records alert and are recoverable without reapplying infrastructure.

### B8 — S010 schema cannot be signed off; key count is not validation (P1)

**Evidence:** T audit `99–117` produces actor, commit_sha, plan_hash, timestamp, environment, module, outcome, pipeline_id, job_id, project_path, mr_ref, checking only 11 keys. P `STR-230.md:13–15` explicitly says S010 was absent and proposes a different contract including pipeline_url and exit_code. That documentation describes runtime/query/verify scripts absent from this archive.

**Fix:** Obtain authoritative S010, reconcile and version a JSON schema, and validate required names, nonempty values, SHA formats, timestamps, outcome/exit-code consistency and job identity. Resolve contradictory documentation. Count of keys cannot prove the specified 11 fields. Document any permitted unknown/null values rather than accepting arbitrary missing evidence.

## Additional findings

**P2 — ServiceNow pattern accepts malformed larger identifiers.** T gate `20,95` searches unbounded `CHG[0-9]{7}`. Local mocked run accepted description `CHG123456789`. Confirm the process owner's exact format, enforce token boundaries and approved configuration. The story requires a valid number in the description; actual ServiceNow existence/status lookup is an additional policy decision, not presumed acceptance scope.

**P2 — Static credential guard and MSI selection need isolation.** P apply `58` exports ARM_CLIENT_SECRET, while T audit `74–77` rejects it. Jobs normally have separate shells, so the apply export alone does not propagate; inherited project/group ARM_CLIENT_SECRET would block audit. T audit `120–122` uses system identity login without explicitly selecting a user-assigned identity or checking the principal/subscription. Bind and test the intended runner MI, isolate Azure CLI state, check cloud/account identity, and avoid relying on inherited credential state. Least-privilege writer/reader roles at P audit main `116–133` are useful source controls but are not deployed evidence.

**P2 — TLS verification disabled and toolchain trust weakened.** P variables `123`, P init `15`, P apply `15` disable Git TLS verification; T plan/apply explicitly set false. Restore CA trust and verification in the legacy jobs. Pin component includes to verified immutable commits/digests, retain dependency locks, and verify catalog release provenance. P workflow `47,100` references remote `@0.1.2`; matching filenames inside a ZIP do not prove remote release bytes match the reviewed team source.

**P2 — Output retention coverage and confidentiality.** P apply `146` declares `reports/terraform/terraform-apply-output.txt` with no writer. Capture initialization and setup diagnostics too; precreate logs and finalize result metadata on handled errors. T plan `88–93` uses errexit/pipefail, so a failed plan can exit before the explicit PLAN_RC handler; the log still survives via artifacts. Handle errors deliberately when a precise audit status is required. Plans/JSON/logs can contain secrets; restrict artifact readers and job token access, and verify redaction without corrupting audit evidence.

**P2 — Destruction falls outside the same change evidence controls.** P destroy `123–124,140–141` allows manual auto-approved destroy, with no approval-count/CHG verification or structured audit. T destroy `143–150` creates then immediately applies a destroy plan after the manual click; it is not reviewed between those commands and has no equivalent audit record. Apply the same environment policy and immutable outcome recording to all infrastructure mutation paths. Include destroy-generated applies when validating “every infrastructure change.”

**P2 — Query correctness/completeness gaps.** T query `74` uses `>` rather than `>=` at next-day midnight, so an end date includes exactly midnight of the following day. `112–118` has no explicit continuation-token handling; verify full enumeration beyond Azure CLI's page limit and implement paging. `79–88` warns on missing fields and accepts them; valid JSON scalars/arrays and nonstring timestamps can produce exceptions downstream. Reject malformed records with explicit diagnostics and a completeness indicator; validate from<=to and actor/date edge cases. The script assumes an existing Azure login/cloud context; document and verify reviewer authentication and private DNS access.

**P2 — Test scaffolding is not release-ready.** P root `.gitlab-ci.yml:2–15` explicitly says do not merge and notes examples/basic is absent; workflow `24,61–111` retains STR_230 branch scaffolding. Publish consistent reviewed refs and exercise a real consumer containing the Terraform root before sign-off.

## Validation actually performed

1. Inspected both ZIP file inventories, executable YAML, Terraform, related component tests and documentation; compared embedded and separate team ZIP hashes.
2. Executed the verbatim gate script body in a local Bash process with controlled mock GitLab responses. Confirmed dev/prod environment bypass, UAT/prod policy mismatch and acceptance of an oversized CHG token. These are local script tests, not full GitLab scheduling tests.
3. Ran the team's real query script against its supplied fixtures. Counts: all=2, prod=1, failure=1, module network=1, October date range=2. This validates these local filters, not Azure enumeration or record creation.
4. Searched supplied sources for the unresolved runtime definition, actual plan producers/consumers, audit writer, policy settings and acceptance test implementations. The team's contract tests are mostly grep assertions: T gate test `39–63`; T audit test `37–58`. Gate injection is dormant at T gate test `25–30`; audit fixture failure at `68–69` is a prewritten JSON record, not a failed apply exercise.

No private GitLab CI lint, live API authorization, Terraform deployment, actual apply, WORM lock, Azure write/delete/overwrite or runner-failure exercise was performed. No claim of passing those tests is made. Local results accompany this report.

## Required acceptance tests before release

| Priority | Test | Required assertion |
|---|---|---|
| P1 | Expanded pipeline CI lint on real GitLab | All includes/reference targets resolve; component release matches reviewed source; required jobs present for every branch/source. |
| P1 | Real consumer plan/apply integration | Exact saved plan is downloaded, hashed, verified and applied; unrelated/stale tfplan and altered binary/hash provenance cannot substitute. |
| P1 | Environment policy table | sandbox/dev auto; UAT manual with 0 blocked and 1 accepted; prod manual with 0/1 blocked and 2 distinct eligible approvals accepted only with valid CHG. |
| P1 | Target mismatch/invalid config | Empty/unknown env, dev branch targeting prod, lowered thresholds and unauthorized production target all reject before mutation. |
| P1 | MR identity/provenance | Post-merge MR resolution works; wrong project/target/SHA, multiple candidate MRs, stale approvals and new commits reject. |
| P1 | API fault injection | 401/403/404/429/5xx, timeout, TLS failure, invalid JSON, null/wrong-type approved_by all block and log complete decision. Verify real token authorization. |
| P1 | DAG bypass | Delay/fail/do not play gate; apply cannot start. Repeat with team's needs-based apply and all manual/retry pipelines. |
| P1 | Apply outcomes and writer failures | Successful, nonzero, partial-change and setup-failed applies generate correct records; misleading `Apply complete` text does not override exit code. Skipped jobs do not become fake applies. |
| P1 | Failure/cancellation recovery | Artifact download failure, runner loss, canceled apply, audit outage, retry and duplicate delivery yield recoverable records without duplicate infrastructure execution. |
| P1 | Storage separation and identity | Actual audit account differs from all state accounts; correct MI writes; reviewer reads; writer cannot delete/manage policy; runner/reviewer private DNS connectivity works. |
| P1 | Draft/legal/lock transition | Draft 730-day provisioned state recorded; legal approval precedes lock; locked policy state and deployed configuration reconciled. |
| P1 | Locked WORM negative tests | Authorized writer/deleter cannot overwrite/delete retained test record; capture specific immutability error, unchanged hash and policy ID/state. Network/RBAC failure is not a pass. |
| P1 | S010 schema | Owner-approved schema validates real records for both success/failure, including actor, actual apply job and verified plan hash. |
| P2 | Artifact download/90 days | Download nonempty full output after success/failure; verify retention/access control in actual GitLab settings. |
| P2 | Compliance query | env/module/actor/date combined filters; inclusive date boundaries; malformed data; multi-page store; auth/network errors must not silently return incomplete success. |
| P1 | Destructive paths | Destroy/retry/promotion use same gate and immutable evidence; reviewed destroy plan cannot change after authorization. |

## External behavior checked against primary documentation

- [GitLab job token endpoint permissions](https://docs.gitlab.com/ci/jobs/ci_job_token/) and [MR approvals API](https://docs.gitlab.com/api/merge_request_approvals/): verify supported authentication on the installed GitLab version; do not infer approvals endpoint support from availability of CI_JOB_TOKEN.
- [GitLab needs](https://docs.gitlab.com/ci/yaml/#needs): listed dependencies determine DAG execution; stage placement alone does not protect a needs-based apply.
- [Azure container immutability configuration](https://learn.microsoft.com/en-us/azure/storage/blobs/immutable-policy-configure-container-scope): unlocked policy remains administratively changeable; locked retention is required for the claimed final protection.

**Disposition:** STR-222 has partial functional gate logic but fails integrated authorization assurance. STR-230 has partial capture, storage source and query functionality but fails reliable plan/apply/audit linkage and lacks locked-store acceptance evidence. Close B1–B8 and retain the required acceptance evidence before approving the stories.
