#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f ".env" ]]; then
  echo "Missing .env file. Copy .env.example to .env and fill values."
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required."
  exit 1
fi

get_env() {
  grep "^$1=" .env | cut -d= -f2- || true
}

get_secret_from_kv() {
  local vault_name="$1"
  local secret_name="$2"
  az keyvault secret show \
    --vault-name "${vault_name}" \
    --name "${secret_name}" \
    --query value \
    -o tsv \
    --only-show-errors
}

REVIEW_ENDPOINT_URL="${REVIEW_ENDPOINT_URL:-$(get_env REVIEW_ENDPOINT_URL)}"
REVIEW_ENDPOINT_API_KEY="${REVIEW_ENDPOINT_API_KEY:-$(get_env REVIEW_ENDPOINT_API_KEY)}"
JIRA_PROJECT_KEY="${JIRA_PROJECT_KEY:-$(get_env JIRA_PROJECT_KEY)}"
AZURE_KEY_VAULT_NAME="${AZURE_KEY_VAULT_NAME:-$(get_env AZURE_KEY_VAULT_NAME)}"
REVIEW_ENDPOINT_API_KEY_SECRET_NAME="${REVIEW_ENDPOINT_API_KEY_SECRET_NAME:-$(get_env REVIEW_ENDPOINT_API_KEY_SECRET_NAME)}"
TARGET_EPIC_KEY="${1:-}"
ALLOW_TRANSITION="${ORCHESTRATOR_TEST_ALLOW_TRANSITION:-false}"
ALLOW_DISPATCH="${ORCHESTRATOR_TEST_ALLOW_DISPATCH:-false}"
ALLOW_COMMENT="${ORCHESTRATOR_TEST_ALLOW_COMMENT:-false}"
DRY_RUN="${ORCHESTRATOR_TEST_DRY_RUN:-true}"

if [[ -z "${REVIEW_ENDPOINT_API_KEY}" && -n "${AZURE_KEY_VAULT_NAME}" && -n "${REVIEW_ENDPOINT_API_KEY_SECRET_NAME}" ]]; then
  REVIEW_ENDPOINT_API_KEY="$(get_secret_from_kv "${AZURE_KEY_VAULT_NAME}" "${REVIEW_ENDPOINT_API_KEY_SECRET_NAME}" 2>/dev/null || true)"
fi

if [[ -z "${REVIEW_ENDPOINT_URL}" || -z "${REVIEW_ENDPOINT_API_KEY}" || -z "${JIRA_PROJECT_KEY}" ]]; then
  echo "Missing REVIEW_ENDPOINT_URL, REVIEW_ENDPOINT_API_KEY, or JIRA_PROJECT_KEY."
  exit 1
fi

ORCHESTRATOR_URL="${REVIEW_ENDPOINT_URL%/review_epic}/execute_orchestrator_cycle"

if [[ -n "${TARGET_EPIC_KEY}" ]]; then
  REQUEST_BODY="$(jq -n \
    --arg project_key "${JIRA_PROJECT_KEY}" \
    --arg epic_key "${TARGET_EPIC_KEY}" \
    --arg dry_run "${DRY_RUN}" \
    --arg allow_transition "${ALLOW_TRANSITION}" \
    --arg allow_dispatch "${ALLOW_DISPATCH}" \
    --arg allow_comment "${ALLOW_COMMENT}" \
    '{
      project_key: $project_key,
      mode: "single_epic",
      epic_key: $epic_key,
      dry_run: ($dry_run == "true"),
      allow_transition_execution: ($allow_transition == "true"),
      allow_dispatch_execution: ($allow_dispatch == "true"),
      allow_comment_execution: ($allow_comment == "true")
    }' \
  )"
else
  REQUEST_BODY="$(jq -n \
    --arg project_key "${JIRA_PROJECT_KEY}" \
    --arg dry_run "${DRY_RUN}" \
    --arg allow_transition "${ALLOW_TRANSITION}" \
    --arg allow_dispatch "${ALLOW_DISPATCH}" \
    --arg allow_comment "${ALLOW_COMMENT}" \
    '{
      project_key: $project_key,
      mode: "batch",
      batch_limit: 5,
      dry_run: ($dry_run == "true"),
      allow_transition_execution: ($allow_transition == "true"),
      allow_dispatch_execution: ($allow_dispatch == "true"),
      allow_comment_execution: ($allow_comment == "true")
    }'
  )"
fi

echo "POST ${ORCHESTRATOR_URL}?code=***"
curl -sS \
  -X POST \
  -H "Content-Type: application/json" \
  "${ORCHESTRATOR_URL}?code=${REVIEW_ENDPOINT_API_KEY}" \
  -d "${REQUEST_BODY}" \
  | jq .
