#!/usr/bin/env bash
set -euo pipefail

CHECKLIST_FILE="shared/dor/checklist.v1.json"
TEMPLATE_FILE="shared/templates/jira-missing-info-comment.md"

if ! command -v jq >/dev/null 2>&1; then
  echo "jq is required for this test."
  exit 1
fi

[[ -f "$CHECKLIST_FILE" ]] || { echo "Missing $CHECKLIST_FILE"; exit 1; }
[[ -f "$TEMPLATE_FILE" ]] || { echo "Missing $TEMPLATE_FILE"; exit 1; }

echo "Validating checklist schema shape..."
jq -e '.version and .required_items and (.required_items | type == "array")' "$CHECKLIST_FILE" >/dev/null

echo "Validating required checklist IDs..."
for id in business_goal personas scope acceptance_criteria dependencies nfrs success_metrics rollout_plan; do
  jq -e --arg id "$id" '.required_items[] | select(.id == $id)' "$CHECKLIST_FILE" >/dev/null || {
    echo "Missing required checklist ID: $id"
    exit 1
  }
done

echo "Validating missing-info template placeholders..."
grep -q "{{missing_item_1}}" "$TEMPLATE_FILE"
grep -q "{{missing_item_2}}" "$TEMPLATE_FILE"
grep -q "{{missing_item_3}}" "$TEMPLATE_FILE"

echo "DoR assets look valid."
