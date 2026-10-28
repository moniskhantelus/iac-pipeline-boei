# STR-222 and STR-230 implementation

Scope: **iac-pipeline-boei only**, using the team's existing components without changing their source, release or supplied ZIP. The workflow includes the original gate/audit components and then this repository's explicit job overrides. Code is implemented; production acceptance still requires the private-service evidence and business confirmations below.

## STR-222 — environment-specific approval before infrastructure changes

| Acceptance criterion | Executable implementation | Validation / remaining acceptance |
|---|---|---|
| Sandbox/dev automatic approval, environment logged | `runtime/control.py`: `config()` validates the target; `approval()` automatically approves sandbox/dev and emits structured audit output. `.iac_gates_job.yml` schedules those exact branches automatically. | Local tests verify automatic approval without an API call and reject prod/dev mismatches. Real consumer CI scheduling remains to be verified. |
| UAT manual approval and at least one MR approval | `iac/.iac_gates_job.yml` sets UAT to manual. `approval()` resolves the merged promotion MR associated with the deployment commit and requires one eligible, active, independent reviewer. | Tests cover zero blocked / one accepted and failure messages. Installed GitLab token/API/rule configuration needs live verification. |
| Production manual approval, two reviewers and valid change number | Main maps to prod in protected policy and job rules. `approval()` requires two distinct eligible reviewers and a whole `CHG` plus seven-digit token in the MR description. | Tests cover insufficient, duplicate, author/bot/inactive/unlisted reviewers and absent/oversized change tokens. Process owner must confirm the actual number format. |
| API failure blocks changes | `api()` has timeouts, bounded retry, strict HTTPS origin policy and no credential-forwarding redirects. `approval()` validates response types and fails closed. Apply rechecks approvals before mutation. | Tests cover API refusal and malformed approval data. Actual server/API authentication remains an acceptance test. |
| Every gate decision logged | `approval()` emits environment, approval count, change-record presence and APPROVED/BLOCKED outcome, and saves `control-evidence/gate-decision.json`. Configuration failures save `control-error.json`. | Local decision/error assertions. Confirm artifact retention and log access in actual GitLab. |
| Placeholder removed | The inherited gate script is replaced by the functional pipeline-owned runtime, not a no-op. | Integration tests and a local original-component/consumer merge check verify the replacement. |
| Gate before apply | Stages place `iac_approval` before `iac_apply`; apply also has mandatory `needs` on both `iac_init_job` and `iac_gates_job`. Its evidence is bound to the reviewed plan and deployment. | Contract tests verify mandatory dependencies; real GitLab DAG/manual scheduling remains to be exercised. |

The existing team component has branch-based behavior and an open-MR lookup that do not satisfy this pipeline's target/commit requirements. Those gaps are patched by **our job override**, not by modifying the component. Authorized reviewers, branch protections, protected deployment permissions and policy/variable ownership are configuration requirements that code cannot fabricate.

## STR-230 — permanent evidence for infrastructure changes

| Acceptance criterion | Executable implementation | Validation / remaining acceptance |
|---|---|---|
| Plan/apply outputs written and downloadable | `plan_command()` writes `control-evidence/plan.log`, `plan.txt`, saved `plan.tfplan` and `plan-manifest.json`. `apply_command()` writes `apply.log`, `result.json` and `audit.json`. Controlled jobs publish this directory with `when: always`. | Local command-flow tests exercise real wrappers with fake executables, including failed apply. Real artifact downloads still need verification. |
| Dedicated shared-services WORM account; draft 730 days before legal lock | `shared-services/audit/main.tf` provisions the separate account/container, private networking and writer/reader permissions. Separation preconditions reject known state accounts. `lock_retention` defaults false; locking requires the separately approved reference. | Terraform formatting checked; provider schema validation/deployment and legal confirmation remain external. Production runtime requires an actually locked 730-day policy. |
| Structured record on successful/failed apply | `apply_command()` writes durable intent before mutation, then uses the actual Terraform exit code in a finally block to build the exact 11-key record and terminal envelope. It uploads evidence conditionally to unique paths. | Command-flow tests verify both success and nonzero failure are recorded even when text misleadingly says “Apply complete.” Full S010 field mapping requires owner confirmation. |
| Immutable rejection proven | `runtime/verify_worm.py` refuses an unlocked/non-730-day policy, creates a unique record, requests overwrite/delete, requires Azure's immutability error, and checks unchanged bytes. It never locks a policy. | Verifier tests reject unrelated authorization failures. The actual locked-store acceptance test must run after legal approval, using an authorized test operator. |
| Failed applies recorded | Actual nonzero exit codes produce outcome `failure`, survive as operational artifacts and are delivered to the compliance store. Missing terminal evidence or inconsistent records fail the delivery job; a missing record is never treated as success. | Local failure, setup-failure, outage and evidence-integrity tests. Runner-loss/cancellation reconciliation needs operational acceptance. |
| Compliance query by environment/module/date/actor | `runtime/query_audit.py` implements all four filters plus outcome; Azure enumeration requests all pages and validates records. Inclusive end dates exclude the next day's midnight. | Local filter/date/malformed-record tests; real multi-page Azure query acceptance remains. |
| Separate retention | Controlled CI artifacts expire after 90 days; the audit store has an independent 730-day retention policy. Runtime rejects state/audit account reuse. | Source/runtime checks; actual GitLab and Azure policy evidence still required. |

### Record contract

The provisional 11 fields are `actor`, `commit_sha`, `plan_hash`, `timestamp`, `environment`, `module`, `outcome`, `pipeline_id`, `job_id`, `project_path`, `mr_ref`. The job ID is the **actual apply job**, not the subsequent delivery job. `result.json` separately preserves the actual exit code, operation, execution actor, log hash and attempt identity. This mapping is explicit rather than claiming an unavailable S010 specification was verified.

`validate_terminal()` is shared by normal delivery and operator replay. It rejects a mismatch between record/outcome/exit code, changed logs, missing evidence, invalid dates and a blob path bound to another project/pipeline/job. A missing terminal record is a failed delivery requiring investigation.

A process killed before it can publish a terminal result remains discoverable through its immutable intent. `runtime/reconcile.py` reports incomplete attempts as unknown; `runtime/replay_terminal.py` can deliver trusted saved records without rerunning infrastructure. It cannot infer a final infrastructure outcome that was never observed. Configure and test the independent monitoring/incident process before accepting “every apply” in production.

## Deployment prerequisites and sign-off

Use `FIXES-AND-DEPLOYMENT.md` and `control-config.example.json`. Actual target/account/identity IDs, reviewer IDs, private GitLab API credentials, a digest-pinned image, real Terraform root and reviewed state keys must be configured. The example contains deliberate placeholders and confirmation flags set false; inventing those values would produce an unsafe implementation.

Local tests are evidence of code behavior, not a deployed compliance sign-off. Retain live merged GitLab CI lint, API/authentication and DAG/manual-gate evidence; a real successful and failed apply; artifact downloads; Azure identity/RBAC/network checks; legal/S010 confirmation; locked-store rejection; and interruption/replay/reconciliation evidence before closing the stories.

No components repository changes, infrastructure deployment or retention lock are part of this source change.
