# STR-230 implementation

Jobs use this repository's scripts/audit.py embedded by iac/.audit_runtime.yml.
There is no catalog audit-record dependency. Apply captures Terraform output and publishes
a record for ordinary success/failure. Init retains the saved plan and checksum.
The retained sandbox audit-account value is test scaffolding; supply a separate account,
managed identity and approved retention before production use. The schema remains
provisional pending authoritative S010 confirmation. Live WORM tests remain required.
