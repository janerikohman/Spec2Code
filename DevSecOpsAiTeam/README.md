# Spec2Code - 100% Agentic Orchestration (v2.0)

Epic-delivery workflow for Jira using **100% Agentic Architecture**:
- **AI Foundry**: Coordinator Agent (master orchestrator) + 8 role agents (autonomous, peer-to-peer collaboration)
- **Azure Function**: Minimal webhook receiver only (100 lines)
- **Jira**: Event-driven ingress and delivery tracking

## Repository Structure

### Core Agents (v2.0 - 100% Agentic)

- **`agents/coordinator-agent/`**
  - Master orchestrator instructions (450+ lines)
  - Responsible for epic orchestration, intelligent sequencing, feedback loops, gate verification
  - Runs in Azure AI Foundry

- **`agents/*-agent/`** (8 specialized agents)
  - `po-requirements-agent/` - Product Owner requirements gathering
  - `architect-agent/` - Architecture & design decisions
  - `security-architect-agent/` - Security posture & threat modeling
  - `devops-iac-agent/` - Infrastructure automation & cost optimization
  - `developer-agent/` - Implementation planning
  - `tester-qa-agent/` - Quality assurance & testability
  - `finops-agent/` - Cost optimization & budget tracking
  - `release-manager-agent/` - Release coordination & delivery verification
  
  All agents support:
  - Peer-to-peer communication via `invoke_agent()` tool
  - Confidence scoring (0.0-1.0) with feedback loops
  - Mandatory DoR gate verification per phase
  - Automatic Jira/Confluence integration

### Infrastructure & Configuration

- **`functions/review-endpoint/`**
  - `function_app.py` - Minimal webhook (100 lines) - delegates to Coordinator Agent
  - `coordinator_agent.py` - Orchestration engine (900 lines, fully implemented)
  - `requirements.txt` - Python dependencies

- **`agents/shared/`**
  - `agent-communication-protocol-v2.json` - Agent-to-agent messaging contract
  - `epic-state-machine-v2.json` - 19-state workflow for epic delivery
  - `evidence-requirements.md` - DoR gate definitions

### Configuration

- **`.env.agentic`** - Foundry agent registry, confidence thresholds, feature flags, Jira/Confluence endpoints
- **`.env.example`** - Template for local setup

### Documentation & Deployment

- **[DEPLOY-V2.md](DEPLOY-V2.md)** ⭐ **Deployment script → START HERE** (10 min to production)
- `docs/`
  - `architecture.md` - System design
  - `operations.md` - Operational procedures
  - `setup-vscode-foundry.md` - Foundry setup guide
- `shared/dor/`
  - Definition of Ready gates for each phase

## 🚀 Quick Deploy

1. Edit `.env.agentic` with your Foundry project ID
2. Run commands from [DEPLOY-V2.md](DEPLOY-V2.md) (~10 minutes)
3. Test with 3 test epics in Jira
4. Get approval → production ready

**Status**: Ready for immediate deployment
