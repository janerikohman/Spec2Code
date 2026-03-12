# Review Endpoint Function — Tool Adapter

HTTP-triggered Azure Function (`epicreview257529268`) that serves as the **tool adapter** for all Azure AI Foundry agents.

## Phase 1 Working Checkpoint (Locked Logic)

- `POST /api/execute_orchestrator_cycle` remains the orchestration execution entrypoint.
- Epic scheduler calls this endpoint on every timer cycle for pending epics.
- Core architecture/logic remains unchanged for Phase 1.
- Ongoing improvements are focused on agent behavior and output quality, not orchestration topology.

All routes use **ANONYMOUS** auth.

## Endpoints

| Method | Route | Purpose |
|--------|-------|---------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/execute_orchestrator_cycle` | Full orchestration cycle (called by epic-scheduler) |
| `POST` | `/api/tool/jira/get_issue_context` | Read Jira epic context |
| `POST` | `/api/tool/jira/add_comment` | Post comment to Jira issue |
| `POST` | `/api/tool/jira/transition_issue` | Transition Jira issue status |
| `POST` | `/api/tool/jira/list_open_dispatch_issues` | List open dispatch stories for an epic |
| `POST` | `/api/tool/jira/create_dispatch_story` | Create a role dispatch story under an epic |
| `POST` | `/api/tool/confluence/create_page` | Create a Confluence page in space `S2C` |

## Configuration (Azure Function App settings)

| Setting | Value / Source |
|---------|---------------|
| `JIRA_BASE_URL` | `https://shahosa.atlassian.net` |
| `JIRA_EMAIL_SECRET_NAME` | `jira-email` (Key Vault secret name) |
| `JIRA_API_TOKEN_SECRET_NAME` | `jira-api-token` (Key Vault secret name) |
| `CONFLUENCE_BASE_URL` | `https://shahosa.atlassian.net` |
| `CONFLUENCE_SPACE_KEY` | `S2C` |
| `AI_FOUNDRY_PROJECT_ENDPOINT` | Foundry project endpoint URL |
| `AZURE_KEY_VAULT_NAME` | `kv-epic-po-2787129` |

## Architecture Role

The Function is the **only** component that makes direct API calls to Jira, Confluence, and Bitbucket. Foundry agents call these routes as OpenAPI tools — they never call external APIs directly.
