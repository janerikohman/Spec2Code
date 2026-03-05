# Architecture

## Components

- Jira Cloud
  - System of record for Epic state, decisions, approvals, and evidence links.
- Azure Logic App (`epic-review-workflow`)
  - Recurrence scheduler and Jira Epic scanner.
  - Calls orchestrator endpoint once per Epic.
- Azure Function (`review-endpoint`)
  - Hosts `execute_orchestrator_cycle`.
  - Evaluates gate checks, executes transitions, dispatches role stories, posts deduplicated missing-evidence comments.
- Azure Key Vault
  - Stores Jira/Bitbucket/API secrets consumed by scripts/function.
- Azure AI Foundry agents
  - Orchestrator + role agents (PO, Architect, Security, DevOps, QA, FinOps, Release).

## Responsibility Split

- Logic App:
  - Scheduling, Epic iteration, endpoint invocation.
- Function orchestrator:
  - Workflow state machine logic and side effects in Jira.
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

- Logic App run success does not imply transition success; inspect orchestrator action output.
- Orchestrator returns `errors` per Epic item (`transition_failed`, `dispatch_failed:*`).
- Recovery path:
  1. Fix gate evidence or Jira workflow/status mapping.
  2. Wait next schedule or run orchestrator endpoint manually.
