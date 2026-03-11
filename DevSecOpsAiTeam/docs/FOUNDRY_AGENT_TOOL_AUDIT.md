# Foundry Agent / Tool Audit

Date: 2026-03-11

## Goal

Verify that:

1. Foundry remains the orchestrator/controller.
2. Azure Function is only a tool adapter.
3. Agent prompts, registered tools, and implemented Function routes are aligned.

## Current Verified Runtime Facts

- Tool-less Foundry agents run successfully.
- Tool-enabled Foundry agents fail at run start with `Azure.AI.Agents.Persistent.RunError` / server error.
- Direct Function tool endpoints work for Jira and Confluence after configuration fixes.
- Therefore the current hard blocker is the Foundry OpenAPI-tool runtime/connection path, not the basic Function runtime.

## Live Tool Inventory

### Function tool routes implemented

- `/api/tool/jira/get_issue_context`
- `/api/tool/jira/add_comment`
- `/api/tool/jira/transition_issue`
- `/api/tool/jira/list_open_dispatch_issues`
- `/api/tool/jira/create_dispatch_story`
- `/api/tool/confluence/create_page`

### Registered role tool sets

- `coordinator`: 6 OpenAPI functions
	- `jira_get_issue_context`
	- `jira_add_comment`
	- `jira_transition_issue`
	- `jira_list_open_dispatch_issues`
	- `jira_create_dispatch_story`
	- `confluence_create_page`
- `po-requirements`: 2 OpenAPI functions
	- `jira_get_issue_context`
	- `jira_add_comment`
- `architect`, `security-architect`, `devops-iac`, `developer`, `tester-qa`, `finops`, `release-manager`: 3 OpenAPI functions each
	- `jira_get_issue_context`
	- `jira_add_comment`
	- `confluence_create_page`

## Prompt / Tool Mismatches

### Coordinator prompt expectations not fully backed by current tools

The coordinator prompt references capabilities that do not currently exist as registered tools:

- `invoke_agent(...)`
- `jira_transition_epic(...)` (actual tool is `jira_transition_issue`)
- `jira_create_story(...)` (actual tool is `jira_create_dispatch_story`)
- `get_epic_context(...)` (actual tool is `jira_get_issue_context`)
- `ask_customer_for_clarification(...)` (can be approximated via Jira comments, but no dedicated tool)
- `escalate_to_human_review(...)` (no dedicated tool)

### Specialist prompts overstate currently available capabilities

Examples:

- `architect-agent` mentions Bitbucket read access and agent-to-agent invocation.
- `devops-iac-agent` mentions Bitbucket write access and Azure API access.
- `developer-agent` assumes broader execution and QA invocation capability.

At runtime these agents currently only receive Jira/Confluence OpenAPI tools, not Bitbucket/Azure tools.

## Configuration fixes already applied

- `CONFLUENCE_BASE_URL` corrected to Atlassian wiki base.
- `CONFLUENCE_SPACE_KEY` corrected to a valid space key (`PM`).
- `AI_FOUNDRY_ROLE_MODEL_MAP_JSON` updated to pin `coordinator` to `gpt-4o-mini-agents`.

## Platform-level blocker still active

Even a brand-new minimal pilot agent with exactly one OpenAPI tool (`jira_get_issue_context`) fails at run start.

This strongly indicates the remaining problem is in the current Foundry OpenAPI-tool runtime/connection behavior, not in the higher-level orchestration prompt.

## Best-practice next steps

1. Keep Foundry as orchestrator.
2. Keep Azure Function as tool adapter only.
3. Do not move orchestration logic back into the Function.
4. Align prompts to the actual tool contract, or add the missing tool adapters explicitly.
5. Add a dedicated Foundry-compatible agent invocation tool only if the design requires the coordinator to call specialist agents through a tool adapter.

## Recommended contract cleanup

### Coordinator should either:

- use only the currently available tool names and behaviors, or
- receive additional dedicated tools for:
	- role-agent invocation
	- customer clarification posting
	- explicit escalation handling

### Specialist prompts should be revised to reflect actual live tools unless Bitbucket/Azure tools are added.

## Practical conclusion

The repository now has a much clearer separation of responsibilities, but there are two remaining gaps:

1. **Platform/runtime gap:** Foundry OpenAPI tool runs still fail.
2. **Prompt-contract gap:** some prompts describe tools/capabilities that are not actually registered.
