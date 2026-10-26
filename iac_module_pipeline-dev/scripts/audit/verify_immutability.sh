#!/usr/bin/env bash
#
# verify_immutability.sh — tamper-proof acceptance test for the WORM audit store (AC4).
# Attempts to OVERWRITE and DELETE an existing audit record and asserts that Azure rejects both
# with an immutability error.
#
# IMPORTANT: this only truly PASSES against the LOCKED store (after the manual
# `az ... immutability-policy lock` step performed post legal sign-off). Against the
# unlocked/draft store the overwrite/delete will SUCCEED and the script correctly reports
# FAIL / not-yet-immutable. See docs/audit-worm-runbook.md.
#
# Usage: verify_immutability.sh [--blob <path>]
#
# Required environment: AUDIT_STORAGE_ACCOUNT, AUDIT_CONTAINER
#
set -euo pipefail

TARGET_BLOB=""
while [ $# -gt 0 ]; do
  case "$1" in
    --blob)
      TARGET_BLOB="${2:-}"
      shift 2
      ;;
    --help)
      echo "Usage: verify_immutability.sh [--blob <path>]"
      exit 0
      ;;
    *)
      echo "[ERROR] unknown flag: $1" >&2
      exit 2
      ;;
  esac
done

# Classify an az error string. Returns:
#   0 = immutability rejection (PASS)
#   1 = unrelated/other error (INCONCLUSIVE)
is_immutability_error() {
  case "$1" in
    *ImmutabilityPolicy* | *BlobImmutableDueToPolicy* | *immutab*) return 0 ;;
    *) return 1 ;;
  esac
}

# Pick the newest record if none supplied.
if [ -z "${TARGET_BLOB}" ]; then
  TARGET_BLOB="$(az storage blob list \
    --account-name "${AUDIT_STORAGE_ACCOUNT}" \
    --container-name "${AUDIT_CONTAINER}" \
    --auth-mode login \
    --query "sort_by([], &properties.creationTime)[-1].name" -o tsv 2>/dev/null || true)"
fi

if [ -z "${TARGET_BLOB}" ]; then
  echo "[INCONCLUSIVE] no record found to test against"
  exit 3
fi
echo "[INFO] Target record: ${TARGET_BLOB}"

TMP="$(mktemp)"
printf 'tamper-attempt' >"${TMP}"

# --- Attempt 1: OVERWRITE ---
echo "[INFO] Attempting overwrite (expected to be REJECTED on a locked store)..."
if OUT="$(az storage blob upload \
  --account-name "${AUDIT_STORAGE_ACCOUNT}" \
  --container-name "${AUDIT_CONTAINER}" \
  --name "${TARGET_BLOB}" \
  --file "${TMP}" \
  --overwrite \
  --auth-mode login \
  --no-progress 2>&1)"; then
  echo "[FAIL] overwrite SUCCEEDED — record is NOT immutable (store not locked?)"
  rm -f "${TMP}"
  exit 1
else
  if is_immutability_error "${OUT}"; then
    echo "[PASS] overwrite rejected by immutability policy"
  else
    echo "[INCONCLUSIVE] overwrite failed for an unrelated reason:"
    echo "${OUT}"
    rm -f "${TMP}"
    exit 3
  fi
fi

# --- Attempt 2: DELETE ---
echo "[INFO] Attempting delete (expected to be REJECTED on a locked store)..."
if OUT="$(az storage blob delete \
  --account-name "${AUDIT_STORAGE_ACCOUNT}" \
  --container-name "${AUDIT_CONTAINER}" \
  --name "${TARGET_BLOB}" \
  --auth-mode login 2>&1)"; then
  echo "[FAIL] delete SUCCEEDED — record is NOT immutable (store not locked?)"
  rm -f "${TMP}"
  exit 1
else
  if is_immutability_error "${OUT}"; then
    echo "[PASS] delete rejected by immutability policy"
  else
    echo "[INCONCLUSIVE] delete failed for an unrelated reason:"
    echo "${OUT}"
    rm -f "${TMP}"
    exit 3
  fi
fi

rm -f "${TMP}"
echo "[PASS] record is tamper-proof: both overwrite and delete were rejected by the immutability policy"
exit 0
