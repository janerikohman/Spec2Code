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

AZURE_SUBSCRIPTION_ID="$(get_env AZURE_SUBSCRIPTION_ID)"
AZURE_RESOURCE_GROUP="$(get_env AZURE_RESOURCE_GROUP)"
AZURE_LOCATION="$(get_env AZURE_LOCATION)"
AZURE_KEY_VAULT_NAME="$(get_env AZURE_KEY_VAULT_NAME)"
REVIEW_ENDPOINT_API_KEY_SECRET_NAME="$(get_env REVIEW_ENDPOINT_API_KEY_SECRET_NAME)"
DOR_FIELD_MAP_JSON="$(get_env DOR_FIELD_MAP_JSON)"
ENABLE_TEMPLATE_HINT="$(get_env ENABLE_TEMPLATE_HINT)"
ORCHESTRATOR_STATUS_MAP_JSON="$(get_env ORCHESTRATOR_STATUS_MAP_JSON)"
ORCHESTRATOR_DISPATCH_ISSUE_TYPE="$(get_env ORCHESTRATOR_DISPATCH_ISSUE_TYPE)"
BITBUCKET_ENABLE_AUTOMATION="$(get_env BITBUCKET_ENABLE_AUTOMATION)"
BITBUCKET_ENABLE_PR_AUTOMATION="$(get_env BITBUCKET_ENABLE_PR_AUTOMATION)"
BITBUCKET_API_BASE="$(get_env BITBUCKET_API_BASE)"
BITBUCKET_WORKSPACE="$(get_env BITBUCKET_WORKSPACE)"
BITBUCKET_REPO_SLUG="$(get_env BITBUCKET_REPO_SLUG)"
BITBUCKET_MAIN_BRANCH="$(get_env BITBUCKET_MAIN_BRANCH)"
BITBUCKET_EMAIL="$(get_env BITBUCKET_EMAIL)"
BITBUCKET_SINGLE_REPO_MODE="$(get_env BITBUCKET_SINGLE_REPO_MODE)"
BITBUCKET_AUTO_CREATE_REPO="$(get_env BITBUCKET_AUTO_CREATE_REPO)"
BITBUCKET_PROJECT_KEY="$(get_env BITBUCKET_PROJECT_KEY)"
BITBUCKET_API_TOKEN_SECRET_NAME="$(get_env BITBUCKET_API_TOKEN_SECRET_NAME)"
BITBUCKET_USERNAME_SECRET_NAME="$(get_env BITBUCKET_USERNAME_SECRET_NAME)"
BITBUCKET_APP_PASSWORD_SECRET_NAME="$(get_env BITBUCKET_APP_PASSWORD_SECRET_NAME)"
JIRA_BASE_URL="$(get_env JIRA_BASE_URL)"
CONFLUENCE_SPACE_KEY="$(get_env CONFLUENCE_SPACE_KEY)"
JIRA_EMAIL_SECRET_NAME="$(get_env JIRA_EMAIL_SECRET_NAME)"
JIRA_API_TOKEN_SECRET_NAME="$(get_env JIRA_API_TOKEN_SECRET_NAME)"

FUNCTION_APP_NAME="$(get_env REVIEW_FUNCTION_APP_NAME)"
if [[ -z "${FUNCTION_APP_NAME}" ]]; then
  FUNCTION_APP_NAME="epicreview$RANDOM$RANDOM"
fi
STORAGE_ACCOUNT_NAME="$(get_env REVIEW_FUNCTION_STORAGE_ACCOUNT)"
if [[ -z "${STORAGE_ACCOUNT_NAME}" ]]; then
  STORAGE_ACCOUNT_NAME="st${FUNCTION_APP_NAME//-/}"
fi
STORAGE_ACCOUNT_NAME="${STORAGE_ACCOUNT_NAME:0:24}"
RUNTIME="python"
RUNTIME_VERSION="3.11"

if [[ -z "${AZURE_SUBSCRIPTION_ID}" || -z "${AZURE_RESOURCE_GROUP}" || -z "${AZURE_LOCATION}" ]]; then
  echo "Missing Azure values in .env"
  exit 1
fi

az account set --subscription "${AZURE_SUBSCRIPTION_ID}" --only-show-errors

echo "Ensuring storage account ${STORAGE_ACCOUNT_NAME} exists..."
if ! az storage account show --name "${STORAGE_ACCOUNT_NAME}" --resource-group "${AZURE_RESOURCE_GROUP}" --only-show-errors >/dev/null 2>&1; then
  az storage account create \
    --name "${STORAGE_ACCOUNT_NAME}" \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --location "${AZURE_LOCATION}" \
    --sku Standard_LRS \
    --only-show-errors \
    1>/tmp/review-storage-create.json
