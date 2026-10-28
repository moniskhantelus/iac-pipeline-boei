# Scope correction — October 28, 2026

The fixes apply to iac-pipeline-boei only. The previous dual-repository proposal is superseded.

- Removed the modified components-main source tree and component-publication example.
- Restored components-main.zip exactly to the original supplied bytes; no team component source or release is changed.
- Kept the original component review as evidence of dependencies and weaknesses.
- Included the team's existing terraform-gate and audit-record release at the original 0.1.2 reference.
- Added explicit pipeline-owned job overrides, loaded after those components, for verified environment policy, approval/plan linkage, actual apply outcomes and durable audit delivery.
- Retained this repository's saved-plan, identity isolation, storage provisioning, failure handling, query and recovery fixes.
- Updated setup instructions and added integration tests checking archive provenance and consumer-only scope.

A local merge check against the original supplied component YAML verified override precedence, mandatory plan/gate dependencies, functional gate logic and delivery of terminal records instead of log parsing. Actual published catalog contents and GitLab server CI lint remain external acceptance checks. No cloud resources were deployed or retention policy locked.
