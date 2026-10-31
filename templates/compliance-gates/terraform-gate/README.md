# Terraform approval gate (STR-222)

Owned by this repository. Included through `include: local` with inputs, not a catalog component.
Canonical runtime: `gate.py`; embedded in `template.yml` so consumer checkouts need no helper files.

Sandbox/dev approve automatically. UAT waits for manual approval and requires at least one
independent MR approval. Prod waits for manual approval and requires at least two independent
MR approvals plus a bounded CHG number in the MR description. API errors block the gate.
Set masked `GATE_API_TOKEN` with read_api access to the consumer project's approvals endpoint.
A protected variable requires a protected test branch. Keep one open MR from the deployed
branch, on the same source-head commit; postmerge deployment requires a separate MR association design.

`template-workflow/.iac_module_template.yml` configures job `iac_gates_job` in `iac_approval`.
Real apply has mandatory dependencies on the plan and gate and validates gate-decision.json.
Do not override its gate dependency, rules, or allow_failure. Gate has no needs so prior scans
and plan must finish first. Invalid environments fail closed.