fi

echo "Ensuring Function App ${FUNCTION_APP_NAME} exists (Consumption)..."
if ! az functionapp show --name "${FUNCTION_APP_NAME}" --resource-group "${AZURE_RESOURCE_GROUP}" --only-show-errors >/dev/null 2>&1; then
  az functionapp create \
    --name "${FUNCTION_APP_NAME}" \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --consumption-plan-location "${AZURE_LOCATION}" \
    --storage-account "${STORAGE_ACCOUNT_NAME}" \
    --functions-version 4 \
    --runtime "${RUNTIME}" \
    --runtime-version "${RUNTIME_VERSION}" \
    --os-type Linux \
    --only-show-errors \
    1>/tmp/review-function-create.json
fi

# Cost guardrail: warn if app is not on a Consumption plan.
SERVER_FARM_ID="$(az functionapp show --name "${FUNCTION_APP_NAME}" --resource-group "${AZURE_RESOURCE_GROUP}" --query serverFarmId -o tsv --only-show-errors || true)"
if [[ -n "${SERVER_FARM_ID}" ]]; then
  PLAN_SKU="$(az appservice plan show --ids "${SERVER_FARM_ID}" --query "sku.tier" -o tsv --only-show-errors || true)"
  if [[ "${PLAN_SKU}" != "Dynamic" ]]; then
    echo "WARNING: Function App is on '${PLAN_SKU}' plan tier, not Consumption (Dynamic). This may increase cost."
  fi
fi

echo "Configuring remote build app settings..."
az functionapp config appsettings set \
  --name "${FUNCTION_APP_NAME}" \
  --resource-group "${AZURE_RESOURCE_GROUP}" \
  --settings SCM_DO_BUILD_DURING_DEPLOYMENT=true ENABLE_ORYX_BUILD=true \
  --only-show-errors \
  1>/tmp/review-function-appsettings.json

if [[ -n "${DOR_FIELD_MAP_JSON}" ]]; then
  echo "Configuring DOR_FIELD_MAP_JSON app setting..."
  az functionapp config appsettings set \
    --name "${FUNCTION_APP_NAME}" \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --settings DOR_FIELD_MAP_JSON="${DOR_FIELD_MAP_JSON}" \
    --only-show-errors \
    1>/tmp/review-function-dor-map-appsettings.json
fi

if [[ -n "${ENABLE_TEMPLATE_HINT}" ]]; then
  echo "Configuring ENABLE_TEMPLATE_HINT app setting..."
  az functionapp config appsettings set \
    --name "${FUNCTION_APP_NAME}" \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --settings ENABLE_TEMPLATE_HINT="${ENABLE_TEMPLATE_HINT}" \
    --only-show-errors \
    1>/tmp/review-function-template-hint-appsettings.json
fi

if [[ -n "${ORCHESTRATOR_STATUS_MAP_JSON}" ]]; then
  echo "Configuring ORCHESTRATOR_STATUS_MAP_JSON app setting..."
  az functionapp config appsettings set \
    --name "${FUNCTION_APP_NAME}" \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --settings ORCHESTRATOR_STATUS_MAP_JSON="${ORCHESTRATOR_STATUS_MAP_JSON}" \
    --only-show-errors \
    1>/tmp/review-function-status-map-appsettings.json
fi

if [[ -n "${ORCHESTRATOR_DISPATCH_ISSUE_TYPE}" ]]; then
  echo "Configuring ORCHESTRATOR_DISPATCH_ISSUE_TYPE app setting..."
  az functionapp config appsettings set \
    --name "${FUNCTION_APP_NAME}" \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --settings ORCHESTRATOR_DISPATCH_ISSUE_TYPE="${ORCHESTRATOR_DISPATCH_ISSUE_TYPE}" \
    --only-show-errors \
    1>/tmp/review-function-dispatch-issue-type-appsettings.json
fi

