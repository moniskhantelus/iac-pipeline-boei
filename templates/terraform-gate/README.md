# terraform-gate

Environment-specific approval gate for Terraform pipelines (STR-222). One job, placed in a stage
before apply, that approves or blocks the run from the `environment` input and the merge
request's approvals and change ticket. It fails closed on every error and writes an audit record.

The job body is `scripts/gate.py` (Python 3 standard library only), embedded byte-for-byte in
`template.yml` and drift-tested by `tests/test_gate.py`.

## Usage

Today (from this repo):

```yaml
include:
  - project: 'kaas/pipelines/iac_module_pipeline'
    ref: <tag or branch>
    file: '/templates/terraform-gate/template.yml'
    inputs:
      job_name: iac_gates_job
      stage: iac_approval        # must run before the apply stage
      environment: $DEPLOY_ENV   # sandbox | dev | uat | prod
```

After the components team merges it (file copied to `templates/terraform-gate/template.yml`
of the components project, flat path so GitLab can resolve it):

```yaml
include:
  - component: $CI_SERVER_FQDN/<components project path>/terraform-gate@<version>
    inputs:
      job_name: iac_gates_job
      stage: iac_approval
      environment: $DEPLOY_ENV
```

## Inputs

| Input | Required | Default | Notes |
|---|---|---|---|
| `job_name` | no | `tf-gate` | Gate job name. |
| `stage` | no | `approve` | Must be before the apply stage. |
| `environment` | yes | none | `sandbox`, `dev`, `uat` or `prod`. Anything else fails closed. Pass a variable such as `$DEPLOY_ENV`. |
| `min_approvals_uat` | no | `"1"` | MR approvals required for uat, author excluded. |
| `min_approvals_prod` | no | `"2"` | MR approvals required for prod, author excluded. |
| `chg_pattern` | no | `"(CHG\|INC)[0-9]{7}"` | Regex searched in the MR description (prod only). Sample ServiceNow ticket: `INC8747347`. OQ-02: CHG vs INC needs process-owner confirmation. |
| `gate_image` | no | `registry.web.boeing.com/amp/docker-images/terraform/terraform-azure/ubi8minimal-azterraform/v1.9.2:26.04.15` | Needs `python3` only. |
| `gitlab_token` | no | `"$GATE_API_TOKEN"` | Sent as `PRIVATE-TOKEN`. Empty falls back to `CI_JOB_TOKEN`. |

## Required: GATE_API_TOKEN

`CI_JOB_TOKEN` cannot read the merge request and approvals API (it gets HTTP 401), so uat and
prod need a real token:

1. Create a **project access token** (or a **group access token** to cover several projects)
   with scope `read_api` and role Reporter or higher.
2. Add it as CI/CD variable `GATE_API_TOKEN` (Settings > CI/CD > Variables), **masked** and
   **protected**.
3. Protect the uat and prod branches (for example `uat*`, `main`), otherwise protected variables
   are not passed to their jobs and the gate falls back to `CI_JOB_TOKEN`.

If the token is missing or rejected (401/403), the job fails with
`set masked CI variable GATE_API_TOKEN = project/group access token with read_api`.
Every API call logs its endpoint and HTTP status; the token is never printed or written.

## Behavior

| environment | Job | Approves when |
|---|---|---|
| `sandbox` | runs automatically | always (no API call) |
| `dev` | runs automatically | always (no API call) |
| `uat` | manual, blocks the pipeline until run | >= `min_approvals_uat` approvals on the MR for this commit |
| `prod` | manual, blocks the pipeline until run | >= `min_approvals_prod` approvals on the MR for this commit AND a ticket matching `chg_pattern` in the MR description |
| anything else | not created (`when: never`) | never. `gate.py` also refuses it if run. |

The job uses `allow_failure: false`, so a BLOCKED gate stops the later stages.

Merge request rules for uat and prod:

- MR pipelines use `CI_MERGE_REQUEST_IID` directly. Branch pipelines look up open MRs with
  `source_branch` equal to the branch and a different target. None, or more than one, is BLOCKED
  (the open MRs are listed).
- The MR head sha must equal the pipeline commit (`CI_COMMIT_SHA`;
  `CI_MERGE_REQUEST_SOURCE_BRANCH_SHA` in merged-results pipelines). Otherwise BLOCKED:
  "approvals are for a different commit; re-run pipeline on MR head".
- Approvals come from `approved_by` of the approvals API; the MR author's approval never counts.
- API calls time out after 10 s and retry once on 5xx or no response. Any other failure blocks.

### Rules and the environment variable

The job sets `GATE_ENV` from the `environment` input and its rules match `$GATE_ENV`. Job-level
variables are available to that job's `rules:if`, and a value such as `$DEPLOY_ENV` (set by
`workflow:rules` variables in the consumer) is expanded before matching. If a GitLab instance
did not expand that nested reference, `GATE_ENV` would not match and the job would not be
created; in that case change the two rules to match `$DEPLOY_ENV` directly. Verify on the first
live run that the gate job appears with the expected `when` for each environment.

## Audit record

Every run writes `gate-decision.json` (artifact, `when: always`, kept 90 days):

```json
{
  "approvals_count": 2,
  "approvers": ["bob", "carol"],
  "branch": "main_STR301",
  "change_ticket": "INC8747347",
  "commit_sha": "7ebf18eb...",
  "environment": "prod",
  "job_id": "52356125",
  "mr_iid": 12,
  "outcome": "APPROVED",
  "pipeline_id": "1234567",
  "reason": "2 of 2 required approvals on MR !12, change ticket INC8747347",
  "required": 2,
  "timestamp": "2026-04-20T10:00:00Z"
}
```

and logs one line:

```text
[AUDIT] gate_decision environment=prod branch=main_STR301 commit_sha=... mr_iid=12 approvals=2/2 approvers=bob,carol change_ticket=INC8747347 outcome=APPROVED reason="..."
```

## Why not components terraform-gate@0.1.2

Observed in live runs of `kaas/pipelines/components` `compliance-gates/terraform-gate@0.1.2`
from `kaas/platform/infra-lab/azure_resource_group` (branches `sandbox_STR301`, `uat_STR301`,
`main_STR301`):

- `component:` include failed with "content not found": the template sits at a nested path,
  and GitLab only resolves `templates/<name>.yml` or `templates/<name>/template.yml`.
- The default image (curl-jq) could not be pulled: "requested access to the resource is denied".
- `CI_JOB_TOKEN` gets HTTP 401 `{"message":"401 Unauthorized"}` on
  `GET /projects/:id/merge_requests`.
- That 401 was reported only as a generic "GitLab API unreachable", hiding the cause.
- The decision was taken from the branch prefix instead of the environment.

## Tests

```text
python -m unittest tests.test_gate -v
```
