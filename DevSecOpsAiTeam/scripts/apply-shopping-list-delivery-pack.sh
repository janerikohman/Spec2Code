#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <target-repo-path>"
  exit 1
fi

TARGET_REPO="$1"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TEMPLATE_DIR="${SCRIPT_DIR}/../templates/shopping-list-delivery-pack"

if [[ ! -d "${TARGET_REPO}" ]]; then
  echo "Target repo does not exist: ${TARGET_REPO}"
  exit 1
fi

mkdir -p "${TARGET_REPO}/infra/bicep" "${TARGET_REPO}/scripts"

cp "${TEMPLATE_DIR}/bitbucket-pipelines.yml" "${TARGET_REPO}/bitbucket-pipelines.yml"
cp "${TEMPLATE_DIR}/Dockerfile" "${TARGET_REPO}/Dockerfile"
cp "${TEMPLATE_DIR}/.dockerignore" "${TARGET_REPO}/.dockerignore"
cp "${TEMPLATE_DIR}/infra/bicep/main.bicep" "${TARGET_REPO}/infra/bicep/main.bicep"
cp "${TEMPLATE_DIR}/infra/bicep/deploy.sh" "${TARGET_REPO}/infra/bicep/deploy.sh"
cp "${TEMPLATE_DIR}/scripts/e2e-local.sh" "${TARGET_REPO}/scripts/e2e-local.sh"
cp "${TEMPLATE_DIR}/README.md" "${TARGET_REPO}/infra/README-delivery-pack.md"

chmod +x "${TARGET_REPO}/infra/bicep/deploy.sh" "${TARGET_REPO}/scripts/e2e-local.sh"

echo "Applied shopping-list delivery pack to ${TARGET_REPO}"