if [[ -n "${BITBUCKET_ENABLE_AUTOMATION}" || -n "${BITBUCKET_WORKSPACE}" || -n "${BITBUCKET_REPO_SLUG}" ]]; then
  echo "Configuring Bitbucket automation app settings..."
  BB_SETTINGS=()
  [[ -n "${BITBUCKET_ENABLE_AUTOMATION}" ]] && BB_SETTINGS+=("BITBUCKET_ENABLE_AUTOMATION=${BITBUCKET_ENABLE_AUTOMATION}")
  [[ -n "${BITBUCKET_ENABLE_PR_AUTOMATION}" ]] && BB_SETTINGS+=("BITBUCKET_ENABLE_PR_AUTOMATION=${BITBUCKET_ENABLE_PR_AUTOMATION}")
  [[ -n "${BITBUCKET_API_BASE}" ]] && BB_SETTINGS+=("BITBUCKET_API_BASE=${BITBUCKET_API_BASE}")
  [[ -n "${BITBUCKET_WORKSPACE}" ]] && BB_SETTINGS+=("BITBUCKET_WORKSPACE=${BITBUCKET_WORKSPACE}")
  [[ -n "${BITBUCKET_REPO_SLUG}" ]] && BB_SETTINGS+=("BITBUCKET_REPO_SLUG=${BITBUCKET_REPO_SLUG}")
  [[ -n "${BITBUCKET_MAIN_BRANCH}" ]] && BB_SETTINGS+=("BITBUCKET_MAIN_BRANCH=${BITBUCKET_MAIN_BRANCH}")
  [[ -n "${BITBUCKET_EMAIL}" ]] && BB_SETTINGS+=("BITBUCKET_EMAIL=${BITBUCKET_EMAIL}")
  [[ -n "${BITBUCKET_SINGLE_REPO_MODE}" ]] && BB_SETTINGS+=("BITBUCKET_SINGLE_REPO_MODE=${BITBUCKET_SINGLE_REPO_MODE}")
  [[ -n "${BITBUCKET_AUTO_CREATE_REPO}" ]] && BB_SETTINGS+=("BITBUCKET_AUTO_CREATE_REPO=${BITBUCKET_AUTO_CREATE_REPO}")
  [[ -n "${BITBUCKET_PROJECT_KEY}" ]] && BB_SETTINGS+=("BITBUCKET_PROJECT_KEY=${BITBUCKET_PROJECT_KEY}")

  if [[ -n "${AZURE_KEY_VAULT_NAME}" && -n "${BITBUCKET_API_TOKEN_SECRET_NAME}" ]]; then
    BB_TOKEN_REF="@Microsoft.KeyVault(SecretUri=https://${AZURE_KEY_VAULT_NAME}.vault.azure.net/secrets/${BITBUCKET_API_TOKEN_SECRET_NAME}/)"
    BB_SETTINGS+=("BITBUCKET_API_TOKEN=${BB_TOKEN_REF}")
  elif [[ -n "${AZURE_KEY_VAULT_NAME}" && -n "${BITBUCKET_USERNAME_SECRET_NAME}" && -n "${BITBUCKET_APP_PASSWORD_SECRET_NAME}" ]]; then
    # Legacy fallback for older app-password based setups.
    BB_USER_REF="@Microsoft.KeyVault(SecretUri=https://${AZURE_KEY_VAULT_NAME}.vault.azure.net/secrets/${BITBUCKET_USERNAME_SECRET_NAME}/)"
    BB_PASS_REF="@Microsoft.KeyVault(SecretUri=https://${AZURE_KEY_VAULT_NAME}.vault.azure.net/secrets/${BITBUCKET_APP_PASSWORD_SECRET_NAME}/)"
    BB_SETTINGS+=("BITBUCKET_USERNAME=${BB_USER_REF}")
    BB_SETTINGS+=("BITBUCKET_APP_PASSWORD=${BB_PASS_REF}")
  fi

  if [[ "${#BB_SETTINGS[@]}" -gt 0 ]]; then
    az functionapp config appsettings set \
      --name "${FUNCTION_APP_NAME}" \
      --resource-group "${AZURE_RESOURCE_GROUP}" \
      --settings "${BB_SETTINGS[@]}" \
      --only-show-errors \
      1>/tmp/review-function-bitbucket-appsettings.json
  fi
fi

