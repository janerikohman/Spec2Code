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

JIRA_BASE_URL="${JIRA_BASE_URL:-$(get_env JIRA_BASE_URL)}"
JIRA_EMAIL="${JIRA_EMAIL:-$(get_env JIRA_EMAIL)}"
JIRA_API_TOKEN="${JIRA_API_TOKEN:-$(get_env JIRA_API_TOKEN)}"
JIRA_PROJECT_KEY="${JIRA_PROJECT_KEY:-$(get_env JIRA_PROJECT_KEY)}"
AZURE_KEY_VAULT_NAME="${AZURE_KEY_VAULT_NAME:-$(get_env AZURE_KEY_VAULT_NAME)}"
JIRA_EMAIL_SECRET_NAME="${JIRA_EMAIL_SECRET_NAME:-$(get_env JIRA_EMAIL_SECRET_NAME)}"
JIRA_API_TOKEN_SECRET_NAME="${JIRA_API_TOKEN_SECRET_NAME:-$(get_env JIRA_API_TOKEN_SECRET_NAME)}"
REVIEW_ENDPOINT_URL="${REVIEW_ENDPOINT_URL:-$(get_env REVIEW_ENDPOINT_URL)}"
REVIEW_ENDPOINT_API_KEY="${REVIEW_ENDPOINT_API_KEY:-$(get_env REVIEW_ENDPOINT_API_KEY)}"
REVIEW_ENDPOINT_API_KEY_SECRET_NAME="${REVIEW_ENDPOINT_API_KEY_SECRET_NAME:-$(get_env REVIEW_ENDPOINT_API_KEY_SECRET_NAME)}"

LIVE_MODE=false
if [[ "${1:-}" == "--live" ]]; then
  LIVE_MODE=true
  shift
fi

if [[ -z "${JIRA_EMAIL}" && -n "${AZURE_KEY_VAULT_NAME}" && -n "${JIRA_EMAIL_SECRET_NAME}" ]]; then
  JIRA_EMAIL="$(get_secret_from_kv "${AZURE_KEY_VAULT_NAME}" "${JIRA_EMAIL_SECRET_NAME}" 2>/dev/null || true)"
fi
if [[ -z "${JIRA_API_TOKEN}" && -n "${AZURE_KEY_VAULT_NAME}" && -n "${JIRA_API_TOKEN_SECRET_NAME}" ]]; then
  JIRA_API_TOKEN="$(get_secret_from_kv "${AZURE_KEY_VAULT_NAME}" "${JIRA_API_TOKEN_SECRET_NAME}" 2>/dev/null || true)"
fi

if [[ -z "${JIRA_BASE_URL}" || -z "${JIRA_EMAIL}" || -z "${JIRA_API_TOKEN}" || -z "${JIRA_PROJECT_KEY}" ]]; then
  echo "Missing Jira values. Need JIRA_BASE_URL, JIRA_EMAIL, JIRA_API_TOKEN, JIRA_PROJECT_KEY."
  exit 1
fi

SUMMARY="${1:-[Agent Demo] Epic intake check $(date +%Y-%m-%d\ %H:%M)}"

auth_b64="$(printf '%s:%s' "${JIRA_EMAIL}" "${JIRA_API_TOKEN}" | base64)"
create_payload="$(jq -n \
  --arg key "${JIRA_PROJECT_KEY}" \
  --arg summary "${SUMMARY}" \
  '{
    fields: {
      project: { key: $key },
      issuetype: { name: "Epic" },
      summary: $summary,
      description: {
        type: "doc",
        version: 1,
        content: [
          {
            type: "paragraph",
            content: [
              {
                type: "text",
                text: "Feature request: Add self-service profile update for customer contact details."
              }
            ]
          },
          {
            type: "paragraph",
            content: [
              {
                type: "text",
                text: "Business Goal: reduce support tickets and improve data accuracy."
              }
            ]
          }
        ]
      },
      labels: ["agent-demo"]
    }
  }'
)"

echo "Creating demo Epic in project ${JIRA_PROJECT_KEY}..."
resp_file="$(mktemp /tmp/jira-create-epic.XXXXXX.json)"
http_code="$(
  curl -sS -o "${resp_file}" -w "%{http_code}" \
    -X POST "${JIRA_BASE_URL}/rest/api/3/issue" \
    -H "Authorization: Basic ${auth_b64}" \
    -H "Accept: application/json" \
    -H "Content-Type: application/json" \
    -d "${create_payload}"
)"

if [[ "${http_code}" != "201" ]]; then
  echo "Epic creation failed (HTTP ${http_code})."
  cat "${resp_file}"
  rm -f "${resp_file}"
  exit 1
fi

EPIC_KEY="$(jq -r '.key // empty' "${resp_file}")"
rm -f "${resp_file}"

if [[ -z "${EPIC_KEY}" ]]; then
  echo "Epic created but key not found in response."
  exit 1
fi

echo "Created Epic: ${EPIC_KEY}"
if [[ "${LIVE_MODE}" == "true" ]]; then
  if [[ -z "${REVIEW_ENDPOINT_API_KEY}" && -n "${AZURE_KEY_VAULT_NAME}" && -n "${REVIEW_ENDPOINT_API_KEY_SECRET_NAME}" ]]; then
    REVIEW_ENDPOINT_API_KEY="$(get_secret_from_kv "${AZURE_KEY_VAULT_NAME}" "${REVIEW_ENDPOINT_API_KEY_SECRET_NAME}" 2>/dev/null || true)"
  fi
  if [[ -z "${REVIEW_ENDPOINT_URL}" || -z "${REVIEW_ENDPOINT_API_KEY}" ]]; then
    echo "Missing REVIEW_ENDPOINT_URL or REVIEW_ENDPOINT_API_KEY for --live mode."
    exit 1
  fi
  ORCH_URL="${REVIEW_ENDPOINT_URL%/review_epic}/execute_orchestrator_cycle"
  echo "Running orchestrator LIVE cycle (comments enabled, no transitions)..."
  curl -sS \
    -X POST \
    -H "Content-Type: application/json" \
    "${ORCH_URL}?code=${REVIEW_ENDPOINT_API_KEY}" \
    -d "{\"project_key\":\"${JIRA_PROJECT_KEY}\",\"mode\":\"single_epic\",\"epic_key\":\"${EPIC_KEY}\",\"dry_run\":false,\"allow_transition_execution\":false,\"allow_dispatch_execution\":false,\"allow_comment_execution\":true}" \
    | jq .
else
  echo "Running orchestrator dry-run..."
  bash scripts/test-orchestrator-cycle.sh "${EPIC_KEY}"
fi
