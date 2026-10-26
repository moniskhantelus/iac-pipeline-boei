#!/usr/bin/env bash
#
# query_audit.sh — search the immutable (WORM) audit store for infrastructure-change records.
# A compliance reviewer can filter by environment, module, date range, and actor, then list or
# download matching records. Read-only; never prints secrets.
#
# Required environment: AUDIT_STORAGE_ACCOUNT, AUDIT_CONTAINER
#
set -euo pipefail

usage() {
  cat <<'EOF'
Usage: query_audit.sh [options]

  --environment <env>    filter by environment (blob path prefix)       [optional]
  --module <name>        filter by module (blob path prefix segment)    [optional]
  --from <YYYY-MM-DD>     records with timestamp >= this date (UTC)      [optional]
  --to   <YYYY-MM-DD>     records with timestamp <= this date (UTC)      [optional]
  --actor <login>        filter by actor field                          [optional]
  --download <dir>       download matching records into <dir>           [optional]
  --help                 print this usage and exit 0

Environment:
  AUDIT_STORAGE_ACCOUNT  WORM storage account (e.g. strataaudit)
  AUDIT_CONTAINER        blob container (e.g. audit-records)
EOF
}

# IDENTICAL sanitize rule to write_audit_record.sh so sanitized record paths still match.
sanitize_segment() { printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '-'; }

ENVIRONMENT=""
MODULE=""
FROM=""
TO=""
ACTOR=""
DOWNLOAD_DIR=""

while [ $# -gt 0 ]; do
  case "$1" in
    --environment)
      ENVIRONMENT="${2:-}"
      shift 2
      ;;
    --module)
      MODULE="${2:-}"
      shift 2
      ;;
    --from)
      FROM="${2:-}"
      shift 2
      ;;
    --to)
      TO="${2:-}"
      shift 2
      ;;
    --actor)
      ACTOR="${2:-}"
      shift 2
      ;;
    --download)
      DOWNLOAD_DIR="${2:-}"
      shift 2
      ;;
    --help)
      usage
      exit 0
      ;;
    *)
      echo "[ERROR] unknown flag: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

validate_date() {
  # Accept strictly YYYY-MM-DD.
  case "$1" in
    [0-9][0-9][0-9][0-9]-[0-1][0-9]-[0-3][0-9]) return 0 ;;
    *) return 1 ;;
  esac
}
if [ -n "${FROM}" ] && ! validate_date "${FROM}"; then
  echo "[ERROR] --from must be YYYY-MM-DD" >&2
  exit 2
fi
if [ -n "${TO}" ] && ! validate_date "${TO}"; then
  echo "[ERROR] --to must be YYYY-MM-DD" >&2
  exit 2
fi

# Build the server-side list prefix from sanitized env/module (same rule as the writer).
PREFIX=""
if [ -n "${ENVIRONMENT}" ]; then
  ENV_SEG="$(sanitize_segment "${ENVIRONMENT}")"
  PREFIX="${ENV_SEG}/"
  if [ -n "${MODULE}" ]; then
    MODULE_SEG="$(sanitize_segment "${MODULE}")"
    PREFIX="${ENV_SEG}/${MODULE_SEG}/"
  fi
fi

echo "[INFO] Listing records in ${AUDIT_CONTAINER} (prefix='${PREFIX}')"
LIST_ARGS=(--account-name "${AUDIT_STORAGE_ACCOUNT}"
  --container-name "${AUDIT_CONTAINER}"
  --auth-mode login
  --query "[].name" -o tsv)
if [ -n "${PREFIX}" ]; then
  LIST_ARGS+=(--prefix "${PREFIX}")
fi

BLOBS="$(az storage blob list "${LIST_ARGS[@]}")"

if [ -z "${BLOBS}" ]; then
  echo "[INFO] no records found"
  exit 0
fi

printf '%-60s %-22s %-10s %-10s %-10s %s\n' "BLOB" "TIMESTAMP" "ENVIRONMENT" "MODULE" "OUTCOME" "ACTOR"
MATCHED=0
while IFS= read -r blob; do
  [ -n "${blob}" ] || continue

  # Date-range filter uses the timestamp embedded in the blob name (avoids a download).
  # Blob name: <env>/<module>/<TS>-<pipeline>-<job>.json ; TS = YYYY-MM-DDTHH:MM:SSZ
  base="${blob##*/}"
  ts_date="${base%%T*}"
  if [ -n "${FROM}" ] && [ "${ts_date}" "<" "${FROM}" ]; then continue; fi
  if [ -n "${TO}" ] && [ "${ts_date}" ">" "${TO}" ]; then continue; fi

  # For actor (and to render the row), read the JSON record.
  RECORD="$(az storage blob download \
    --account-name "${AUDIT_STORAGE_ACCOUNT}" \
    --container-name "${AUDIT_CONTAINER}" \
    --name "${blob}" \
    --auth-mode login \
    --no-progress -o tsv --query content 2>/dev/null || true)"

  if [ -z "${RECORD}" ]; then
    continue
  fi

  r_actor="$(printf '%s' "${RECORD}" | jq -r '.actor // ""')"
  if [ -n "${ACTOR}" ] && [ "${r_actor}" != "${ACTOR}" ]; then
    continue
  fi

  r_ts="$(printf '%s' "${RECORD}" | jq -r '.timestamp // ""')"
  r_env="$(printf '%s' "${RECORD}" | jq -r '.environment // ""')"
  r_mod="$(printf '%s' "${RECORD}" | jq -r '.module // ""')"
  r_out="$(printf '%s' "${RECORD}" | jq -r '.outcome // ""')"

  printf '%-60s %-22s %-10s %-10s %-10s %s\n' \
    "${blob}" "${r_ts}" "${r_env}" "${r_mod}" "${r_out}" "${r_actor}"
  MATCHED=$((MATCHED + 1))

  if [ -n "${DOWNLOAD_DIR}" ]; then
    mkdir -p "${DOWNLOAD_DIR}/$(dirname "${blob}")"
    printf '%s' "${RECORD}" >"${DOWNLOAD_DIR}/${blob}"
  fi
done <<<"${BLOBS}"

if [ "${MATCHED}" -eq 0 ]; then
  echo "[INFO] no records matched the given filters"
fi
exit 0