if [[ -n "${JIRA_BASE_URL}" ]]; then
  echo "Configuring Jira app settings for orchestrator endpoint..."
  if [[ -n "${AZURE_KEY_VAULT_NAME}" && -n "${JIRA_EMAIL_SECRET_NAME}" && -n "${JIRA_API_TOKEN_SECRET_NAME}" ]]; then
    az functionapp identity assign \
      --name "${FUNCTION_APP_NAME}" \
      --resource-group "${AZURE_RESOURCE_GROUP}" \
      --only-show-errors \
      1>/tmp/review-function-identity-assign.json

    PRINCIPAL_ID="$(az functionapp identity show --name "${FUNCTION_APP_NAME}" --resource-group "${AZURE_RESOURCE_GROUP}" --query principalId -o tsv --only-show-errors)"
    KV_SCOPE="$(az keyvault show --name "${AZURE_KEY_VAULT_NAME}" --query id -o tsv --only-show-errors)"
    az role assignment create \
      --assignee-object-id "${PRINCIPAL_ID}" \
      --assignee-principal-type ServicePrincipal \
      --role "Key Vault Secrets User" \
      --scope "${KV_SCOPE}" \
      --only-show-errors \
      1>/tmp/review-function-kv-role.json || true

    EMAIL_REF="@Microsoft.KeyVault(SecretUri=https://${AZURE_KEY_VAULT_NAME}.vault.azure.net/secrets/${JIRA_EMAIL_SECRET_NAME}/)"
    TOKEN_REF="@Microsoft.KeyVault(SecretUri=https://${AZURE_KEY_VAULT_NAME}.vault.azure.net/secrets/${JIRA_API_TOKEN_SECRET_NAME}/)"
    az functionapp config appsettings set \
      --name "${FUNCTION_APP_NAME}" \
      --resource-group "${AZURE_RESOURCE_GROUP}" \
      --settings JIRA_BASE_URL="${JIRA_BASE_URL}" JIRA_EMAIL="${EMAIL_REF}" JIRA_API_TOKEN="${TOKEN_REF}" \
      --only-show-errors \
      1>/tmp/review-function-jira-appsettings.json

    if [[ -n "${CONFLUENCE_SPACE_KEY}" ]]; then
      az functionapp config appsettings set \
        --name "${FUNCTION_APP_NAME}" \
        --resource-group "${AZURE_RESOURCE_GROUP}" \
        --settings CONFLUENCE_SPACE_KEY="${CONFLUENCE_SPACE_KEY}" \
        --only-show-errors \
        1>/tmp/review-function-confluence-appsettings.json
    fi
  else
    echo "Skipping Jira Key Vault references: missing AZURE_KEY_VAULT_NAME or Jira secret names."
  fi
fi

echo "Packaging function code..."
TMP_ZIP="/tmp/review-endpoint.zip"
rm -f "${TMP_ZIP}"
(cd functions/review-endpoint && zip -qr "${TMP_ZIP}" .)

echo "Deploying function package..."
az functionapp deployment source config-zip \
  --name "${FUNCTION_APP_NAME}" \
  --resource-group "${AZURE_RESOURCE_GROUP}" \
  --src "${TMP_ZIP}" \
  --timeout 1800 \
  --only-show-errors \
  1>/tmp/review-function-deploy.json

echo "Fetching function key and URL..."
FUNCTION_KEY="$(az functionapp keys list \
  --name "${FUNCTION_APP_NAME}" \
  --resource-group "${AZURE_RESOURCE_GROUP}" \
  --query functionKeys.default \
  -o tsv \
  --only-show-errors)"

FUNCTION_URL="https://${FUNCTION_APP_NAME}.azurewebsites.net/api/review_epic"

if [[ -n "${AZURE_KEY_VAULT_NAME}" ]]; then
  : "${REVIEW_ENDPOINT_API_KEY_SECRET_NAME:=review-endpoint-api-key}"
  echo "Storing function key in Key Vault ${AZURE_KEY_VAULT_NAME}/${REVIEW_ENDPOINT_API_KEY_SECRET_NAME}..."
  az keyvault secret set \
    --vault-name "${AZURE_KEY_VAULT_NAME}" \
    --name "${REVIEW_ENDPOINT_API_KEY_SECRET_NAME}" \
    --value "${FUNCTION_KEY}" \
    --only-show-errors \
    1>/tmp/review-function-keyvault-set.json
fi

ENV_FUNCTION_KEY="${FUNCTION_KEY}"
if [[ -n "${AZURE_KEY_VAULT_NAME}" ]]; then
  ENV_FUNCTION_KEY=""
fi

python3 - <<PY
from pathlib import Path

env_path = Path(".env")
lines = env_path.read_text().splitlines()
updates = {
    "REVIEW_FUNCTION_APP_NAME": "${FUNCTION_APP_NAME}",
    "REVIEW_FUNCTION_STORAGE_ACCOUNT": "${STORAGE_ACCOUNT_NAME}",
    "REVIEW_ENDPOINT_URL": "${FUNCTION_URL}",
    "REVIEW_ENDPOINT_API_KEY_SECRET_NAME": "${REVIEW_ENDPOINT_API_KEY_SECRET_NAME}",
    "REVIEW_ENDPOINT_API_KEY": "${ENV_FUNCTION_KEY}",
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

echo "Done."
echo "REVIEW_ENDPOINT_URL=${FUNCTION_URL}"
if [[ -n "${AZURE_KEY_VAULT_NAME}" ]]; then
  echo "REVIEW_ENDPOINT_API_KEY stored in Key Vault secret ${REVIEW_ENDPOINT_API_KEY_SECRET_NAME}"
else
  echo "REVIEW_ENDPOINT_API_KEY=<written to .env>"
fi
