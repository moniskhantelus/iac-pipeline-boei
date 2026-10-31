# IaC module pipeline — local approval gate integration

This pipeline uses only CI files owned by this repository. There are no external
`component:` or nested `project:` includes. Files keep a component-style template,
inputs and README layout under `templates/compliance-gates/terraform-gate/`.

The existing consumer include can continue pointing at
`/template-workflow/.iac_module_template.yml` in the mirrored pipeline repository
and its test branch. Copy all changed files to the same GitLab branch/revision;
nested local includes resolve in that pipeline repository, not the consumer checkout.
The root `.gitlab-ci.yml` also loads this workflow. There is no apply probe.

Stages retain scan/lint jobs, then `iac_init → iac_approval → iac_apply → iac_destroy`.
Sandbox/dev gates run automatically. UAT needs a manual gate plus one independent
MR approval. Prod needs a manual gate plus two independent MR approvals and a
CHG number in the MR description. API verification errors block the pipeline.
Apply downloads and verifies gate-decision.json for the same environment, commit
and pipeline, and applies the saved plan after verifying its checksum.

Set masked `GATE_API_TOKEN` (read_api) on the consumer project. Protected tokens
require a protected test branch. For the current branch-pipeline model, keep one
open MR FROM the consumer deployment/test branch, at its current head commit;
add the independent approvals and production CHG number there.

Branch mappings: sandbox_* → sandbox, dev_* → dev, uat_* → uat,
main/main_* → prod; STR_230/STR_230_* → sandbox test scaffolding.
Existing dev credentials, sandbox state settings and sandbox audit-account value
are retained test scaffolding. They must be replaced with the correct target and
separate audit account before production deployment. This integration executes
real Terraform jobs from the existing legacy pipeline.

The audit runner is implemented locally in scripts/audit.py and embedded by
iac/.audit_runtime.yml. It records ordinary apply/destroy outcomes without any
catalog component release. S010 schema agreement, audit account separation,
managed identity and live WORM acceptance remain deployment requirements.

Run local tests: `python3 -m unittest discover -s tests -v`.
In GitLab, validate the merged consumer configuration and run the test branch.
The gate and real apply must both be present; do not override gate rules or dependencies.
See [gate details](templates/compliance-gates/terraform-gate/README.md).
