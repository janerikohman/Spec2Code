# Spec2Code — Autonomous DevSecOps AI Team

Spec2Code is a fully autonomous, agent-driven epic delivery system.
A Jira epic enters the pipeline; a coordinated team of AI agents produces a
signed-off delivery package — no human intervention required between trigger
and outcome.

## How it works

```
Jira Epic  →  Azure Function (webhook)  →  Coordinator Agent (AI Foundry)
                                                    │
                    ┌───────────────────────────────┼───────────────────────┐
                    ▼               ▼               ▼                       ▼
              PO Agent       Architect Agent   Security Agent   DevOps / Dev / QA / FinOps / Release
                    │               │               │                       │
                    └───────────────┴───────────────┴───────────────────────┘
                                            │
                                   Delivery Package
                              (Jira comment + Confluence page)
```

- **Coordinator Agent** is the single orchestration decision-maker (RULE_1).
  It sequences specialists dynamically based on epic type — no static paths
  (RULE_9).
- **8 specialist agents** collaborate peer-to-peer via AI Foundry, each with
  confidence scoring and mandatory DoR gate verification.
- **All secrets** are stored in and retrieved from Azure Key Vault at runtime —
  never hardcoded, never in environment variables (RULE_15).
- **Jira + Confluence** share one email/API-key pair (RULE_16).
  **Bitbucket** uses its own separate credentials (RULE_17).

## Repository layout

```
DevSecOpsAiTeam/
├── agents/                  # System instructions for all 9 agents
│   ├── coordinator-agent/
│   ├── po-requirements-agent/
│   ├── architect-agent/
│   ├── security-architect-agent/
│   ├── devops-iac-agent/
│   ├── developer-agent/
│   ├── tester-qa-agent/
│   ├── finops-agent/
│   ├── release-manager-agent/
│   └── shared/              # Agent communication protocol, epic state machine
├── functions/
│   ├── review-endpoint/     # Azure Function + coordinator runtime + KV secrets
│   └── epic-scheduler/      # Scheduled orchestration trigger
├── scripts/                 # Operational and test scripts (all KV-backed)
├── docs/                    # Architecture, operations, setup guides
├── templates/               # Delivery pack templates (Bicep, Dockerfile, pipeline)
├── shared/dor/              # Definition of Ready gate definitions
├── .env.example             # Config template — copy to .env and populate
└── DEPLOY-V2.md             # Deployment guide — start here

.github/guardrails/          # Immutable governance enforcement
├── AGENT_GUARDRAILS.md      # 17 rules — single source of truth
├── AGENT_KNOWLEDGE_BASE.md  # Resolved blocker library
├── check_agent_guardrails.sh
└── check_no_legacy_agent_core.sh
```

## Quick start

```bash
# 1. Copy config template and set non-secret values
cp DevSecOpsAiTeam/.env.example DevSecOpsAiTeam/.env

# 2. Deploy to Azure (Key Vault, Function App, AI Foundry agents)
bash DevSecOpsAiTeam/DEPLOY-V2.md   # follow the guide

# 3. Verify guardrails pass before any deployment
bash .github/guardrails/check_agent_guardrails.sh
bash .github/guardrails/check_no_legacy_agent_core.sh
```

## Governance — immutable rules

All 17 rules are enforced by the guardrail scripts and embedded in the
coordinator system prompt. Key rules:

| Rule | Mandate |
|------|---------|
| RULE_1 | Coordinator Agent is the only orchestrator |
| RULE_9 | No fallback mode, no static/legacy orchestration paths |
| RULE_15 | All secrets in Azure Key Vault — never hardcoded |
| RULE_16 | Jira + Confluence share one email/API-key |
| RULE_17 | Bitbucket uses its own separate credentials |

See [.github/guardrails/AGENT_GUARDRAILS.md](.github/guardrails/AGENT_GUARDRAILS.md)
for the full rule set.

## Secret management

Required Key Vault secrets before first deploy:

| Secret name | Content |
|-------------|---------|
| `JIRA-EMAIL` | Email for Jira AND Confluence |
| `JIRA-API-TOKEN` | API token for Jira AND Confluence |
| `BITBUCKET-USERNAME` | Bitbucket account username |
| `BITBUCKET-APP-PASSWORD` | Bitbucket app-password |
| `BITBUCKET-WORKSPACE` | Bitbucket workspace slug |

## Branch

Active development: `feature/foundry-runtime-logging`  
Default: `main`

