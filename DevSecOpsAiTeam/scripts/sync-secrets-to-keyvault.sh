#!/usr/bin/env bash
set -euo pipefail

if [[ ! -f ".env" ]]; then
  echo "Missing .env file. Copy .env.example to .env and fill values."
  exit 1
fi

get_env() {
  grep "^$1=" .env | cut -d= -f2- || true
}

AZURE_RESOURCE_GROUP="$(get_env AZURE_RESOURCE_GROUP)"
AZURE_LOCATION="$(get_env AZURE_LOCATION)"
AZURE_KEY_VAULT_NAME="$(get_env AZURE_KEY_VAULT_NAME)"

JIRA_EMAIL="$(get_env JIRA_EMAIL)"
JIRA_API_TOKEN="$(get_env JIRA_API_TOKEN)"
REVIEW_ENDPOINT_API_KEY="$(get_env REVIEW_ENDPOINT_API_KEY)"
BITBUCKET_API_TOKEN="$(get_env BITBUCKET_API_TOKEN)"
BITBUCKET_USERNAME="$(get_env BITBUCKET_USERNAME)"
BITBUCKET_APP_PASSWORD="$(get_env BITBUCKET_APP_PASSWORD)"

JIRA_EMAIL_SECRET_NAME="$(get_env JIRA_EMAIL_SECRET_NAME)"
JIRA_API_TOKEN_SECRET_NAME="$(get_env JIRA_API_TOKEN_SECRET_NAME)"
REVIEW_ENDPOINT_API_KEY_SECRET_NAME="$(get_env REVIEW_ENDPOINT_API_KEY_SECRET_NAME)"
BITBUCKET_API_TOKEN_SECRET_NAME="$(get_env BITBUCKET_API_TOKEN_SECRET_NAME)"
BITBUCKET_USERNAME_SECRET_NAME="$(get_env BITBUCKET_USERNAME_SECRET_NAME)"
BITBUCKET_APP_PASSWORD_SECRET_NAME="$(get_env BITBUCKET_APP_PASSWORD_SECRET_NAME)"

: "${AZURE_RESOURCE_GROUP:?Missing AZURE_RESOURCE_GROUP in .env}"
: "${AZURE_LOCATION:?Missing AZURE_LOCATION in .env}"

if [[ -z "${AZURE_KEY_VAULT_NAME}" ]]; then
  AZURE_KEY_VAULT_NAME="kv-epic-po-${RANDOM}${RANDOM}"
  AZURE_KEY_VAULT_NAME="${AZURE_KEY_VAULT_NAME:0:24}"
  echo "Creating Key Vault ${AZURE_KEY_VAULT_NAME}..."
  az keyvault create \
    --name "${AZURE_KEY_VAULT_NAME}" \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --location "${AZURE_LOCATION}" \
    --sku standard \
    --only-show-errors \
    1>/tmp/keyvault-create.json
fi

: "${JIRA_EMAIL_SECRET_NAME:=jira-email}"
: "${JIRA_API_TOKEN_SECRET_NAME:=jira-api-token}"
: "${REVIEW_ENDPOINT_API_KEY_SECRET_NAME:=review-endpoint-api-key}"
: "${BITBUCKET_API_TOKEN_SECRET_NAME:=bitbucket-api-token}"
: "${BITBUCKET_USERNAME_SECRET_NAME:=bitbucket-username}"
: "${BITBUCKET_APP_PASSWORD_SECRET_NAME:=bitbucket-app-password}"

if [[ -n "${JIRA_EMAIL}" ]]; then
  az keyvault secret set --vault-name "${AZURE_KEY_VAULT_NAME}" --name "${JIRA_EMAIL_SECRET_NAME}" --value "${JIRA_EMAIL}" --only-show-errors 1>/tmp/kv-jira-email.json
fi
if [[ -n "${JIRA_API_TOKEN}" ]]; then
  az keyvault secret set --vault-name "${AZURE_KEY_VAULT_NAME}" --name "${JIRA_API_TOKEN_SECRET_NAME}" --value "${JIRA_API_TOKEN}" --only-show-errors 1>/tmp/kv-jira-token.json
fi
if [[ -n "${REVIEW_ENDPOINT_API_KEY}" ]]; then
  az keyvault secret set --vault-name "${AZURE_KEY_VAULT_NAME}" --name "${REVIEW_ENDPOINT_API_KEY_SECRET_NAME}" --value "${REVIEW_ENDPOINT_API_KEY}" --only-show-errors 1>/tmp/kv-review-key.json
fi
if [[ -n "${BITBUCKET_API_TOKEN}" ]]; then
  az keyvault secret set --vault-name "${AZURE_KEY_VAULT_NAME}" --name "${BITBUCKET_API_TOKEN_SECRET_NAME}" --value "${BITBUCKET_API_TOKEN}" --only-show-errors 1>/tmp/kv-bb-token.json
fi
if [[ -n "${BITBUCKET_USERNAME}" ]]; then
  az keyvault secret set --vault-name "${AZURE_KEY_VAULT_NAME}" --name "${BITBUCKET_USERNAME_SECRET_NAME}" --value "${BITBUCKET_USERNAME}" --only-show-errors 1>/tmp/kv-bb-user.json
fi
if [[ -n "${BITBUCKET_APP_PASSWORD}" ]]; then
  az keyvault secret set --vault-name "${AZURE_KEY_VAULT_NAME}" --name "${BITBUCKET_APP_PASSWORD_SECRET_NAME}" --value "${BITBUCKET_APP_PASSWORD}" --only-show-errors 1>/tmp/kv-bb-pass.json
fi

python3 - <<PY
from pathlib import Path

env_path = Path(".env")
lines = env_path.read_text().splitlines()
updates = {
    "AZURE_KEY_VAULT_NAME": "${AZURE_KEY_VAULT_NAME}",
    "JIRA_EMAIL_SECRET_NAME": "${JIRA_EMAIL_SECRET_NAME}",
    "JIRA_API_TOKEN_SECRET_NAME": "${JIRA_API_TOKEN_SECRET_NAME}",
    "REVIEW_ENDPOINT_API_KEY_SECRET_NAME": "${REVIEW_ENDPOINT_API_KEY_SECRET_NAME}",
    "BITBUCKET_API_TOKEN_SECRET_NAME": "${BITBUCKET_API_TOKEN_SECRET_NAME}",
    "BITBUCKET_USERNAME_SECRET_NAME": "${BITBUCKET_USERNAME_SECRET_NAME}",
    "BITBUCKET_APP_PASSWORD_SECRET_NAME": "${BITBUCKET_APP_PASSWORD_SECRET_NAME}",
    "JIRA_EMAIL": "",
    "JIRA_API_TOKEN": "",
    "REVIEW_ENDPOINT_API_KEY": "",
    "BITBUCKET_API_TOKEN": "",
    "BITBUCKET_USERNAME": "",
    "BITBUCKET_APP_PASSWORD": "",
}
out = []
seen = set()
for line in lines:
    if "=" in line and not line.strip().startswith("#"):
        key = line.split("=", 1)[0]
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
            continue
    out.append(line)
for key, val in updates.items():
    if key not in seen:
        out.append(f"{key}={val}")
env_path.write_text("\\n".join(out) + "\\n")
PY

echo "Key Vault sync complete."
echo "AZURE_KEY_VAULT_NAME=${AZURE_KEY_VAULT_NAME}"
echo "Secrets now loaded from Key Vault during deployment."
