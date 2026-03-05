# Minimum Cost Baseline

Use this baseline to keep the Jira Epic agent flow as cheap as possible while still useful.

## Service choices

- Azure Function App: Consumption plan only.
- Logic App: Consumption workflow (`Microsoft.Logic/workflows`).
- Azure Key Vault: Standard tier.
- Azure AI Foundry: one orchestrator agent, no extra projects/environments.

## Runtime settings

- `RUN_EVERY_MINUTES=120` (or 240 for even lower cost).
- `MAX_EPICS_PER_RUN=20` (reduce to 10 if board is small).
- Keep Logic App foreach concurrency at `1` (already configured).
- Keep orchestrator dedupe comments enabled (default `[orc-hash]` behavior).

## Guardrails implemented in scripts

- `scripts/deploy-review-function.sh`
  - Warns if Function App is not on Consumption (`Dynamic`) tier.
  - Assigns managed identity only when Jira+KeyVault integration is configured.
- `scripts/deploy-logic-app.sh`
  - Blocks schedule intervals under 60 minutes unless `ALLOW_HIGH_FREQUENCY_SCHEDULE=true`.
  - Blocks very high batch size (`MAX_EPICS_PER_RUN > 50`).

## Monthly hygiene

- Rotate Jira token in Key Vault (no redeploy needed).
- Review Logic App run history for unnecessary triggers.
- Keep only one active workflow in production until load justifies splitting.
