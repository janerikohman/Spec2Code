# Spec2Code — End-to-End Demo Guide

**Duration**: ~20 minutes  
**What you show**: A Jira epic enters the system → AI agents orchestrate full delivery → Confluence pages, Jira dispatch stories, Bitbucket PR, delivery comments — all produced automatically.

---

## Pre-Demo Setup (5 min before)

Open these tabs in your browser and keep them ready:

| Tab | URL |
|-----|-----|
| Jira Board | https://shahosa.atlassian.net/jira/software/projects/KAN/boards |
| KAN-148 Epic | https://shahosa.atlassian.net/browse/KAN-148 |
| Confluence S2C | https://shahosa.atlassian.net/wiki/spaces/S2C |
| Bitbucket PR | https://bitbucket.org/shahosa/kan148-shopping-list-app/pull-requests/1 |
| Azure AI Foundry | https://ai.azure.com |

Open a terminal in VS Code and run:
```bash
cd /Users/shaho/Library/CloudStorage/OneDrive-KnowitAB/Poc/S2C/Spec2Code/DevSecOpsAiTeam
```

---

## Demo Script

### PART 1 — The Problem (2 min)

> *"Today I want to show you how we turn a Jira epic directly into shipped code — with zero manual hand-off between product, engineering, security, DevOps, and QA."*

> *"Normally a team has to organise meetings, write architecture docs, create tickets, set up pipelines... this system does all of that autonomously, using 8 AI agents working together."*

---

### PART 2 — Show the Epic (2 min)

Switch to **KAN-148** tab.

> *"Here's our epic — Shopping List Web App MVP. It has a full product spec: business goal, personas, acceptance criteria, NFRs, scope. This is the only input the system needs."*

Point out:
- Description section (business goal, scope, AC)
- Status: **In Progress** — the system already started working on it
- Comments section — scroll down to show the automated delivery comment posted by the system

---

### PART 3 — Show the AI Agent Platform (2 min)

Switch to **Azure AI Foundry** tab → Agents section.

> *"We have 9 agents running in Azure AI Foundry. One coordinator that orchestrates everything, and 8 specialists — PO, Architect, Security, DevOps, Developer, QA, FinOps, Release Manager."*

> *"Each agent has a system prompt defining its role, DoR gates, and tool contracts. They call real APIs — Jira, Confluence, Bitbucket — through an Azure Function that acts as a secure tool adapter."*

---

### PART 4 — Trigger a Live Orchestration Cycle (3 min)

Switch to terminal. Run:

```bash
../.venv/bin/python scripts/test_full_orchestration.py 2>&1
```

> *"I'm now triggering the coordinator agent on KAN-148. Watch what it does..."*

While it runs (~30 seconds), explain:
1. Coordinator reads the epic from Jira
2. Checks open dispatch stories
3. Creates a new developer story
4. Posts a progress comment
5. Transitions the epic status

Expected output:
```
Status: completed
Tools used: jira_get_issue_context, jira_list_open_dispatch_issues,
            jira_add_comment, jira_create_dispatch_story, jira_transition_issue
✅ FULL ORCHESTRATION CYCLE SUCCESSFUL
```

Switch to **KAN-148** in Jira, refresh — show:
- New comment: *"Orchestration cycle in progress..."*
- New child story created (KAN-15x)

---

### PART 5 — Show the Specialist Agents Publishing Documentation (4 min)

> *"Now let's see what happens when we dispatch all 8 specialists on this epic. Each one reads the Jira context and publishes a structured document to Confluence."*

Run:
```bash
../.venv/bin/python scripts/run_specialist_dispatch.py --epic KAN-148 2>&1
```

While it runs (~3 minutes), narrate each agent as it completes:
- **PO/Requirements** — checks completeness against Definition of Ready
- **Architect** — produces architecture decision record
- **Security Architect** — threat model and risk assessment
- **DevOps/IaC** — infrastructure design, pipeline blueprint
- **Developer** — implementation plan and story breakdown
- **QA/Tester** — test strategy and quality gate criteria
- **FinOps** — cost estimate and FinOps recommendations
- **Release Manager** — release plan and runbook

Expected summary:
```
✅ po-requirements        COMPLETED
✅ architect              COMPLETED
✅ security-architect     COMPLETED
✅ devops-iac             COMPLETED
✅ developer              COMPLETED
✅ tester-qa              COMPLETED
✅ finops                 COMPLETED
✅ release-manager        COMPLETED
8/8 agents completed
```

