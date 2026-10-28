# Validation: pipeline-only scope

The branch changes iac-pipeline-boei only. The original components-main.zip is unchanged; its SHA-256 is 0ae47a2256c7207b1b54971d19351574314751c5de4f82fae15a2d6293fe5d6e.

- The 50 existing pipeline behavioral/command-flow tests cover environment mismatch, independent reviewers, MR/commit binding, API failures, saved-plan integrity, actual exit codes, immutable intent/delivery/replay behavior and recovery helpers. Local command-flow commands use fakes.
- Additional integration tests check the original ZIP digest, existing component references and pipeline-owned job overrides without loading modified component source.
- Seven embedded pipeline runtime copies are checked against runtime/control.py.
- Local YAML parsing/merge checks validate script strings, required plan/gate dependencies, override precedence and include paths. This is not GitLab server CI lint.
- Terraform formatting was checked. Provider initialization remains unverified because registry.terraform.io DNS was unavailable on this host.
- Private GitLab API/catalog behavior, real Azure identity/RBAC/networking, deployment outcomes, locked WORM negative tests and independent monitoring remain live acceptance requirements.

No team component source/release was changed. The earlier dual-repository fix proposal is superseded. See FIXES-AND-DEPLOYMENT.md for the pipeline integration contract and prerequisites.

Additional story-completion checks cover missing terminal evidence, exit-code/outcome disagreement, altered logs, cross-project/pipeline/job paths, malformed dates and combined query filters. See test-results.txt for the final suite count and docs/STR-222-STR-230-implementation.md for acceptance traceability.
