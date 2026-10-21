#!/usr/bin/env bash
# Run only against an approved, already LOCKED acceptance-test container.
# Uses the operator's existing az login; does not create/change/lock any policy.
set -euo pipefail
: "${AUDIT_RESOURCE_GROUP:?}" "${AUDIT_STORAGE_ACCOUNT:?}"
container="${AUDIT_CONTAINER:-audit}"
state=$(az storage container immutability-policy show --account-name "$AUDIT_STORAGE_ACCOUNT" --container-name "$container" --resource-group "$AUDIT_RESOURCE_GROUP" --query state -o tsv)
[[ "$state" == Locked ]] || { echo 'Policy is not Locked; test refused.' >&2; exit 1; }
test_dir=$(mktemp -d)
trap 'rm -rf "$test_dir"' EXIT
name="acceptance/$(date -u +%Y%m%dT%H%M%SZ)-${RANDOM}-${RANDOM}.json"
printf '{"test":"STR-230 WORM acceptance"}\n' > "$test_dir/record.json"
common=(--account-name "$AUDIT_STORAGE_ACCOUNT" --container-name "$container" --auth-mode login --name "$name" --only-show-errors)
az storage blob upload "${common[@]}" --file "$test_dir/record.json" --overwrite false
# Use a test operator with data delete/write permission: authorization failures do not prove WORM.
for operation in overwrite delete; do
  if [[ "$operation" == overwrite ]]; then
    printf '{"modified":true}\n' > "$test_dir/record.json"
    command=(az storage blob upload "${common[@]}" --file "$test_dir/record.json" --overwrite true)
  else
    command=(az storage blob delete "${common[@]}")
  fi
  if "${command[@]}" > "$test_dir/result" 2>&1; then
    echo "FAIL: $operation unexpectedly succeeded" >&2; exit 1
  fi
  if ! grep -Eq 'BlobImmutableDueToPolicy|BlobImmutableDueToLegalHold' "$test_dir/result"; then
    cat "$test_dir/result" >&2; echo 'FAIL: rejection did not prove immutability' >&2; exit 1
  fi
  echo "PASS: $operation rejected by Azure immutability policy"
done
echo "Retained test evidence blob: $name"
