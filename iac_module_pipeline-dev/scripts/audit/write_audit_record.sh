#!/usr/bin/env bash
#
# write_audit_record.sh — assemble a structured JSON audit record for an infrastructure change
# and upload it to the immutable (WORM) audit store. Called from the apply job's trap on EVERY
# apply, success or failure. Never prints secrets.
#
# Usage: write_audit_record.sh <success|failure>
#
# Required environment:
#   AUDIT_STORAGE_ACCOUNT, AUDIT_CONTAINER   (from variables/.variables.yml)
# Consumed CI environment (all optional; empty -> safe default):
#   GITLAB_USER_LOGIN, CI_COMMIT_SHA, PLAN_HASH, APPLIED_PLAN_HASH, CI_COMMIT_BRANCH,
#   CI_PROJECT_NAME, CI_PIPELINE_ID, CI_PIPELINE_URL, CI_JOB_ID, TF_VERSION
#
set -euo pipefail

OUTCOME="${1:?outcome arg (success|failure) required}"
case "${OUTCOME}" in
  success | failure) ;;
  *)
    echo "[ERROR] invalid outcome '${OUTCOME}' (expected success|failure)" >&2
    exit 2
    ;;
esac

# environment = branch prefix (value before first underscore); never empty.
ENVIRONMENT="${CI_COMMIT_BRANCH%%_*}"
ENVIRONMENT="${ENVIRONMENT:-unknown}"
MODULE="${CI_PROJECT_NAME:-unknown}"
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

# plan_hash is the single most important compliance field. If the init-stage hand-off is
# missing/empty, still write the record (resilience) with plan_hash:"" plus a grep-able marker.
if [ -z "${PLAN_HASH:-}" ]; then
  echo "[AUDIT-WARN] plan_hash empty at apply time — reviewed-plan hash hand-off gap (see runbook §11)"
fi

# Sanitize the two values that become blob-PATH segments. The JSON record keeps the ORIGINAL
# unsanitized values (via jq --arg); only the blob path uses the sanitized forms. query_audit.sh
# applies the IDENTICAL rule so prefixes still match.
sanitize_segment() { printf '%s' "$1" | tr -c 'A-Za-z0-9._-' '-'; }
ENV_SEG="$(sanitize_segment "${ENVIRONMENT}")"
MODULE_SEG="$(sanitize_segment "${MODULE}")"

# Build the record with jq (never string concatenation — avoids quoting/injection bugs).
# EXACTLY the 11 mandated fields + the additive integrity field applied_plan_hash.
#   pipeline_id / pipeline_url / terraform_version / schema_version are marked
#   'pending S010 reconciliation' — their exact names/semantics await S010 confirmation.
RECORD="$(jq -n \
  --arg actor "${GITLAB_USER_LOGIN:-unknown}" \
  --arg commit_sha "${CI_COMMIT_SHA:-}" \
  --arg plan_hash "${PLAN_HASH:-}" \
  --arg applied_plan_hash "${APPLIED_PLAN_HASH:-}" \
  --arg timestamp "${TS}" \
  --arg environment "${ENVIRONMENT}" \
  --arg module "${MODULE}" \
  --arg outcome "${OUTCOME}" \
  --arg pipeline_id "${CI_PIPELINE_ID:-}" \
  --arg pipeline_url "${CI_PIPELINE_URL:-}" \
  --arg terraform_version "${TF_VERSION:-}" \
  --arg schema_version "1.0" \
  '{
     actor:$actor,
     commit_sha:$commit_sha,
     plan_hash:$plan_hash,
     applied_plan_hash:$applied_plan_hash,
     timestamp:$timestamp,
     environment:$environment,
     module:$module,
     outcome:$outcome,
     pipeline_id:$pipeline_id,
     pipeline_url:$pipeline_url,
     terraform_version:$terraform_version,
     schema_version:$schema_version
   }')"

# Collision-proof blob name (retry-safe): CI_JOB_ID differs on a GitLab retry of the same
# pipeline, so a retried apply writes a DISTINCT blob instead of colliding with a locked policy.
BLOB_PATH="${ENV_SEG}/${MODULE_SEG}/${TS}-${CI_PIPELINE_ID:-nopipe}-${CI_JOB_ID:-nojob}.json"

TMP="$(mktemp)"
printf '%s' "${RECORD}" >"${TMP}"

echo "[INFO] Writing audit record to ${AUDIT_CONTAINER}/${BLOB_PATH} (outcome=${OUTCOME})"
az storage blob upload \
  --account-name "${AUDIT_STORAGE_ACCOUNT}" \
  --container-name "${AUDIT_CONTAINER}" \
  --name "${BLOB_PATH}" \
  --file "${TMP}" \
  --auth-mode login \
  --no-progress

rm -f "${TMP}"
echo "[INFO] Audit record written."
