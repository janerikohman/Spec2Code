# Foundry Multi-Agent Rollout

## Goal

Instantiate the Epic-delivery multi-agent model in Azure AI Foundry, using Jira Epic as system of record.

## Recommended rollout order

1. Orchestrator agent
   - Use: `agents/orchestrator-agent/system-instructions.md`
   - Preferred tool: `execute_orchestrator_cycle`
   - Tool schema: `agents/orchestrator-agent/runbook-tool-schema.v1.json`
   - Keep granular tools only as fallback/debug path
2. PO/Requirements agent
   - Use: `agents/po-requirements-agent/system-instructions.md`
3. Architect agent
   - Use: `agents/architect-agent/system-instructions.md`
4. Security architect agent
   - Use: `agents/security-architect-agent/system-instructions.md`
5. DevOps/IaC agent
   - Use: `agents/devops-iac-agent/system-instructions.md`
6. QA agent
   - Use: `agents/tester-qa-agent/system-instructions.md`
7. FinOps agent
   - Use: `agents/finops-agent/system-instructions.md`
8. Release manager agent
   - Use: `agents/release-manager-agent/system-instructions.md`

## Shared policy artifacts

- State machine: `agents/shared/epic-state-machine.v1.json`
- Evidence rules: `agents/shared/evidence-requirements.v1.md`
- Model overview: `docs/multi-agent-delivery-model.md`

## Non-negotiable runtime rules

- Only orchestrator transitions Epic status.
- Customer communication only in Epic comments/fields.
- No budget exception/policy gate change without linked approval artifact.
- Every major artifact must link back to the Epic.

## First UAT scenario

1. Create Epic in `NEW` with minimal info.
2. Run orchestrator:
   - Move to `TRIAGE` only if intake evidence exists.
3. Run PO:
   - Ask missing questions in Epic.
4. Run architect/security:
   - Produce design/ADR/security evidence links.
5. Verify orchestrator transition decisions align to state-machine evidence gates.

## Tool registration notes

Register `execute_orchestrator_cycle` in Foundry as a custom tool with:

- input schema from `agents/orchestrator-agent/runbook-tool-schema.v1.json` `input_schema`
- output contract from `output_schema`
- start with `dry_run=true` in UAT, then allow execution flags incrementally

Or import the OpenAPI file directly:

- `agents/orchestrator-agent/openapi.execute-orchestrator-cycle.v1.yaml`

Automation option (recommended):

1. Set in `.env`:
   - `AI_FOUNDRY_PROJECT_ENDPOINT`
   - `AI_FOUNDRY_MODEL_DEPLOYMENT` (default `gpt-4o-mini`)
2. Run:
   - `bash scripts/register-foundry-orchestrator-tool.sh`
3. Dry-run orchestrator endpoint:
   - `bash scripts/test-orchestrator-cycle.sh`
   - or single Epic: `bash scripts/test-orchestrator-cycle.sh KAN-123`
