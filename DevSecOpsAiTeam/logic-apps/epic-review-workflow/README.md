# Epic Review Logic App

Main deployable template: `workflow.json`

## Current Flow (Orchestrator-Only)

1. `Recurrence` trigger (configured by `runEveryMinutes`).
2. Jira search for Epics via `epicJql`.
3. For each Epic:
   - increment run counter
   - call Azure Function endpoint:
     - `POST /api/execute_orchestrator_cycle`
     - mode: `single_epic`
4. Emit compact run summary.

There is no legacy `review_epic` label/template branch in the active workflow.

## Required Parameters

- `jiraBaseUrl`
- `jiraEmail` (secure)
- `jiraApiToken` (secure)
- `jiraProjectKey`
- `epicJql`
- `reviewEndpointUrl`
- `reviewEndpointApiKey` (secure)
- `runEveryMinutes`
- `maxEpicsPerRun`
- `orchestratorRunEnabled`
- `orchestratorDryRun`
- `orchestratorAllowTransitionExecution`
- `orchestratorAllowDispatchExecution`
- `orchestratorAllowCommentExecution`

## Deployment

- `bash scripts/deploy-logic-app.sh`

The deploy script loads secrets from Key Vault when configured in `.env`.
