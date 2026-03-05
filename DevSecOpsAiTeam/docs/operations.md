# Operations Runbook

## Current Runtime Model

- Logic App runs on a recurrence schedule and scans Jira Epics.
- For each Epic, Logic App calls `execute_orchestrator_cycle`.
- Orchestrator performs gate checks, transitions, dispatches role stories, and posts missing-evidence comments.
- Missing-evidence comments are deduplicated by hash (`[orc-hash:...]`) to avoid 5-minute spam loops.

## Run Cadence

- Default low-cost cadence: every 60-240 minutes.
- Demo cadence: every 5 minutes (requires `ALLOW_HIGH_FREQUENCY_SCHEDULE=true`).
- Keep Logic App foreach concurrency at `1`.

## Monitoring

- Read `Compose_run_summary` from each Logic App run:
  - `run_id`
  - `epics_checked`
  - `completed_at_utc`
- For detailed behavior, inspect orchestrator action output per Epic:
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
- Disable orchestrator execution globally via:
  - `ORCHESTRATOR_RUN_ENABLED=false`

## Change Management

- Update state/gate logic in:
  - `functions/review-endpoint/function_app.py`
  - `agents/shared/epic-state-machine.v1.json`
- Redeploy after any workflow/function change:
  - `bash scripts/deploy-review-function.sh`
  - `bash scripts/deploy-logic-app.sh`
