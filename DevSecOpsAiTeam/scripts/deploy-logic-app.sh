#!/usr/bin/env bash
set -euo pipefail

# Optional: set AZURE_CONFIG_DIR externally when running in restricted environments.
if [[ -n "${AZURE_CONFIG_DIR:-}" ]]; then
  mkdir -p "${AZURE_CONFIG_DIR}"
fi

if [[ ! -f ".env" ]]; then
  echo "Missing .env file. Copy .env.example to .env and fill values."
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

AZURE_RESOURCE_GROUP="$(get_env AZURE_RESOURCE_GROUP)"
AZURE_LOCATION="$(get_env AZURE_LOCATION)"
AZURE_KEY_VAULT_NAME="$(get_env AZURE_KEY_VAULT_NAME)"
JIRA_BASE_URL="$(get_env JIRA_BASE_URL)"
JIRA_EMAIL="$(get_env JIRA_EMAIL)"
JIRA_API_TOKEN="$(get_env JIRA_API_TOKEN)"
JIRA_PROJECT_KEY="$(get_env JIRA_PROJECT_KEY)"
JIRA_BOARD_JQL="$(get_env JIRA_BOARD_JQL)"
REVIEW_ENDPOINT_URL="$(get_env REVIEW_ENDPOINT_URL)"
REVIEW_ENDPOINT_API_KEY="$(get_env REVIEW_ENDPOINT_API_KEY)"
JIRA_EMAIL_SECRET_NAME="$(get_env JIRA_EMAIL_SECRET_NAME)"
JIRA_API_TOKEN_SECRET_NAME="$(get_env JIRA_API_TOKEN_SECRET_NAME)"
REVIEW_ENDPOINT_API_KEY_SECRET_NAME="$(get_env REVIEW_ENDPOINT_API_KEY_SECRET_NAME)"
RUN_EVERY_MINUTES="$(get_env RUN_EVERY_MINUTES)"
MAX_EPICS_PER_RUN="$(get_env MAX_EPICS_PER_RUN)"
ALLOW_HIGH_FREQUENCY_SCHEDULE="$(get_env ALLOW_HIGH_FREQUENCY_SCHEDULE)"
ORCHESTRATOR_RUN_ENABLED="$(get_env ORCHESTRATOR_RUN_ENABLED)"
ORCHESTRATOR_DRY_RUN="$(get_env ORCHESTRATOR_DRY_RUN)"
ORCHESTRATOR_ALLOW_TRANSITION_EXECUTION="$(get_env ORCHESTRATOR_ALLOW_TRANSITION_EXECUTION)"
ORCHESTRATOR_ALLOW_DISPATCH_EXECUTION="$(get_env ORCHESTRATOR_ALLOW_DISPATCH_EXECUTION)"
ORCHESTRATOR_ALLOW_COMMENT_EXECUTION="$(get_env ORCHESTRATOR_ALLOW_COMMENT_EXECUTION)"

: "${AZURE_RESOURCE_GROUP:?Missing AZURE_RESOURCE_GROUP in .env}"
: "${AZURE_LOCATION:?Missing AZURE_LOCATION in .env}"

if [[ -n "${AZURE_KEY_VAULT_NAME}" ]]; then
  : "${JIRA_EMAIL_SECRET_NAME:=jira-email}"
  : "${JIRA_API_TOKEN_SECRET_NAME:=jira-api-token}"
  : "${REVIEW_ENDPOINT_API_KEY_SECRET_NAME:=review-endpoint-api-key}"
  echo "Loading sensitive values from Key Vault ${AZURE_KEY_VAULT_NAME}..."
  JIRA_EMAIL="$(get_secret_from_kv "${AZURE_KEY_VAULT_NAME}" "${JIRA_EMAIL_SECRET_NAME}")"
  JIRA_API_TOKEN="$(get_secret_from_kv "${AZURE_KEY_VAULT_NAME}" "${JIRA_API_TOKEN_SECRET_NAME}")"
  REVIEW_ENDPOINT_API_KEY="$(get_secret_from_kv "${AZURE_KEY_VAULT_NAME}" "${REVIEW_ENDPOINT_API_KEY_SECRET_NAME}")"
fi

