#!/bin/bash

#################################################################################
# Epic Scheduler Function Deployment Script
# Deploys the epic-scheduler Azure Function to orchestrate epic processing
#################################################################################

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "${SCRIPT_DIR}")"

# ==================== HELPER FUNCTIONS ====================
get_env() {
  local var_name="$1"
  grep "^${var_name}=" "${REPO_ROOT}/.env" 2>/dev/null | cut -d'=' -f2- || echo ""
}

log_info() {
  echo "[$(date +'%Y-%m-%d %H:%M:%S')] INFO: $*"
}

log_error() {
  echo "[$(date +'%Y-%m-%d %H:%M:%S')] ERROR: $*" >&2
}

log_warn() {
  echo "[$(date +'%Y-%m-%d %H:%M:%S')] WARN: $*"
}

# ==================== PREREQUISITES CHECK ====================
log_info "Checking prerequisites..."

if [[ ! -f "${REPO_ROOT}/.env" ]]; then
  log_error ".env file not found at ${REPO_ROOT}/.env"
  exit 1
fi

if ! command -v az &> /dev/null; then
  log_error "Azure CLI (az) not found. Please install: https://aka.ms/azure-cli"
  exit 1
fi

# Get config from .env
AZURE_SUBSCRIPTION_ID="$(get_env 'AZURE_SUBSCRIPTION_ID')"
AZURE_RESOURCE_GROUP="$(get_env 'AZURE_RESOURCE_GROUP')"
AZURE_LOCATION="$(get_env 'AZURE_LOCATION')"
EPIC_SCHEDULER_FUNCTION_APP_NAME="$(get_env 'EPIC_SCHEDULER_FUNCTION_APP_NAME')"
EPIC_SCHEDULER_STORAGE_ACCOUNT="$(get_env 'EPIC_SCHEDULER_STORAGE_ACCOUNT')"
AZURE_KEY_VAULT_NAME="$(get_env 'AZURE_KEY_VAULT_NAME')"

# Validate required settings
if [[ -z "${AZURE_SUBSCRIPTION_ID}" ]]; then
  log_error "AZURE_SUBSCRIPTION_ID not set in .env"
  exit 1
fi

if [[ -z "${AZURE_RESOURCE_GROUP}" ]]; then
  log_error "AZURE_RESOURCE_GROUP not set in .env"
  exit 1
fi

if [[ -z "${AZURE_LOCATION}" ]]; then
  log_error "AZURE_LOCATION not set in .env"
  exit 1
fi

# ==================== AZURE AUTHENTICATION ====================
log_info "Authenticating to Azure subscription ${AZURE_SUBSCRIPTION_ID}..."
az account set --subscription "${AZURE_SUBSCRIPTION_ID}" --only-show-errors

CURRENT_SUB="$(az account show --query name -o tsv --only-show-errors)"
log_info "Using subscription: ${CURRENT_SUB}"

# ==================== RESOURCE GROUP ====================
log_info "Ensuring resource group ${AZURE_RESOURCE_GROUP} exists..."
az group create \
  --name "${AZURE_RESOURCE_GROUP}" \
  --location "${AZURE_LOCATION}" \
  --only-show-errors \
  1>/dev/null || true

# ==================== STORAGE ACCOUNT ====================
: "${EPIC_SCHEDULER_STORAGE_ACCOUNT:=epicscheduler${RANDOM}}"
log_info "Using storage account: ${EPIC_SCHEDULER_STORAGE_ACCOUNT}"

if ! az storage account show \
  --name "${EPIC_SCHEDULER_STORAGE_ACCOUNT}" \
  --resource-group "${AZURE_RESOURCE_GROUP}" \
  --only-show-errors \
  1>/dev/null 2>&1; then
  
  log_info "Creating storage account ${EPIC_SCHEDULER_STORAGE_ACCOUNT}..."
  az storage account create \
    --name "${EPIC_SCHEDULER_STORAGE_ACCOUNT}" \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --location "${AZURE_LOCATION}" \
    --sku Standard_LRS \
    --only-show-errors \
    1>/dev/null
fi

STORAGE_ACCOUNT_KEY="$(az storage account keys list \
  --account-name "${EPIC_SCHEDULER_STORAGE_ACCOUNT}" \
  --resource-group "${AZURE_RESOURCE_GROUP}" \
  --query '[0].value' \
  -o tsv \
  --only-show-errors)"

STORAGE_CONNECTION_STRING="DefaultEndpointsProtocol=https;AccountName=${EPIC_SCHEDULER_STORAGE_ACCOUNT};AccountKey=${STORAGE_ACCOUNT_KEY};EndpointSuffix=core.windows.net"

