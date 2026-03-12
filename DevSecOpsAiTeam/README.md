# Spec2Code — Agentic DevSecOps Delivery (v2.0)

Automated epic-delivery pipeline using **100% Agentic Architecture** on Azure AI Foundry.

## Phase 1 Working Checkpoint (Locked Logic)

- `epic-scheduler-agentic` timer trigger is active on `0 */5 * * * *` (every 5 minutes).
- Scheduler responsibility is unchanged and minimal: query pending Jira epics and call `POST /api/execute_orchestrator_cycle`.
- `review-endpoint` remains the orchestration executor and agent coordinator.
- Core architecture and orchestration logic are now treated as **locked for Phase 1**.
- Future work is limited to agent-quality and execution improvements, not architecture/logic changes.

## Phase 2 Execution Hardening (No Architecture/Logic Change)

- Phase 2 keeps the same architecture and orchestration logic from Phase 1.
- Blockers are fixed in-place with targeted changes only (no topology refactor).
- Follow [docs/PHASE2_IMPLEMENTATION_CHECKLIST.md](docs/PHASE2_IMPLEMENTATION_CHECKLIST.md) for acceptance criteria and evidence requirements.
- Epic completion now requires user-visible outcomes: app URL, test report, deployment proof, and story closure traceability.

| Component | Resource | Status |
|-----------|----------|--------|
| Coordinator Agent | `asst_7J7tf7yRPJRdQcBvo0TIrNi2` | ✅ Live |
| 8 Specialist Agents | see `.env` `AI_FOUNDRY_ROLE_AGENT_MAP_JSON` | ✅ 8/8 PASS |
| Tool Adapter (Function) | `epicreview257529268.azurewebsites.net` | ✅ Running |
| Epic Scheduler | `epic-scheduler-agentic` | ✅ Running (every 5 min) |
| Key Vault | `kv-epic-po-2787129` | ✅ Active |
| Confluence space | `S2C` — shahosa.atlassian.net/wiki/spaces/S2C | ✅ Created |
| Jira project | `KAN` — shahosa.atlassian.net | ✅ Active |
| Bitbucket workspace | `shahosa` | ✅ Active |

---

## Repository Structure

### Agents

- **`agents/coordinator-agent/`** — Master orchestrator: sequences specialist roles, gates, dispatches stories
- **`agents/*-agent/`** — 8 specialist roles, each with advisory-mode Confluence publishing:
  - `po-requirements-agent/` — Requirements analysis
  - `architect-agent/` — Architecture & ADR
  - `security-architect-agent/` — Threat model & security posture
  - `devops-iac-agent/` — IaC, pipelines, cost optimisation
  - `developer-agent/` — Implementation planning
  - `tester-qa-agent/` — Test strategy & quality gates
  - `finops-agent/` — Cost estimates & FinOps analysis
  - `release-manager-agent/` — Release plan & runbook
- **`agents/shared/`** — Agent communication protocol, epic state machine, evidence requirements

> **Advisory-mode rule**: agents only call `confluence_create_page` when explicitly asked, never on review-only prompts.

### Functions (Azure)

- **`functions/review-endpoint/`** — Tool adapter (`function_app.py`). Exposes:
  - `POST /api/tool/jira/get_issue_context`
  - `POST /api/tool/jira/add_comment`
  - `POST /api/tool/jira/transition_issue`
  - `POST /api/tool/jira/list_open_dispatch_issues`
  - `POST /api/tool/jira/create_dispatch_story`
  - `POST /api/tool/confluence/create_page`
  - `POST /api/execute_orchestrator_cycle`
  - `GET  /api/health`
- **`functions/epic-scheduler/`** — Timer trigger (every 5 min): polls Jira JQL for pending epics, calls `execute_orchestrator_cycle`

### Scripts

| Script | Purpose |
|--------|---------|
| `scripts/register-foundry-role-assistants.sh` | Register / update all 9 Foundry agents |
| `scripts/test_all_specialist_agents.py` | Smoke-test all 8 specialists (expect 8/8 PASS) |
| `scripts/run_specialist_dispatch.py` | Dispatch all specialists on an epic + publish Confluence pages |
| `scripts/prepare_bitbucket_epic_repo.py` | Create Bitbucket repo + push delivery pack |
| `scripts/create_bitbucket_pr.py` | Open Bitbucket PR for epic delivery branch |
| `scripts/post_delivery_comment.py` | Post delivery evidence comment to Jira |
| `scripts/test_full_orchestration.py` | E2E coordinator orchestration cycle test |
| `scripts/test-orchestrator-cycle.sh` | Manual bash orchestration trigger |
| `scripts/deploy-review-function.sh` | Deploy review-endpoint to Azure |
| `scripts/deploy-epic-scheduler.sh` | Deploy epic-scheduler to Azure |
| `scripts/sync-secrets-to-keyvault.sh` | Push secrets from `.env` to Key Vault |

### Configuration

- **`.env`** — All config: Foundry endpoints, agent IDs, Jira/Bitbucket settings, secret names
- **`templates/shopping-list-delivery-pack/`** — Delivery pack template applied to Bitbucket repos per epic

---

## Quick Start

```bash
# 1. Copy and fill config
cp .env.example .env   # fill JIRA_BASE_URL, AI_FOUNDRY_PROJECT_ENDPOINT, etc.

# 2. Sync secrets to Key Vault
bash scripts/sync-secrets-to-keyvault.sh

# 3. Register all Foundry agents
bash scripts/register-foundry-role-assistants.sh

# 4. Verify 8/8 agents pass
../.venv/bin/python scripts/test_all_specialist_agents.py

# 5. Run e2e orchestration on an epic
../.venv/bin/python scripts/test_full_orchestration.py

# 6. Dispatch specialists + publish Confluence docs
../.venv/bin/python scripts/run_specialist_dispatch.py --epic KAN-148
```

See [DEPLOY-V2.md](DEPLOY-V2.md) for full Azure deployment steps.

**Current status**: ✅ Production — 8/8 agents live, KAN-148 delivered, Confluence S2C populated
