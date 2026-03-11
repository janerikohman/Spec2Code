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

- Store secrets in Azure Key Vault `kv-epic-po-2787129`:
  - `jira-email`
  - `jira-api-token`
  - `review-endpoint-api-key`
  - `bitbucket-api-token` — Bitbucket API token (Basic auth: `BITBUCKET_EMAIL:token`)
- Keep `.env` for non-sensitive config and secret names only.
- Push secrets to KV: `bash scripts/sync-secrets-to-keyvault.sh`

## Preferred Authentication Method

- Jira and Confluence MUST use the same authentication method:
  - **username/email + API token** via **Basic auth**
- This is the preferred and canonical path for both scripts and deployed runtime.
- Store the secret values in Azure Key Vault and expose them consistently to runtime.
- Preferred runtime configuration:
  - `JIRA_EMAIL`
  - `JIRA_API_TOKEN`
  - These may be populated directly as Azure Function App settings or via Key Vault references.
- If using configurable secret names, ensure the same names are used by:
  - local scripts
  - deployed Function App
  - coordinator runtime

### Verification sequence

1. Resolve `email + API token` from Key Vault.
2. Perform a direct Jira REST read on a known epic:
   - `GET /rest/api/2/issue/{EPIC_KEY}`
3. Only after this succeeds, test `/api/execute_orchestrator_cycle`.
4. If orchestration fails with Jira `404`, verify runtime is using the same `email + API token` pair as the successful direct Jira probe.

## Agent Architecture Rules

### RULE: Agent invocation MUST use Foundry agent runtime, NOT OpenAI API directly

**Direct OpenAI invocation is forbidden in this runtime.**

- ✅ Implemented via Foundry runtime APIs only (`client.agents.*`)
- ✅ No direct OpenAI fallbacks in Python source
- ✅ Invocation flow: thread → user message → run → poll run status → read assistant messages

**Verification:**
```bash
# No direct OpenAI runtime usage in Python code
grep -R "get_openai_client\|responses\.create\|openai_client\|from openai\|import openai" . --include="*.py" | wc -l
# Expected: 0

# Foundry runtime APIs are used
grep -R "client\.agents\." functions/review-endpoint/foundry_agents.py | wc -l
# Expected: >0
```

**Implementation location:** `functions/review-endpoint/function_app.py` (coordinator_agent.py)
- All agent invocations use `AgentsClient` from `azure.ai.agents`
- Thread → user message → `runs.create_and_process()` → assistant message read

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
  - `agents/shared/epic-state-machine-v2.json`
- Update role behaviour prompts in:
  - `agents/*/system-instructions.md`
  - Re-register assistants after prompt updates: `bash scripts/register-foundry-role-assistants.sh`
  - Verify agents: `../.venv/bin/python scripts/test_all_specialist_agents.py`
- Redeploy after any function change: `bash scripts/deploy-review-function.sh`

## Confluence Space

- Space `S2C` must exist at `https://shahosa.atlassian.net/wiki/spaces/S2C`.
- To create if missing:
  ```bash
  JIRA_TOKEN=$(az keyvault secret show --vault-name kv-epic-po-2787129 --name jira-api-token --query value -o tsv)
  JIRA_EMAIL=$(az keyvault secret show --vault-name kv-epic-po-2787129 --name jira-email --query value -o tsv)
  curl -u "$JIRA_EMAIL:$JIRA_TOKEN" -X POST "https://shahosa.atlassian.net/wiki/rest/api/space" \
    -H "Content-Type: application/json" \
    -d '{"key":"S2C","name":"Spec2Code"}'
  ```

## Delivery Automation (per Epic)

```bash
# 1. Prepare Bitbucket repo + push delivery pack
../.venv/bin/python scripts/prepare_bitbucket_epic_repo.py --epic KAN-148

# 2. Open Bitbucket PR
../.venv/bin/python scripts/create_bitbucket_pr.py --epic KAN-148 --repo-slug kan148-shopping-list-app

# 3. Post delivery evidence to Jira
../.venv/bin/python scripts/post_delivery_comment.py --epic KAN-148 --pr-url <PR_URL>

# 4. Dispatch all specialists + publish Confluence docs
../.venv/bin/python scripts/run_specialist_dispatch.py --epic KAN-148
```

- Delivery pack template: `templates/shopping-list-delivery-pack/`
- Includes: `bitbucket-pipelines.yml`, `Dockerfile`, `infra/bicep/main.bicep`, `infra/bicep/deploy.sh`, `scripts/e2e-local.sh`
