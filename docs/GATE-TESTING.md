# Run the approval-gate test in GitLab

This kit tests the real corrected approval gate, its manual/automatic behavior, its API lookup and its decision artifact. The apply job is a probe using the same evidence guard as the legacy apply job. It never executes Terraform, Azure login or destroy. It does not test infrastructure provisioning or audit uploads.

1. Use a separate test project, or a dedicated branch in your existing legacy consumer project. Copy this kit's files to that checkout, including the hidden `.gitlab-ci.yml`. On an existing consumer test branch, this root file REPLACES the normal workflow include for this test. Do not append the normal legacy include to it. Keep the test branch unmerged.
2. Commit and push those files. This configuration creates pipelines only through GitLab's **Run pipeline** action (`web`), so a normal push does not run this kit. Other project-level automation or custom CI configuration settings are outside the kit; confirm the project actually uses this root `.gitlab-ci.yml`.
3. In GitLab, run CI Lint against this branch/configuration. Then select **Build → Pipelines → Run pipeline**, select the test branch, and choose `DEPLOY_ENV=dev`.
4. Expect `test → iac_init → iac_approval → iac_apply`. The unit test job runs 19 tests. `iac_gates_job` runs automatically, and `iac_apply_job` prints the probe PASS message after verifying its artifact.
5. Run another pipeline with `DEPLOY_ENV=uat`. The gate must wait for a manual click and apply must wait. Click the gate: with no open MR/approvals it must fail and apply must not run.
6. To test successful UAT/prod, open exactly one MR FROM this test branch TO a different branch in the same project. Keep it open and do not merge it. Add approvals to this MR. Do not push another commit after approvals; rerun a pipeline on the same source head. The gate compares the current branch commit to the MR head.
7. Set masked CI variable `GATE_API_TOKEN` to an appropriate project/group access token with `read_api` and permission to read the MR approvals endpoint. If the variable is protected, use a protected test branch or the variable will not be supplied. Never commit the token. The fallback job token may lack access; 401/403 is an expected fail-closed result in that case.
8. Repeat the matrix below. For every blocked/manual gate, confirm the probe does not execute. Download `gate-decision.json` and verify environment, pipeline/commit, approvals count, ticket and outcome. The gate validates format only; it does not call ServiceNow.

| DEPLOY_ENV | MR setup | Expected gate |
|---|---|---|
| sandbox/dev | None required | Automatic pass, then probe pass |
| uat | No approvals | Manual; blocks after click |
| uat | One independent approval | Manual; passes after click |
| prod | One independent approval + CHG1234567 in MR description | Manual; blocks after click |
| prod | Two independent approvals, no change number | Manual; blocks after click |
| prod | Two independent approvals + INC1234567 only | Manual; blocks after click |
| prod | Two independent approvals + CHG1234567 in MR description | Manual; passes after click, then probe pass |

The MR author does not count as an independent approver. GitLab edition/project settings must support the approvals endpoint. An unreachable API or missing/invalid token blocks UAT/prod. To simulate absent gate configuration, remove the local include on a test revision and run CI Lint: apply's required `iac_gates_job` dependency must make configuration invalid.

A passed probe confirms gate wiring and policy behavior, not the real legacy apply/audit integration. Before moving these changes into an infrastructure-running pipeline, correct the account/environment settings identified in the review and test against an isolated sandbox. This kit intentionally contains no real apply job or destroy job.
