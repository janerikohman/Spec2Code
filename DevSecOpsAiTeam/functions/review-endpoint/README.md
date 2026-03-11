# Review Endpoint Function

HTTP-triggered Azure Function that serves as the orchestration entry point for Spec2Code.

## Endpoints

- `GET /api/health` - Health check
- `GET /api/test` - Test endpoint  
- `POST /api/execute_orchestrator_cycle` - Main orchestration endpoint (called by epic-scheduler)

## Configuration

Set these environment variables in Azure Function App settings:

- `JIRA_BASE_URL` - Base URL for Jira (e.g. `https://your-org.atlassian.net`)
- `FOUNDRY_API_BASE` - Base URL for Foundry agents (default: https://api.microsoft.com/foundry)
- `KEY_VAULT_URL` - Azure Key Vault URL for secrets

## Orchestration Flow

1. Epic Scheduler detects new epics in Jira
2. Calls `/api/execute_orchestrator_cycle` with epic_keys
3. Review Endpoint coordinates 8 agents:
   - Architect Agent
   - Security Agent  
   - DevOps/IaC Agent
   - Developer Agent
   - QA/Tester Agent
   - FinOps Agent
   - Release Manager Agent
   - PO/Requirements Agent
