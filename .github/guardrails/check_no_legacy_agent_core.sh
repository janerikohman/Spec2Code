#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TARGET_DIR="$ROOT_DIR/DevSecOpsAiTeam/functions/review-endpoint"
TEAM_DIR="$ROOT_DIR/DevSecOpsAiTeam"

if [[ ! -d "$TARGET_DIR" ]]; then
  echo "Target directory not found: $TARGET_DIR"
  exit 2
fi

if [[ ! -d "$TEAM_DIR" ]]; then
  echo "Team directory not found: $TEAM_DIR"
  exit 2
fi

PATTERNS=(
  "use_fallback"
  "fallback_response"
  "graceful fallback"
  "legacy_project_endpoint"
  "AZURE_FOUNDRY_PROJECT_ENDPOINT"
  "AZURE_FOUNDRY_ENDPOINT"
  "_determine_agent_sequence"
  "_verify_all_gates"
  "hardcoded sequence"
  "static gate"
)

EXIT_CODE=0

echo "Checking for forbidden fallback/legacy/static markers in: $TARGET_DIR"
for pattern in "${PATTERNS[@]}"; do
  if grep -RIn --exclude-dir="__pycache__" --exclude="*.pyc" "$pattern" "$TARGET_DIR" >/tmp/legacy_hits.txt 2>/dev/null; then
    if [[ -s /tmp/legacy_hits.txt ]]; then
      echo "\n❌ Forbidden pattern found: $pattern"
      cat /tmp/legacy_hits.txt
      EXIT_CODE=1
    fi
  fi
done

if [[ $EXIT_CODE -eq 0 ]]; then
  echo "✅ No forbidden fallback/legacy/static markers found."
fi

echo "Checking for outdated file names in: $TEAM_DIR"
if find "$TEAM_DIR" \
  -path '*/.venv/*' -prune -o \
  -path '*/__pycache__/*' -prune -o \
  -type f \
  \( -name '*legacy*' -o -name '*deprecated*' -o -name '*old*' -o -name '*draft*' -o -name '*.v1.*' \) \
  -print >/tmp/legacy_name_hits.txt; then
  if [[ -s /tmp/legacy_name_hits.txt ]]; then
    echo "\n❌ Outdated file naming detected:"
    cat /tmp/legacy_name_hits.txt
    EXIT_CODE=1
  fi
fi

echo "Checking for stale references to outdated artifacts in: $TEAM_DIR"
if grep -RIn --exclude-dir=".venv" --exclude-dir="__pycache__" --exclude="*.pyc" \
  -E 'epic-state-machine\.v1\.json|evidence-requirements\.v1\.md|checklist\.v1\.json|SHOPPING_LIST_EPIC_DRAFT\.md|create_and_run_epic_from_draft\.py' \
  "$TEAM_DIR" >/tmp/legacy_reference_hits.txt 2>/dev/null; then
  if [[ -s /tmp/legacy_reference_hits.txt ]]; then
    echo "\n❌ Stale references to removed legacy artifacts detected:"
    cat /tmp/legacy_reference_hits.txt
    EXIT_CODE=1
  fi
fi

exit $EXIT_CODE
