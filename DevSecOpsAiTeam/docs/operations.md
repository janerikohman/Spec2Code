# Operations Runbook

## Current Runtime Model

- Jira event-driven automation/webhook calls `/api/execute_orchestrator_cycle`.
- Foundry agents are control plane; Function app is tool adapter via explicit operations (`/api/tool/...`).
- Orchestrator performs gate checks, transitions, dispatches role stories, and posts missing-evidence comments.
- Missing-evidence comments are deduplicated by hash (`[orc-hash:...]`).

## Trigger Model

- Production trigger is event-driven from Jira only.
- Manual validation trigger remains available via:
  - `bash scripts/test-orchestrator-cycle.sh`

## Monitoring

- For behavior, inspect orchestrator output per Epic:
  - `gate_checks`
  - `proposed_actions`
  - `executed_actions`
  - `errors`

## Secret Management

- Store secrets in Azure Key Vault:
  - `jira-email`
  - `jira-api-token`
  - `review-endpoint-api-key`
  - `bitbucket-api-token` (if Bitbucket automation enabled)
- Keep `.env` for non-sensitive config and secret names only.

## Guardrails

- Do not process terminal Epics (`Done`).
- Do not post duplicate missing-evidence comments unless missing-state changed.
- Keep one open dispatch story per `Epic + role` until sign-off/done.
- Only orchestrator can transition Epic status.
- Customer communication stays in Epic thread; Epic creator is the only human participant.

## Manual Override

- Add label `agent-ignore` to skip an Epic (if this rule is implemented in your fork/runtime).

## Change Management

- Update state/gate logic in:
  - `functions/review-endpoint/function_app.py`
  - `agents/shared/epic-state-machine.json`
- Update role behavior prompts in:
  - `agents/*/system-instructions.md`
  - Re-register assistants after prompt updates:
    - `bash scripts/register-foundry-role-assistants.sh`
- Redeploy after any workflow/function change:
  - `bash scripts/deploy-review-function.sh`

## Execution Baseline For Real Delivery

- Apply runnable delivery assets to the target app repository:
  - `bash scripts/apply-shopping-list-delivery-pack.sh <target-repo-path>`
- Required generated assets:
  - `bitbucket-pipelines.yml`
  - `infra/bicep/main.bicep`
  - `infra/bicep/deploy.sh`
  - `scripts/e2e-local.sh`
- Role expectation:
  - DevOps agent commits pipeline/IaC.
  - Developer agent commits feature code + tests.
  - QA agent runs e2e and links evidence.
