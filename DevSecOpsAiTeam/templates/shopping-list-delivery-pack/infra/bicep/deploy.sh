#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 5 ]]; then
  echo "Usage: $0 <subscription-id> <resource-group> <location> <app-name> <plan-name> [sku]"
  exit 1
fi

SUBSCRIPTION_ID="$1"
RESOURCE_GROUP="$2"
LOCATION="$3"
APP_NAME="$4"
PLAN_NAME="$5"
SKU_NAME="${6:-B1}"

az account set --subscription "${SUBSCRIPTION_ID}"
az group create --name "${RESOURCE_GROUP}" --location "${LOCATION}" >/dev/null

az deployment group create \
  --resource-group "${RESOURCE_GROUP}" \
  --template-file "$(dirname "$0")/main.bicep" \
  --parameters appName="${APP_NAME}" planName="${PLAN_NAME}" skuName="${SKU_NAME}" location="${LOCATION}"

echo "Infra deployed."
echo "App URL: https://${APP_NAME}.azurewebsites.net"
