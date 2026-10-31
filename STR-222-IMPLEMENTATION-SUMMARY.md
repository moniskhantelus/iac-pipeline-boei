# STR-222 implementation

The legacy workflow includes its own local approval template with component-style inputs.
Canonical files: templates/compliance-gates/terraform-gate/{template.yml,gate.py,README.md}.
Real apply depends on iac_gates_job and verifies its decision before Azure setup.
See docs/STR-222-approval-gates.md. No external repository files are loaded.
