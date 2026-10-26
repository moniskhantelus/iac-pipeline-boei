# STR-222 — environment-specific approval gate

## Behavior

| Target branch | Environment | Job scheduling | Checks when executed |
|---|---|---|---|
| `sandbox` / `sandbox_*` | sandbox | Automatic | Explicit auto-approval log; no API needed |
| `dev` / `dev_*` | dev | Automatic | Explicit auto-approval log; no API needed |
| `uat` / `uat_*` | UAT | Blocking manual | At least one distinct non-author MR approver |
| `main` | production | Blocking manual | At least two distinct non-author MR approvers AND a matching ServiceNow reference in the MR description |
| Anything else | unknown | Blocking manual | Refused; no fallback to a lower environment |

The supplied ZIP already had `iac_approval` before `iac_apply`; this order is retained and tested. Apply has no `needs` shortcut and waits for the blocking gate stage. Its `dependencies: [iac_init_job]` only selects downloaded artifacts; it does not bypass the gate. The placeholder has been replaced entirely with real logic. Existing STR-230 plan/apply/audit/storage code is unchanged.

For UAT/production, pressing Play starts verification, NOT unconditional approval. Insufficient approvals or a missing production reference fail the gate. After correcting the MR, retry the gate. A manual job that has not been started is a blocking wait, not a recorded approval decision. API and configuration errors fail closed. Duplicate approval identities count once and the MR author does not count.

## ServiceNow rule confirmed for this implementation

The user supplied `INC8747347` as a dummy example. The default syntax rule is uppercase `INC` plus exactly seven ASCII digits, with alphanumeric/underscore boundaries rejected (`XINC8747347` and `INC87473478` do not match). The code checks the MR description only. It does not contact ServiceNow or prove that the referenced record exists, is approved, or is classified as a change rather than an incident. The service owner must confirm that the supplied INC format meets Boeing's change-control policy. If policy specifies another format, set the protected `SERVICENOW_CHANGE_PATTERN` variable (for example `CHG[0-9]{7}`). Invalid patterns block the gate.

## GitLab API configuration

Set masked `APPROVAL_GATE_TOKEN` with `read_api` access to the consumer project and its MR approvals. Prefer a dedicated project access token with the least role allowed by your GitLab version/license. Protect the token for production and rotate it. The gate intentionally does not assume `CI_JOB_TOKEN` can access the approvals endpoint. Verify the installed GitLab tier/version exposes this API.

The gate uses `CI_API_V4_URL`, `CI_PROJECT_ID`, `CI_COMMIT_SHA`, and GitLab branch/MR context. Python 3 is required in the existing Terraform image. HTTPS verification remains enabled, independently of existing `GIT_SSL_NO_VERIFY` elsewhere. For a private CA, configure `APPROVAL_GATE_CA_FILE` as a GitLab file variable containing the trusted CA bundle. API requests have a 20-second timeout and refuse redirects; non-2xx responses, invalid JSON, missing tokens, malformed approvals and TLS/network failures all block. Tokens and MR descriptions are not logged.

For branch pipelines (the existing workflow), the gate uses the commit-associated MR endpoint, requires exactly one merged MR targeting the current branch/project, then requires this pipeline SHA to equal the MR's merge SHA, squash SHA, or final head SHA (fast-forward merges). Direct pushes without a matching reviewed MR, ambiguous matches, and an older commit merely included within an MR are refused. Tags/unknown branches do not obtain implicit approval.

The code also supports exact-head opened MR contexts when a consuming workflow enables them, using the MR target branch for environment classification. The supplied workflow remains branch-based: this change does not enable MR deployments or merged-result/merge-train pipelines. Synthetic merge-result SHAs are refused by the exact-head check. Validate any custom promotion workflow before enabling it.

Configure GitLab to reset approvals when new commits are pushed, disallow author/self approvals, restrict approvers to authorized reviewers, and protect production branches/runners/template refs. The API count represents current recorded identities; reviewer eligibility and approval reset policies belong in GitLab project governance. The gate checks current state at the time it runs; it does not continuously monitor later approval withdrawals. Do not override gate jobs, stage order, environment classification or apply scheduling in consumer CI. Use GitLab policy enforcement if project owners must be unable to bypass templates.

References:
- https://docs.gitlab.com/api/merge_request_approvals/
- https://docs.gitlab.com/api/commits/#list-merge-requests-associated-with-a-commit
- https://docs.gitlab.com/api/merge_requests/

## Audit evidence

Each executed gate prints JSON and saves `reports/approval/gate-decision.json` as an always-uploaded, 90-day artifact. Fields include environment, approvals found/required, reference presence, outcome, reason, MR IID, commit SHA, and pipeline ID. Unverifiable API values are null, rather than falsely reported as zero. For automatic lower-environment decisions, count is zero and reference presence false because these checks are not required. The reason explicitly identifies auto-approval. Blocked logs identify both unmet production conditions when both can be evaluated.

Gate artifacts are operational evidence; STR-230's immutable apply audit remains unchanged. No policy has been locked or retention changed.

## Publication and testing

The supplied archive includes temporary STR_230 scaffolding: root `.gitlab-ci.yml`, a workflow exception for `STR_230`, and cross-project include refs pinned to `STR_230`. These are preserved. Publish changed files to the ref actually used for testing, or update ALL include refs consistently to your chosen test branch/commit. Merely uploading the gate to another branch will not activate it. Before merging to dev, remove the pre-existing temporary scaffolding as its comments direct. This template library has no `examples/basic`; use a consumer project for live plan/gate/apply tests. The `STR_230` branch is intentionally an UNKNOWN deployment target and will block if it reaches the gate.

Run:

```sh
python3 -m unittest discover -s tests -v
```

Local validation: 16 tests pass (11 gate tests plus 5 retained audit tests). Gate cases include lower-env auto-approval, UAT threshold, production approval/reference combinations, duplicate/self approval exclusion, mismatched/missing/ambiguous MRs, unknown environments, missing token, HTTP 401/403/404/429/500, malformed payloads, timeout failures, JSON artifact/exit status, runtime-source parity and stage order.

Live acceptance in Boeing remains required:
1. GitLab CI Lint the fully merged consumer configuration (all private includes available).
2. Sandbox/dev pipeline: confirm gate starts automatically and logs its detected environment.
3. UAT: confirm manual blocking; zero approvals fails with found/required counts; one independent approval succeeds on retry.
4. Production: check zero/one/two approvals, missing/invalid INC reference, and valid reference plus two reviewers. No apply may start for blocked/waiting gates.
5. Use an invalid/revoked test API token to prove failure blocks apply. Test trusted CA configuration on the real runner.
6. Confirm the gate resolves the actual merge/squash/fast-forward commit used by the consumer's deployment model and logs the correct MR.

A syntactically valid dummy INC number is acceptable for a non-production test of the parser only; it is not evidence of an approved production change.
