# STR-222 implementation summary

Implemented against the supplied iac_module_pipeline-STR_230.zip, retaining its existing STR-230 changes and temporary branch scaffolding.

Changed files:
- iac/.iac_gates_job.yml: replaces placeholder with embedded functional gate, environment-specific automatic/manual scheduling, fail-closed behavior and 90-day decision artifact.
- scripts/approval_gate.py: readable source, GitLab API verification, exact deployment-commit/MR association, unique non-author reviewer counts, production INC reference validation.
- tests/test_approval_gate.py: 11 tests covering policy matrix, API errors, malformed responses, missing/ambiguous/stale MRs, independent approvals and wiring.
- docs/STR-222-approval-gates.md and README.md: configuration, deployment and acceptance instructions.

The supplied workflow already orders iac_approval before iac_apply; retained and regression-tested. No changes to apply, plan, audit storage, WORM retention, scan jobs or include refs.

Default ServiceNow syntax: INC plus seven digits, based on the user's dummy INC8747347. Checks format/presence in description, not live ServiceNow status.

Validation: all 16 tests pass, including all 5 existing audit tests. YAML and embedded job syntax checked locally. Live private GitLab CI lint and pipeline acceptance remain pending.

Required configuration: masked read_api APPROVAL_GATE_TOKEN; trusted CA file if required; GitLab reviewer/reset/protected-branch settings; consistent publication to the actual include ref. Exact INC policy semantics require owner confirmation. Unknown deployment branches fail closed, including the inherited STR_230 scaffold branch.

Nothing pushed or deployed; no WORM policy locked.
