# Orchestrator Tool Contracts

## Preferred single endpoint

Use one orchestrator endpoint/tool in Foundry:

- `execute_orchestrator_cycle`
- Schema: `agents/orchestrator-agent/runbook-tool-schema.v1.json`
- OpenAPI import option: `agents/orchestrator-agent/openapi.execute-orchestrator-cycle.v1.yaml`

The endpoint internally executes the operations below. Keep the granular operations for fallback/debug only.

## `find_new_epics`

Input:

```json
{ "jql": "project = KAN AND issuetype = Epic AND status = \"NEW\"" }
```

## `get_epic_snapshot`

Input:

```json
{ "issue_key": "KAN-123" }
```

## `transition_epic_status`

Input:

```json
{
  "issue_key": "KAN-123",
  "from_status": "TRIAGE",
  "to_status": "READY FOR REFINEMENT",
  "reason": "Risk/contact/open questions verified",
  "evidence_links": ["https://..."]
}
```

## `write_epic_comment`

Input:

```json
{
  "issue_key": "KAN-123",
  "body": "Customer decision request..."
}
```

## `link_evidence`

Input:

```json
{
  "issue_key": "KAN-123",
  "artifact_type": "design|adr|scan|qa|release",
  "url": "https://...",
  "title": "string"
}
```

## `dispatch_agent_task`

Input:

```json
{
  "issue_key": "KAN-123",
  "agent_role": "po|architect|security|devops|dev|qa|finops|release",
  "task": "string",
  "due_utc": "2026-03-06T12:00:00Z"
}
```
