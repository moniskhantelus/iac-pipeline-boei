# STR-222 approval gates

All gate files are owned by this repository under templates/compliance-gates/terraform-gate.
The workflow includes template.yml locally with inputs; gate.py is canonical source and
embedded for consumers. No external component release is required.

Stage order is scan/lint → iac_init → iac_approval → iac_apply → iac_destroy.
Sandbox/dev gates run automatically. UAT/prod gates wait for manual action.
UAT requires one independent MR approval; prod requires two and a CHG number in the MR
description. API errors fail closed. Author approvals are excluded; MR head must match
pipeline commit. Set masked GATE_API_TOKEN with read_api access to the consumer project.
Protected variables must be available on the test branch. Keep one open MR from that
branch and run on its current source-head commit.

Apply and manual destroy require the gate and validate its decision artifact before setup.
Apply also verifies the saved plan checksum. These are real legacy jobs, not probes.
Keep the existing consumer project/file include to this repository's workflow and copy
all changed files to the same GitLab ref. Nested local includes use that project/ref.
Validate the merged configuration before running. Existing sandbox credentials/backend
and audit-account values remain test scaffolding to replace before production use.
