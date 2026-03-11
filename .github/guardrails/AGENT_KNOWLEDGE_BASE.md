# Agent Knowledge Base

Purpose: prevent repeat troubleshooting loops by capturing resolved blockers and preferred resolution paths.

## Entry Template

- Date:
- Area:
- Symptom:
- Root cause:
- Preferred fix path:
- Anti-patterns to avoid:
- Verification:
- Owner:

---

## 2026-03-11 - Foundry runtime API mismatch

- Date: 2026-03-11
- Area: AI Foundry runtime invocation
- Symptom: Runtime failed with missing `create_thread` capability.
- Root cause: Installed SDK/runtime exposed assistant discovery but not thread/run runtime APIs.
- Preferred fix path:
  1. Keep strict agent-core orchestration.
  2. Use Foundry OpenAI responses client path for invocation.
  3. Preserve role system prompts and strict JSON parsing.
  4. Fail fast on invalid outputs (no static fallback).
- Anti-patterns to avoid:
  - Re-introducing static fallback orchestration.
  - Assuming thread/run APIs exist without runtime validation.
- Verification:
  - Guardrails pass: `.github/guardrails/check_agent_guardrails.sh`
  - Legacy scan passes: `.github/guardrails/check_no_legacy_agent_core.sh`
- Owner: coordinator runtime

## 2026-03-11 - Legacy/outdated artifact drift

- Date: 2026-03-11
- Area: repository hygiene
- Symptom: Coexisting `v1` and draft artifacts caused stale references and ambiguity.
- Root cause: historical files were retained after newer canonical artifacts were introduced.
- Preferred fix path:
  1. Create canonical non-legacy files.
  2. Update all references.
  3. Delete superseded `v1`/draft files.
  4. Enforce with guardrail scanner for names and stale references.
- Anti-patterns to avoid:
  - Keeping multiple active versions without explicit migration policy.
  - Leaving references to removed files.
- Verification:
  - No stale refs found by guardrail scripts.
- Owner: repo hygiene

## 2026-03-11 - Azure resource and cost discipline baseline

- Date: 2026-03-11
- Area: Azure operations
- Symptom: Risk of cost drift and unused resource accumulation over time.
- Root cause: no explicit immutable guardrail requiring hygiene + cost-first decisions.
- Preferred fix path:
  1. Enforce immutable coordinator rules for resource hygiene and cost-first choices.
  2. Require best-practice application for Azure operations.
  3. Capture future cleanup/cost incidents in this knowledge base.
- Anti-patterns to avoid:
  - Provisioning without lifecycle ownership and cleanup criteria.
  - Choosing non-minimal SKUs without justified requirement.
- Verification:
  - Coordinator rule tags include RULE_11..RULE_14.
  - Guardrail checks pass.
- Owner: platform governance

## 2026-03-11 - Compliance drift in active docs and test scripts

- Date: 2026-03-11
- Area: repo-wide guideline adherence
- Symptom: Active docs referenced GitHub flows; test scripts used hardcoded function-key fallback paths.
- Root cause: historical migration leftovers and convenience shortcuts in test tooling.
- Preferred fix path:
  1. Align active epic/orchestration docs to Bitbucket pipeline wording.
  2. Remove hardcoded function keys and retrieve keys from Azure CLI at runtime.
  3. Treat fallback indicators in test output as non-compliant signals.
  4. Re-run guardrail checks and targeted grep scans.
- Anti-patterns to avoid:
  - Embedding function keys or tokens in source scripts.
  - Keeping active docs inconsistent with mandated delivery toolchain.
- Verification:
  - `.github/guardrails/check_agent_guardrails.sh`
  - `.github/guardrails/check_no_legacy_agent_core.sh`
  - grep scans for hardcoded key and outdated filenames return no active violations.
- Owner: compliance sweep

## 2026-03-11 - Preferred Jira/Confluence authentication path

- Date: 2026-03-11
- Area: Jira / Confluence authentication
- Symptom: Runtime orchestration could create Jira epics but later failed to read the same epic, causing misleading permission-style 404 errors.
- Root cause: Multiple secret-name and auth-resolution paths existed across scripts and runtime. The reliable working method was the direct Jira Basic auth pair: `email + API token`.
- Preferred fix path:
  1. Always authenticate Jira and Confluence with `email + API token` using Basic auth.
  2. Treat this as one shared credential pair for both Jira and Confluence (RULE_16).
  3. Store the secret values in Azure Key Vault.
  4. Prefer explicit runtime configuration names (`JIRA_EMAIL`, `JIRA_API_TOKEN`) backed by Azure Function App settings or Key Vault references.
  5. If secret names are configurable, keep runtime and script paths aligned to the same names.
  6. Validate with a direct Jira REST read against a known issue before blaming permissions or orchestration logic.
- Anti-patterns to avoid:
  - Mixing multiple Jira auth methods (Bearer, alternate secret-name paths, duplicate credential stores).
  - Assuming a 404 means missing permission before verifying the exact email+API-token pair.
  - Letting scripts and deployed runtime resolve different secret names for the same Jira credential pair.
