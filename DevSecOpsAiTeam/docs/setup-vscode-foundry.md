# Setup with VS Code + AI Foundry Extension

## Prerequisites

- Azure subscription with AI Foundry project.
- VS Code with AI Foundry extension installed.
- Jira Cloud project and API access.

## Steps

1. Open this repository in VS Code.
2. Sign in to Azure from the Foundry extension.
3. Select your Foundry project as active context.
4. Create a Foundry project connection for Function key auth and set:
   - `AI_FOUNDRY_OPENAPI_PROJECT_CONNECTION_ID=<connection-id>`
5. Create agent `orchestrator-agent`.
5. Paste instructions from:
   - `agents/orchestrator-agent/system-instructions.md`
6. Register orchestrator tool endpoints using:
   - `bash scripts/register-foundry-orchestrator-tool.sh`
   - this registers explicit OpenAPI operations from the Function tool adapter.
7. Configure environment values from `.env.example`.
8. Move secrets to Key Vault (recommended):
   - run `bash scripts/sync-secrets-to-keyvault.sh`
   - this stores secrets in Key Vault and clears local secret values in `.env`
9. Deploy review endpoint first:
   - optionally set `REVIEW_FUNCTION_APP_NAME` and `REVIEW_FUNCTION_STORAGE_ACCOUNT` in `.env`
   - optionally set `DOR_FIELD_MAP_JSON` in `.env` to map Jira custom fields for strict readiness checks
   - run `bash scripts/deploy-review-function.sh`
   - verify `REVIEW_ENDPOINT_BASE_URL` is written to `.env`
   - if `AZURE_KEY_VAULT_NAME` is set, function key is stored in Key Vault and `REVIEW_ENDPOINT_API_KEY` stays empty in `.env`
10. Configure Jira webhook/automation to call `/api/execute_orchestrator_cycle`.
11. Dry-run against one Jira test Epic:
   - `bash scripts/test-orchestrator-cycle.sh KAN-123`
12. Enable live event-driven execution only after dry-run passes.

## CLI shortcut for orchestrator tool

If you prefer script-based setup instead of manual Foundry UI:

1. Add these to `.env`:
   - `AI_FOUNDRY_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project-name>`
   - `AI_FOUNDRY_MODEL_DEPLOYMENT=gpt-4o-mini-agents` (or your deployed agents model)
2. Register/update orchestrator agent + OpenAPI tool:
   - `bash scripts/register-foundry-orchestrator-tool.sh`
3. Validate endpoint:
   - `bash scripts/test-orchestrator-cycle.sh`

## First Dry-Run Validation

- Workflow finds candidate Epics.
- Orchestrator evaluates gate checks and proposes/executes transitions.
- Orchestrator dispatches role stories and comments only when needed.
- Immediate re-run does not duplicate same missing-gate comment.
