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

PROJECT_ENDPOINT="${AI_FOUNDRY_PROJECT_ENDPOINT:-$(get_env AI_FOUNDRY_PROJECT_ENDPOINT)}"
PROJECT_NAME="${AI_FOUNDRY_PROJECT_NAME:-$(get_env AI_FOUNDRY_PROJECT_NAME)}"
AGENT_NAME="${AI_FOUNDRY_ORCHESTRATOR_AGENT_NAME:-$(get_env AI_FOUNDRY_ORCHESTRATOR_AGENT_NAME)}"
MODEL_DEPLOYMENT="${AI_FOUNDRY_MODEL_DEPLOYMENT:-$(get_env AI_FOUNDRY_MODEL_DEPLOYMENT)}"
API_VERSION="${AI_FOUNDRY_API_VERSION:-2025-05-15-preview}"

REVIEW_ENDPOINT_URL="${REVIEW_ENDPOINT_URL:-$(get_env REVIEW_ENDPOINT_URL)}"
REVIEW_ENDPOINT_API_KEY="${REVIEW_ENDPOINT_API_KEY:-$(get_env REVIEW_ENDPOINT_API_KEY)}"
AZURE_KEY_VAULT_NAME="${AZURE_KEY_VAULT_NAME:-$(get_env AZURE_KEY_VAULT_NAME)}"
REVIEW_ENDPOINT_API_KEY_SECRET_NAME="${REVIEW_ENDPOINT_API_KEY_SECRET_NAME:-$(get_env REVIEW_ENDPOINT_API_KEY_SECRET_NAME)}"

AGENT_NAME="${AGENT_NAME:-orchestrator-agent}"

if [[ -z "${PROJECT_ENDPOINT}" ]]; then
  if [[ -n "${PROJECT_NAME}" ]]; then
    echo "Missing AI_FOUNDRY_PROJECT_ENDPOINT."
    echo "Set it in .env like:"
    echo "AI_FOUNDRY_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/${PROJECT_NAME}"
  else
    echo "Missing AI_FOUNDRY_PROJECT_ENDPOINT in .env."
  fi
  exit 1
fi

if [[ -z "${MODEL_DEPLOYMENT}" ]]; then
  MODEL_DEPLOYMENT="gpt-4o-mini"
fi

TOKEN="$(az account get-access-token --resource https://ai.azure.com --query accessToken -o tsv --only-show-errors 2>/dev/null || true)"
if [[ -z "${TOKEN}" ]]; then
  echo "Azure login required. Run:"
  if [[ -n "${AZURE_CONFIG_DIR:-}" ]]; then
    echo "export AZURE_CONFIG_DIR=${AZURE_CONFIG_DIR}"
  fi
  echo "az login"
  exit 1
fi

if [[ -z "${REVIEW_ENDPOINT_API_KEY}" && -n "${AZURE_KEY_VAULT_NAME}" && -n "${REVIEW_ENDPOINT_API_KEY_SECRET_NAME}" ]]; then
  REVIEW_ENDPOINT_API_KEY="$(get_secret_from_kv "${AZURE_KEY_VAULT_NAME}" "${REVIEW_ENDPOINT_API_KEY_SECRET_NAME}")"
fi

if [[ -z "${REVIEW_ENDPOINT_URL}" || -z "${REVIEW_ENDPOINT_API_KEY}" ]]; then
  echo "Missing REVIEW_ENDPOINT_URL or REVIEW_ENDPOINT_API_KEY (or Key Vault secret)."
  exit 1
fi

OPENAPI_URL="${REVIEW_ENDPOINT_URL%/review_epic}/openapi.execute_orchestrator_cycle.v1.json?code=${REVIEW_ENDPOINT_API_KEY}"
INSTRUCTIONS_FILE="agents/orchestrator-agent/system-instructions.md"
[[ -f "${INSTRUCTIONS_FILE}" ]] || { echo "Missing ${INSTRUCTIONS_FILE}"; exit 1; }

tmp_payload="$(mktemp /tmp/foundry-orchestrator-payload.XXXXXX.json)"
cleanup() {
  rm -f "${tmp_payload}"
}
trap cleanup EXIT

jq -n \
  --arg name "${AGENT_NAME}" \
  --arg model "${MODEL_DEPLOYMENT}" \
  --rawfile instructions "${INSTRUCTIONS_FILE}" \
  --arg openapi_url "${OPENAPI_URL}" \
  '{
    name: $name,
    description: "Epic delivery orchestrator agent",
    definition: {
      kind: "prompt",
      model: $model,
      instructions: $instructions,
      tools: [
        {
          type: "openapi",
          openapi: {
            spec: { url: $openapi_url }
          }
        }
      ]
    }
  }' > "${tmp_payload}"

echo "Registering/updating Foundry agent '${AGENT_NAME}' with OpenAPI tool..."
resp_file="$(mktemp /tmp/foundry-orchestrator-response.XXXXXX.json)"
http_code="$(
  curl -sS -o "${resp_file}" -w "%{http_code}" \
    -X PUT \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    "${PROJECT_ENDPOINT}/agents/${AGENT_NAME}?api-version=${API_VERSION}" \
    --data @"${tmp_payload}"
)"

if [[ "${http_code}" != "200" && "${http_code}" != "201" ]]; then
  echo "Foundry API call failed (HTTP ${http_code}):"
  cat "${resp_file}"
  rm -f "${resp_file}"
  exit 1
fi

echo "Success (HTTP ${http_code})."
jq '{name, id, version, latest: .definition.tools}' "${resp_file}" || true
rm -f "${resp_file}"