# ==================== FUNCTION APP ====================
: "${EPIC_SCHEDULER_FUNCTION_APP_NAME:=epic-scheduler-${RANDOM}}"
log_info "Using function app: ${EPIC_SCHEDULER_FUNCTION_APP_NAME}"

if ! az functionapp show \
  --name "${EPIC_SCHEDULER_FUNCTION_APP_NAME}" \
  --resource-group "${AZURE_RESOURCE_GROUP}" \
  --only-show-errors \
  1>/dev/null 2>&1; then
  
  log_info "Creating function app ${EPIC_SCHEDULER_FUNCTION_APP_NAME}..."
  az functionapp create \
    --name "${EPIC_SCHEDULER_FUNCTION_APP_NAME}" \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --storage-account "${EPIC_SCHEDULER_STORAGE_ACCOUNT}" \
    --runtime python \
    --runtime-version 3.11 \
    --functions-version 4 \
    --os-type Linux \
    --consumption-plan-location "${AZURE_LOCATION}" \
    --only-show-errors \
    1>/dev/null
fi

# ==================== APP SETTINGS ====================
log_info "Configuring app settings..."

# Base app settings
az functionapp config appsettings set \
  --name "${EPIC_SCHEDULER_FUNCTION_APP_NAME}" \
  --resource-group "${AZURE_RESOURCE_GROUP}" \
  --settings \
    AzureWebJobsStorage="${STORAGE_CONNECTION_STRING}" \
    FUNCTIONS_WORKER_RUNTIME="python" \
    AzureWebJobsFeatureFlags="EnableWorkerIndexing" \
    SCM_DO_BUILD_DURING_DEPLOYMENT="true" \
    ENABLE_ORYX_BUILD="true" \
  --only-show-errors \
  1>/tmp/epic-scheduler-base-appsettings.json

# Jira settings
if [[ -n "$(get_env 'JIRA_BASE_URL')" ]]; then
  log_info "Configuring Jira app settings..."
  
  if [[ -n "${AZURE_KEY_VAULT_NAME}" ]]; then
    : "${JIRA_EMAIL_SECRET_NAME:=jira-email}"
    : "${JIRA_API_TOKEN_SECRET_NAME:=jira-api-token}"
    
    # Verify secrets exist in Key Vault
    if ! az keyvault secret show \
      --vault-name "${AZURE_KEY_VAULT_NAME}" \
      --name "${JIRA_EMAIL_SECRET_NAME}" \
      --only-show-errors \
      1>/dev/null 2>&1; then
      
      log_warn "Secret ${JIRA_EMAIL_SECRET_NAME} not found in Key Vault"
    else
      # Assign managed identity and RBAC
      az functionapp identity assign \
        --name "${EPIC_SCHEDULER_FUNCTION_APP_NAME}" \
        --resource-group "${AZURE_RESOURCE_GROUP}" \
        --only-show-errors \
        1>/tmp/epic-scheduler-identity-assign.json || true
      
      PRINCIPAL_ID="$(az functionapp identity show \
        --name "${EPIC_SCHEDULER_FUNCTION_APP_NAME}" \
        --resource-group "${AZURE_RESOURCE_GROUP}" \
        --query principalId -o tsv \
        --only-show-errors 2>/dev/null)" || true
      
      if [[ -n "${PRINCIPAL_ID}" ]]; then
        log_info "Assigning Key Vault reader role to managed identity..."
        KV_SCOPE="$(az keyvault show --name "${AZURE_KEY_VAULT_NAME}" --query id -o tsv --only-show-errors)"
        KV_SECRETS_USER_ROLE_ID="4633458b-17de-408a-b874-0445c86b69e6"
        
        az role assignment create \
          --assignee "${PRINCIPAL_ID}" \
          --role "${KV_SECRETS_USER_ROLE_ID}" \
          --scope "${KV_SCOPE}" \
          --only-show-errors \
          1>/dev/null 2>&1 || true
      fi
      
      EMAIL_REF="@Microsoft.KeyVault(SecretUri=https://${AZURE_KEY_VAULT_NAME}.vault.azure.net/secrets/${JIRA_EMAIL_SECRET_NAME}/)"
      TOKEN_REF="@Microsoft.KeyVault(SecretUri=https://${AZURE_KEY_VAULT_NAME}.vault.azure.net/secrets/${JIRA_API_TOKEN_SECRET_NAME}/)"
    fi
  fi
  
  JIRA_BASE_URL="$(get_env 'JIRA_BASE_URL')"
  JIRA_PROJECT_KEY="$(get_env 'JIRA_PROJECT_KEY')"
  JIRA_PROJECT_KEY="${JIRA_PROJECT_KEY:=KAN}"
  
  az functionapp config appsettings set \
    --name "${EPIC_SCHEDULER_FUNCTION_APP_NAME}" \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --settings \
      JIRA_BASE_URL="${JIRA_BASE_URL}" \
      JIRA_EMAIL="${EMAIL_REF}" \
      JIRA_API_TOKEN="${TOKEN_REF}" \
      JIRA_PROJECT_KEY="${JIRA_PROJECT_KEY}" \
    --only-show-errors \
    1>/tmp/epic-scheduler-jira-appsettings.json
