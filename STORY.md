Create a Tamper-Proof Record of Every Infrastructure Change
 Edit
 Add comment
Assign
More
Active
Share this issue
 Export
Details
Type:
 Story
Resolution:
Unresolved
Priority:
 Medium
Fix Version/s:
None
Affects Version/s:
None
Labels:
None
Epic Link:
(1) Infrastructure Pipeline (IaC Automation and GitOps Driven Provisioning)
Sprint:
STR Sprint 7
Story Points:
3
Release:
None
Project Supported:
None
Description
As a developer

I want every infrastructure change — successful or failed — to produce a permanent, tamper-proof audit record that I can query later

so that when a compliance audit asks "who changed what, when, and what happened," the answer is always available and trustworthy.

Why This Matters

The platform operates under FedRAMP High, which require immutable evidence of every infrastructure change. Today, two problems prevent this:

First, the pipeline is supposed to capture plan and apply outputs as downloadable artifacts, but the capture is broken — the output files referenced in the artifact configuration are never actually written. A developer looking for what happened in a past apply finds empty or missing files.

Second, there is no long-term, tamper-proof audit store. GitLab CI artifacts expire. If someone deletes a pipeline, the record disappears. For compliance purposes, the platform needs a write-once store where records cannot be modified or deleted — even by administrators — for the required retention period.

This story fixes both problems: it repairs the broken artifact capture so pipeline outputs are reliably saved for operational use, and it adds a permanent audit store where a structured record of every apply is written to immutable storage that no one can alter after the fact.

Acceptance Criteria

Artifact capture repaired: Plan output and apply output are reliably written to files and available as downloadable pipeline artifacts after every run. A developer can open any completed pipeline and download the full plan and apply output.
Immutable audit storage provisioned: A dedicated storage account is created in the shared-services environment, separate from Terraform state storage. It is configured for write-once, read-many (WORM) retention. The retention period is provisioned in draft/unlocked state initially and locked to the required duration (730 days) only after legal confirmation.
Structured audit record written on every apply: Every apply — whether it succeeds or fails — writes a structured JSON record to the immutable store. The record contains: who triggered the change, the commit SHA, the plan hash, a timestamp, the target environment, the target module, the apply outcome, and other fields needed for compliance queries (11 fields total as specified in S010).
Tamper-proof verified: Attempting to delete or modify a record in the locked audit store is rejected by Azure with an immutability error. This is confirmed as an acceptance test.
Failed applies are recorded: A failed apply writes an audit record with a failure outcome. The audit trail does not only capture successes — it captures everything.
Compliance query tool: A query script exists that allows a compliance reviewer to search the audit store by environment, module, date range, or actor and retrieve matching records.
Retention separation: Pipeline artifacts are retained for 90 days for operational convenience. The immutable audit store is the compliance record of truth with its own retention policy.
Dependencies

plan hash must be generated and available for inclusion in the audit record)
managed identity must be in place for the pipeline to authenticate to the audit storage account)
legal confirmation of the exact retention period before the WORM policy is locked
Traceability

Blueprint v0.1 Epic-01, Stage 10 (WORM audit log with structured JSON record)
Blueprint v0.1 Epic-01 acceptance criteria (every apply produces an immutable audit log entry)
FedRAMP High / DoD SRG IL4-5 (immutable change records required)
Amends S010 (adds repair of broken artifact capture as a prerequisite not covered in original story)