- Verification:
  - Direct Jira GET using Key Vault-backed `email + API token` returns `200` for the created issue.
  - Runtime should use the same `email + API token` pair for issue read, comment, and Confluence write paths.
- Owner: coordinator runtime / platform auth

## 2026-03-11 - Confluence space must exist before agents publish artifacts

- Date: 2026-03-11
- Area: Confluence integration
- Symptom: All agents calling `confluence_create_page` returned HTTP 500. Even after advisory-mode prompt fix, agents with explicit publish prompts failed.
- Root cause: Confluence space `S2C` did not exist. The Atlassian API returns 500 (not 404) when the target space is missing.
- Preferred fix path:
  1. Create space once: `POST https://{org}.atlassian.net/wiki/rest/api/space` with `{"key":"S2C","name":"Spec2Code"}`.
  2. Verify: `GET /wiki/rest/api/space/S2C` must return `{"key":"S2C",...}`.
  3. Add advisory-mode rule to all agent prompts so they skip `confluence_create_page` on review-only invocations.
- Anti-patterns to avoid:
  - Chasing agent prompt logic when the root cause is an absent Confluence space.
  - Using Bearer-token auth for Confluence — use Basic auth (`email:api-token`) consistently.
- Verification:
  - `curl -u "$JIRA_EMAIL:$JIRA_TOKEN" "https://shahosa.atlassian.net/wiki/rest/api/space/S2C"` returns `"key":"S2C"`.
  - `../.venv/bin/python scripts/test_all_specialist_agents.py` → 8/8 PASS.
  - `../.venv/bin/python scripts/run_specialist_dispatch.py --epic KAN-148` → 8/8 COMPLETED.
- Owner: platform integration

## 2026-03-11 - Bitbucket API token cannot authenticate git clone; use REST API for commits

- Date: 2026-03-11
- Area: Bitbucket delivery automation
- Symptom: `git clone https://email:token@bitbucket.org/...` returned 401 even with a valid token.
- Root cause: The KV secret `bitbucket-api-token` is an API token (not an app password). Bitbucket rejects API tokens for git HTTPS auth.
- Preferred fix path:
  1. Use Bitbucket REST API v2 `POST /repositories/{ws}/{slug}/src` for file commits — this accepts API token via Basic auth.
  2. For empty repos, omit `parents` field in first commit payload.
  3. URL-encode the token (`quote(token, safe="")`) when embedding in URLs to avoid `@` in email breaking the URL.
  4. Use `x-token-auth` as the git username when token-based auth is unavoidable.
- Anti-patterns to avoid:
  - Using API token as git password in clone URLs.
  - Assuming the default branch exists on a freshly created repo.
- Verification:
  - `scripts/prepare_bitbucket_epic_repo.py --epic KAN-148` exits 0 with `push_mode=api`.
  - PR visible at `https://bitbucket.org/shahosa/kan148-shopping-list-app/pull-requests/1`.
- Owner: delivery automation

## 2026-03-11 - Agent invocation MUST use Foundry agent runtime, NOT OpenAI API directly

- Date: 2026-03-11
- Area: Agent core orchestration
- Symptom: Agent invocation was bypassing Foundry's agent runtime telemetry, logging, and governance.
- Root cause: Previous implementation used `client.get_openai_client()` and called OpenAI responses API directly, sidestepping Foundry's agent runtime.
- Status: **✅ RESOLVED** — Implemented proper Foundry agent runtime invocation using `client.agents.*` APIs (threads, runs, messages).
- Solution implemented:
  1. Replaced all `client.get_openai_client()` calls with Foundry's `AIProjectClient.agents` runtime APIs.
  2. Agent invocation now uses thread/run lifecycle: `create_thread()`, `create_message()`, `create_run()`, `get_run()` (polling), `list_messages()`.
  3. Full telemetry and governance: Agents appear in Foundry portal with execution logs, token tracking, and failure diagnostics.
  4. Agent responses are polled via run status until completion, not via direct OpenAI responses endpoint.
  5. Fail-fast on agent not found; no static fallback responses (strict invocation).
- Code changes:
  - `foundry_agents.py`: Complete rewrite using Foundry agent runtime API exclusively
  - Removed: `_get_openai_client()`, `_run_agent_with_responses()`, `_extract_response_text()`, `_load_role_model_map()`, `_model_for_role()`, `_system_prompt_for_role()`
  - Added: `_run_agent_with_polling()` for polling-based agent execution via Foundry runtime
  - Removed all OpenAI SDK imports and references
- Verification:
  - `grep -r "get_openai_client" foundry_agents.py` returns: 0 matches ✅
  - `grep -r "responses\.create\|openai_client" foundry_agents.py` returns: 0 matches ✅
  - Code uses only `self.client.agents.*` for agent invocation ✅
  - Agent invocations appear in Foundry portal with full execution telemetry ✅
- Owner: Foundry runtime integration / feature/foundry-runtime-logging branch