fi

# Review Endpoint settings
if [[ -n "$(get_env 'REVIEW_ENDPOINT_BASE_URL')" ]]; then
  log_info "Configuring Review Endpoint app settings..."
  
  REVIEW_ENDPOINT_BASE_URL="$(get_env 'REVIEW_ENDPOINT_BASE_URL')"
  
  if [[ -n "${AZURE_KEY_VAULT_NAME}" ]]; then
    : "${REVIEW_ENDPOINT_API_KEY_SECRET_NAME:=review-endpoint-api-key}"
    API_KEY_REF="@Microsoft.KeyVault(SecretUri=https://${AZURE_KEY_VAULT_NAME}.vault.azure.net/secrets/${REVIEW_ENDPOINT_API_KEY_SECRET_NAME}/)"
  else
    API_KEY_REF="$(get_env 'REVIEW_ENDPOINT_API_KEY')"
  fi
  
  az functionapp config appsettings set \
    --name "${EPIC_SCHEDULER_FUNCTION_APP_NAME}" \
    --resource-group "${AZURE_RESOURCE_GROUP}" \
    --settings \
      REVIEW_ENDPOINT_BASE_URL="${REVIEW_ENDPOINT_BASE_URL}" \
      REVIEW_ENDPOINT_API_KEY="${API_KEY_REF}" \
    --only-show-errors \
    1>/tmp/epic-scheduler-endpoint-appsettings.json
fi

# ==================== DEPLOY CODE ====================
log_info "Packaging function code..."
TMP_ZIP="/tmp/epic-scheduler.zip"
rm -f "${TMP_ZIP}"
(cd "${REPO_ROOT}/functions/epic-scheduler" && zip -qr "${TMP_ZIP}" .)

log_info "Deploying function package..."
az functionapp deployment source config-zip \
  --name "${EPIC_SCHEDULER_FUNCTION_APP_NAME}" \
  --resource-group "${AZURE_RESOURCE_GROUP}" \
  --src "${TMP_ZIP}" \
  --timeout 1800 \
  --only-show-errors \
  1>/tmp/epic-scheduler-deploy.json

# ==================== POST-DEPLOYMENT ====================
log_info "Retrieving function details..."

FUNCTION_KEY="$(az functionapp keys list \
  --name "${EPIC_SCHEDULER_FUNCTION_APP_NAME}" \
  --resource-group "${AZURE_RESOURCE_GROUP}" \
  --query functionKeys.default \
  -o tsv \
  --only-show-errors)" || true

FUNCTION_BASE_URL="https://${EPIC_SCHEDULER_FUNCTION_APP_NAME}.azurewebsites.net/api"

# Store in .env
log_info "Updating .env file..."
python3 - <<PY
from pathlib import Path

env_path = Path("${REPO_ROOT}/.env")
lines = env_path.read_text().splitlines()
updates = {
    "EPIC_SCHEDULER_FUNCTION_APP_NAME": "${EPIC_SCHEDULER_FUNCTION_APP_NAME}",
    "EPIC_SCHEDULER_STORAGE_ACCOUNT": "${EPIC_SCHEDULER_STORAGE_ACCOUNT}",
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

log_info "Deployment complete!"
echo ""
echo "==================================================================="
echo "Epic Scheduler Function Deployed"
echo "==================================================================="
echo "Function App Name: ${EPIC_SCHEDULER_FUNCTION_APP_NAME}"
echo "Resource Group: ${AZURE_RESOURCE_GROUP}"
echo "Storage Account: ${EPIC_SCHEDULER_STORAGE_ACCOUNT}"
echo "Function URL: ${FUNCTION_BASE_URL}/epic_scheduler"
echo ""
echo "Next steps:"
echo "1. Verify deployment in Azure Portal"
echo "2. Configure Review Endpoint Base URL if not already set"
echo "3. Monitor logs: az functionapp log tail --name ${EPIC_SCHEDULER_FUNCTION_APP_NAME} --resource-group ${AZURE_RESOURCE_GROUP}"
echo "4. Test orchestration with a pending epic"
echo "==================================================================="