: "${JIRA_EMAIL:?Missing JIRA_EMAIL (or Key Vault secret)}"
: "${JIRA_API_TOKEN:?Missing JIRA_API_TOKEN (or Key Vault secret)}"
: "${REVIEW_ENDPOINT_API_KEY:?Missing REVIEW_ENDPOINT_API_KEY (or Key Vault secret)}"

RUN_EVERY_MINUTES="${RUN_EVERY_MINUTES:-120}"
MAX_EPICS_PER_RUN="${MAX_EPICS_PER_RUN:-20}"
ORCHESTRATOR_RUN_ENABLED="${ORCHESTRATOR_RUN_ENABLED:-true}"
ORCHESTRATOR_DRY_RUN="${ORCHESTRATOR_DRY_RUN:-false}"
ORCHESTRATOR_ALLOW_TRANSITION_EXECUTION="${ORCHESTRATOR_ALLOW_TRANSITION_EXECUTION:-true}"
ORCHESTRATOR_ALLOW_DISPATCH_EXECUTION="${ORCHESTRATOR_ALLOW_DISPATCH_EXECUTION:-true}"
ORCHESTRATOR_ALLOW_COMMENT_EXECUTION="${ORCHESTRATOR_ALLOW_COMMENT_EXECUTION:-true}"

# Cost guardrails: keep calls bounded unless explicitly overridden.
if [[ "${ALLOW_HIGH_FREQUENCY_SCHEDULE}" != "true" && "${RUN_EVERY_MINUTES}" -lt 60 ]]; then
  echo "RUN_EVERY_MINUTES=${RUN_EVERY_MINUTES} is too frequent for low-cost mode. Set ALLOW_HIGH_FREQUENCY_SCHEDULE=true to override."
  exit 1
fi
if [[ "${MAX_EPICS_PER_RUN}" -gt 50 ]]; then
  echo "MAX_EPICS_PER_RUN=${MAX_EPICS_PER_RUN} is too high for low-cost mode. Keep <=50."
  exit 1
fi

WORKFLOW_NAME="${WORKFLOW_NAME:-epic-review-workflow}"
TEMPLATE_FILE="logic-apps/epic-review-workflow/workflow.json"
PARAM_FILE="$(mktemp /tmp/workflow.parameters.runtime.XXXXXX.json)"
cleanup() {
  rm -f "${PARAM_FILE}"
}
trap cleanup EXIT

cat > "$PARAM_FILE" <<EOF
{
  "workflowName": { "value": "${WORKFLOW_NAME}" },
  "location": { "value": "${AZURE_LOCATION}" },
  "jiraBaseUrl": { "value": "${JIRA_BASE_URL}" },
  "jiraEmail": { "value": "${JIRA_EMAIL}" },
  "jiraApiToken": { "value": "${JIRA_API_TOKEN}" },
  "jiraProjectKey": { "value": "${JIRA_PROJECT_KEY}" },
  "epicJql": { "value": "${JIRA_BOARD_JQL}" },
  "reviewEndpointUrl": { "value": "${REVIEW_ENDPOINT_URL}" },
  "reviewEndpointApiKey": { "value": "${REVIEW_ENDPOINT_API_KEY}" },
  "runEveryMinutes": { "value": ${RUN_EVERY_MINUTES} },
  "maxEpicsPerRun": { "value": ${MAX_EPICS_PER_RUN} },
  "orchestratorRunEnabled": { "value": ${ORCHESTRATOR_RUN_ENABLED} },
  "orchestratorDryRun": { "value": ${ORCHESTRATOR_DRY_RUN} },
  "orchestratorAllowTransitionExecution": { "value": ${ORCHESTRATOR_ALLOW_TRANSITION_EXECUTION} },
  "orchestratorAllowDispatchExecution": { "value": ${ORCHESTRATOR_ALLOW_DISPATCH_EXECUTION} },
  "orchestratorAllowCommentExecution": { "value": ${ORCHESTRATOR_ALLOW_COMMENT_EXECUTION} }
}
EOF

echo "Deploying Logic App workflow ${WORKFLOW_NAME}..."
az deployment group create \
  --resource-group "${AZURE_RESOURCE_GROUP}" \
  --template-file "${TEMPLATE_FILE}" \
  --parameters @"${PARAM_FILE}" \
  --only-show-errors \
  1>/tmp/logicapp-deploy.json

echo "Deployment complete. Summary:"
cat /tmp/logicapp-deploy.json
