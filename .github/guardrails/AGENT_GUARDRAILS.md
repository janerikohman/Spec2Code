# Agent-Core Guardrails

This is the single source of truth for orchestration guardrails.

## Immutable Rules

- RULE_1_AGENT_ORCHESTRATOR: Agents are the only core orchestrators and decision makers.
- RULE_2_AGENT_CLARIFICATION: Agents must ask each other questions to resolve ambiguity.
- RULE_3_TOOLS_ONLY: Jira, Confluence, Bitbucket, Azure Functions are tools used by agents.
- RULE_4_JIRA_TRACKING: Jira is required for work tracking and decision visibility.
- RULE_5_CONFLUENCE_DOCS: Confluence is required for documentation artifacts.
- RULE_6_BITBUCKET_CODE_PIPELINE: Bitbucket is required for code and pipeline workflow.
- RULE_7_INFRA_DECIDED_BY_RESPONSIBLE_AGENT: Responsible specialist agent decides infrastructure (including VM usage).
- RULE_8_HUMAN_CLARIFICATION_ON_UNCLEAR: If topology/governance is unclear, ask the human user before changing behavior.
- RULE_9_NO_FALLBACK_NO_LEGACY: No fallback mode and no legacy/static orchestration logic.
- RULE_10_NO_OUTDATED_ARTIFACTS: Do not keep outdated/legacy/draft artifacts in the repository; maintain only current canonical files.
- RULE_11_AZURE_RESOURCE_HYGIENE: Keep Azure resources clean; identify and remove unused resources safely.
- RULE_12_COST_EFFICIENCY_FIRST: Cost efficiency is mandatory; prefer lowest-cost viable options.
- RULE_13_KNOWLEDGE_CAPTURE_ON_RESOLUTION: When blocked issues are solved, document preferred resolution to avoid repeated troubleshooting loops.
- RULE_14_BEST_PRACTICES_ALWAYS: Always apply platform and engineering best practices.
- RULE_15_SECRETS_IN_KEY_VAULT: All secrets (API keys, tokens, passwords, connection strings) MUST be stored in and retrieved from Azure Key Vault at runtime. Secrets must never be hardcoded, committed to git, or stored outside Key Vault.
- RULE_16_JIRA_CONFLUENCE_SHARED_AUTH: Jira and Confluence share one email + API key pair for authentication. Use the same credentials for both; never duplicate or maintain separate credentials.
- RULE_17_BITBUCKET_SEPARATE_AUTH: Bitbucket uses its own dedicated credentials (username + app password). These are distinct from Jira/Confluence auth and must never be mixed or reused.

## Enforcement Commands

- `.github/guardrails/check_agent_guardrails.sh`
- `.github/guardrails/check_no_legacy_agent_core.sh`

Both must pass before deployment.

## Knowledge Base

- `.github/guardrails/AGENT_KNOWLEDGE_BASE.md`

Every resolved blocker must be added with:
- Date
- Symptom
- Root cause
- Preferred fix path
- Anti-patterns to avoid
- Verification command/output
