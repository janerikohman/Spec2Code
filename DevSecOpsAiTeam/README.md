# Spec2Code

Agentic Epic-delivery workflow for Jira using Azure AI Foundry + Logic App + Azure Function orchestrator.

## Repository Structure

- `agents/orchestrator-agent/`
  - Foundry instructions and tool schema/OpenAPI for the orchestrator agent.
- `agents/*-agent/`
  - Role-specific instructions for PO, Architect, Security, DevOps, QA, FinOps, Release.
- `logic-apps/epic-review-workflow/`
  - Scheduled Jira poller that calls orchestrator endpoint per Epic.
- `shared/dor/`
  - Versioned Definition of Ready (DoR) checklist schema.
- `shared/templates/`
  - Legacy DoR template assets used by `scripts/test-dor.sh`.
- `docs/`
  - Setup, architecture, and operational guidance.

## Quick Start

1. Read [setup-vscode-foundry.md](/Users/shaho/Library/CloudStorage/OneDrive-KnowitAB/Poc/S2C/Spec2Code/docs/setup-vscode-foundry.md).
2. Apply low-cost defaults from [min-cost-baseline.md](/Users/shaho/Library/CloudStorage/OneDrive-KnowitAB/Poc/S2C/Spec2Code/docs/min-cost-baseline.md).
3. Configure Jira and Azure values in `.env` based on `.env.example`.
4. Move secrets to Key Vault with `bash scripts/sync-secrets-to-keyvault.sh`.
5. Deploy review endpoint using `bash scripts/deploy-review-function.sh`.
6. Deploy the workflow with `bash scripts/deploy-logic-app.sh`.
7. Create/update your Foundry orchestrator agent using `agents/orchestrator-agent/system-instructions.md`.
8. Run one dry-run against a Jira test Epic before enabling/raising schedule frequency.

## Orchestrator Automation

- Register/update orchestrator agent tool in Foundry:
  - `bash scripts/register-foundry-orchestrator-tool.sh`
- Test orchestrator cycle (dry-run):
  - `bash scripts/test-orchestrator-cycle.sh`
- One-command demo (create Epic + run dry-run):
  - `bash scripts/demo-epic-progress.sh`
