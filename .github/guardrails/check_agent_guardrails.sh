#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RUNTIME_DIR="$ROOT_DIR/DevSecOpsAiTeam/functions/review-endpoint"
PROMPTS_FILE="$RUNTIME_DIR/agent_prompts.py"

if [[ ! -d "$RUNTIME_DIR" ]]; then
  echo "Runtime directory missing: $RUNTIME_DIR"
  exit 2
fi

if [[ ! -f "$PROMPTS_FILE" ]]; then
  echo "Prompts file missing: $PROMPTS_FILE"
  exit 2
fi

EXIT_CODE=0

echo "Guardrail check: required coordinator rule tags"
REQUIRED_RULE_TAGS=(
  "RULE_1_AGENT_ORCHESTRATOR"
  "RULE_2_AGENT_CLARIFICATION"
  "RULE_3_TOOLS_ONLY"
  "RULE_4_JIRA_TRACKING"
  "RULE_5_CONFLUENCE_DOCS"
  "RULE_6_BITBUCKET_CODE_PIPELINE"
  "RULE_7_INFRA_DECIDED_BY_RESPONSIBLE_AGENT"
  "RULE_8_HUMAN_CLARIFICATION_ON_UNCLEAR"
  "RULE_9_NO_FALLBACK_NO_LEGACY"
  "RULE_10_NO_OUTDATED_ARTIFACTS"
  "RULE_11_AZURE_RESOURCE_HYGIENE"
  "RULE_12_COST_EFFICIENCY_FIRST"
  "RULE_13_KNOWLEDGE_CAPTURE_ON_RESOLUTION"
  "RULE_14_BEST_PRACTICES_ALWAYS"
  "RULE_15_SECRETS_IN_KEY_VAULT"
  "RULE_16_JIRA_CONFLUENCE_SHARED_AUTH"
  "RULE_17_BITBUCKET_SEPARATE_AUTH"
)

for tag in "${REQUIRED_RULE_TAGS[@]}"; do
  if ! grep -q "$tag" "$PROMPTS_FILE"; then
    echo "❌ Missing required rule tag in coordinator prompt: $tag"
    EXIT_CODE=1
  fi
done

echo "Guardrail check: forbidden legacy/fallback/static patterns"
FORBIDDEN_PATTERNS=(
  "use_fallback"
  "fallback_response"
  "graceful fallback"
  "legacy_project_endpoint"
  "AZURE_FOUNDRY_PROJECT_ENDPOINT"
  "AZURE_FOUNDRY_ENDPOINT"
  "_determine_agent_sequence"
  "_verify_all_gates"
  "hardcoded sequence"
  "JIRA_API_TOKEN\s*=\s*['\"][^$<]"
  "JIRA_EMAIL\s*=\s*['\"][a-zA-Z]"
  "BITBUCKET_APP_PASSWORD\s*=\s*['\"][^$<]"
  "@gmail\.com"
  "@hotmail\.com"
  "@outlook\.com"
)

for pattern in "${FORBIDDEN_PATTERNS[@]}"; do
  if grep -RIEn --exclude-dir="__pycache__" --exclude="*.pyc" "$pattern" "$RUNTIME_DIR" >/tmp/guardrail_hits.txt 2>/dev/null; then
    if [[ -s /tmp/guardrail_hits.txt ]]; then
      echo "❌ Forbidden pattern found: $pattern"
      cat /tmp/guardrail_hits.txt
      EXIT_CODE=1
    fi
  fi
done

echo "Guardrail check: coordinator-only orchestrator usage"
if ! grep -q 'agent_role="coordinator"' "$RUNTIME_DIR/coordinator_agent.py"; then
  echo "❌ coordinator_agent.py does not invoke coordinator role explicitly"
  EXIT_CODE=1
fi

if [[ $EXIT_CODE -eq 0 ]]; then
  echo "✅ All agent-core guardrails passed."
fi

exit $EXIT_CODE