Switch to **Confluence S2C** tab, refresh.

> *"Every one of these pages was written by an AI agent reading the Jira epic and applying its domain expertise — in under 3 minutes."*

Click through pages:
- `KAN-148 – Architecture Design`
- `KAN-148 – Security Assessment`
- `KAN-148 – DevOps & IaC Design`
- `KAN-148 – Release Plan`

---

### PART 6 — Show the Delivery Package in Bitbucket (2 min)

Switch to **Bitbucket PR** tab.

> *"At the same time, the system created a full delivery package — Dockerfile, CI/CD pipeline, Azure Bicep infrastructure, deploy scripts — and opened a pull request targeting main."*

Show:
- PR title and description
- Branch: `epic/kan-148-delivery-pack` → `main`
- Files: `bitbucket-pipelines.yml`, `Dockerfile`, `infra/bicep/main.bicep`

> *"When this PR is merged, the pipeline runs automatically — builds the container, pushes to Azure Container Registry, deploys to Azure Container Apps."*

---

### PART 7 — Show the Full Evidence Trail in Jira (2 min)

Switch back to **KAN-148** in Jira.

> *"Everything the system did is traceable in Jira. The delivery comment links to the Bitbucket PR. Child stories are assigned to the right roles. The epic status was updated automatically."*

Point out:
- Status: **In Progress**
- Comments from the automated system (delivery evidence, orchestration cycle)
- Child stories: KAN-149, KAN-150, KAN-151, KAN-152

---

### PART 8 — Agent Health Check (1 min, optional)

> *"We can also smoke-test all agents at any time to confirm they're ready."*

```bash
../.venv/bin/python scripts/test_all_specialist_agents.py 2>&1 | tail -15
```

Expected:
```
✅ PO/Requirements      - PASS
✅ Architect            - PASS
✅ Security Architect   - PASS
✅ DevOps/IaC           - PASS
✅ Developer            - PASS
✅ QA/Tester            - PASS
✅ FinOps               - PASS
✅ Release Manager      - PASS
8/8 agents PASSED
```

---

### Close (1 min)

> *"To recap — one Jira epic, written by a product owner, triggered:*
> - *8 AI agents each performing domain-expert analysis*
> - *8 Confluence documentation pages published automatically*
> - *Dispatch stories created in Jira for each role*
> - *A full CI/CD delivery package pushed to Bitbucket with a PR ready to merge*
> - *Full audit trail in Jira*
>
> *The only human input was the epic description. Everything else was the system."*

---

## Troubleshooting During Demo

| Problem | Fix |
|---------|-----|
| Agent returns error | Re-run the script — transient Foundry timeouts self-recover |
| Confluence page not appearing | Refresh the space page; pages publish in ~10s after agent completes |
| `az` CLI not authenticated | `az login` in terminal, then retry |
| Jira shows old data | Hard refresh (Cmd+Shift+R) |
| Script exits with KV error | `az account show` to confirm subscription is active |

---

## Key URLs Reference

| Resource | URL |
|----------|-----|
| Jira project | https://shahosa.atlassian.net/jira/software/projects/KAN/boards |
| KAN-148 epic | https://shahosa.atlassian.net/browse/KAN-148 |
| Confluence S2C space | https://shahosa.atlassian.net/wiki/spaces/S2C |
| Bitbucket repo | https://bitbucket.org/shahosa/kan148-shopping-list-app |
| Bitbucket PR #1 | https://bitbucket.org/shahosa/kan148-shopping-list-app/pull-requests/1 |
| Azure Function (health) | https://epicreview257529268.azurewebsites.net/api/health |
| Azure AI Foundry | https://ai.azure.com |

## Commands Reference

```bash
# Working directory for all commands
cd /Users/shaho/Library/CloudStorage/OneDrive-KnowitAB/Poc/S2C/Spec2Code/DevSecOpsAiTeam

# Full coordinator orchestration cycle
../.venv/bin/python scripts/test_full_orchestration.py

# Dispatch all 8 specialists + publish Confluence docs
../.venv/bin/python scripts/run_specialist_dispatch.py --epic KAN-148

# Smoke test all 8 agents
../.venv/bin/python scripts/test_all_specialist_agents.py

# Post delivery comment to Jira
../.venv/bin/python scripts/post_delivery_comment.py --epic KAN-148 \
  --pr-url https://bitbucket.org/shahosa/kan148-shopping-list-app/pull-requests/1

# Check function health
curl -s https://epicreview257529268.azurewebsites.net/api/health
```
