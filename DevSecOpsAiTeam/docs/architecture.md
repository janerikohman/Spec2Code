# Architecture

## Components

- Jira Cloud
  - System of record for Epic state, decisions, approvals, and evidence links.
- Jira Automation/Webhook
  - Event-driven ingress to orchestrator endpoint.
- Azure Function (`review-endpoint`)
  - Hosts `execute_orchestrator_cycle` and explicit tool operations under `/api/tool/...`.
  - Works as execution/tool adapter for Jira/Confluence/Bitbucket side effects.
- Azure Key Vault
  - Stores Jira/Bitbucket/API secrets consumed by scripts/function.
- Azure AI Foundry agents
  - Orchestrator + role agents (PO, Architect, Security, DevOps, QA, FinOps, Release).

## Responsibility Split

- Jira Automation/Webhook:
  - Production trigger and ingress layer.
- Foundry agents:
  - Control plane, role reasoning, and role-specific decisions.
- Function tool adapter:
  - Deterministic side effects and data access for Jira/Confluence/Bitbucket.
- Foundry role agents:
  - Execute role work and publish evidence back to Jira/Confluence/Bitbucket.

## Idempotency and Anti-Spam

- One open dispatch story per `Epic + role`.
- Missing-evidence comments carry `[orc-hash:<hash>]`.
- Same missing-state hash is not posted repeatedly.

## Security and Secrets

- Function and deployment scripts load sensitive values from Key Vault.
- `.env` keeps non-sensitive settings and secret names.
- Bitbucket API token is used via Basic auth (`email:token`).

## Failure Handling

- Orchestrator run success does not imply transition success; inspect returned action/output details.
- Orchestrator returns `errors` per Epic item (`transition_failed`, `dispatch_failed:*`).
- Recovery path:
  1. Fix gate evidence or Jira workflow/status mapping.
  2. Re-trigger from Jira event (webhook/automation) or run orchestrator endpoint manually.
