# Architecture

## Live Resources (Sweden Central)

| Resource | Name / URL |
|----------|------------|
| Resource Group | `AgenticDevSecOps` |
| Tool Adapter Function | `epicreview257529268` → `https://epicreview257529268.azurewebsites.net/api` |
| Epic Scheduler Function | `epic-scheduler-agentic` |
| Key Vault | `kv-epic-po-2787129` |
| AI Foundry Project | `AgenticDevSecOpsTeam` → `agenticdevsecopsteam-resource.services.ai.azure.com` |
| Coordinator Agent | `asst_7J7tf7yRPJRdQcBvo0TIrNi2` |
| Jira | `https://shahosa.atlassian.net` — project `KAN` |
| Confluence | `https://shahosa.atlassian.net/wiki/spaces/S2C` — space `S2C` |
| Bitbucket | workspace `shahosa` |

## Components

- **Jira Cloud** — System of record for Epic state, decisions, approvals, and evidence links.
- **Epic Scheduler Function** (`epic-scheduler-agentic`) — Timer trigger every 5 minutes; polls Jira JQL for pending epics; calls `execute_orchestrator_cycle`.
- **Tool Adapter Function** (`epicreview257529268`) — Hosts `execute_orchestrator_cycle` and all `/api/tool/...` endpoints. Auth: ANONYMOUS (all routes).
- **Azure AI Foundry** — Coordinator Agent + 8 specialist agents. Agents call tools via the Function's OpenAPI spec.
- **Confluence `S2C` space** — Documentation target for all specialist agent artifacts.
- **Bitbucket workspace `shahosa`** — Delivery code target; one repo per epic.
- **Azure Key Vault `kv-epic-po-2787129`** — Stores all secrets consumed by functions and scripts.

## Tool Adapter Routes

```
POST /api/tool/jira/get_issue_context
POST /api/tool/jira/add_comment
POST /api/tool/jira/transition_issue
POST /api/tool/jira/list_open_dispatch_issues
POST /api/tool/jira/create_dispatch_story
POST /api/tool/confluence/create_page
POST /api/execute_orchestrator_cycle
GET  /api/health
```

## Responsibility Split

| Layer | Responsibility |
|-------|---------------|
| Jira Automation / Epic Scheduler | Ingress / event-driven trigger |
| Coordinator Agent (Foundry) | Orchestration: sequencing, gate checks, dispatch |
| Specialist Agents × 8 (Foundry) | Role reasoning, artifact generation, Confluence publishing |
| Tool Adapter Function | Deterministic side effects: Jira reads/writes, Confluence pages, Bitbucket |

## Agent Advisory Mode

All specialist agents have an **advisory-mode rule**: they only call `confluence_create_page` when the prompt explicitly requests publication. Review/analysis prompts return output inline and do not attempt to write to Confluence. This prevents 500 errors when Confluence space is unreachable or not specified.

## Idempotency and Anti-Spam

- One open dispatch story per `Epic + role`.
- Missing-evidence comments carry `[orc-hash:<hash>]`.
- Same missing-state hash is not posted repeatedly.

## Security and Secrets

- Function uses ANONYMOUS auth; network-level security is not yet enforced (suitable for PoC).
- Scripts and function load sensitive values from Key Vault at runtime.
- `.env` holds non-sensitive config and Key Vault secret names only.
- Bitbucket authentication: Basic auth (`BITBUCKET_EMAIL:bitbucket-api-token` from KV).
- Jira/Confluence authentication: Basic auth (`jira-email:jira-api-token` from KV).

## Failure Handling

- Orchestrator run success does not imply transition success; inspect returned action/output details.
- Recovery path:
  1. Fix gate evidence or Jira workflow/status mapping.
  2. Re-trigger via Jira automation or run `scripts/test_full_orchestration.py` manually.
- Agent Confluence 500: ensure space `S2C` exists at `shahosa.atlassian.net/wiki/spaces/S2C`.
- Bitbucket push failures: token is API-key type, not app-password; use REST API commit path (`POST /repositories/{ws}/{slug}/src`).
