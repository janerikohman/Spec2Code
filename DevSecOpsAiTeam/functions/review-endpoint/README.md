# Review Endpoint (Low Cost)

This Azure Function evaluates one Jira Epic for Definition of Ready and returns a structured result for Logic Apps.

## Why this is low cost

- Single HTTP-triggered function.
- Consumption plan (pay per execution).
- No database, no queue, no premium dependencies.
- Minimal Python dependencies (`azure-functions` only).

## Endpoint

- Route: `/api/review_epic`
- Method: `POST`
- Auth: Function key

Input:

```json
{
  "epic": { "fields": { "summary": "...", "description": {} } },
  "comments": [],
  "dor_checklist_version": "1.0.0"
}
```

Output:

```json
{
  "readiness": "ready|needs_info",
  "question_hash": "stable-hash",
  "comment_body": "text",
  "add_labels": ["needs-info"],
  "remove_labels": ["ready-for-delivery"]
}
```

## Strict Field Mapping (Recommended)

The function supports a configurable app setting:

- `DOR_FIELD_MAP_JSON`

Use it to map readiness items to Jira fields/custom fields. Selectors supported:

- `field:<jira_field_name_or_customfield_id>` (for example `field:customfield_10050`)
- `description_section:<section_name>` (for example `description_section:scope`)

Example:

```json
{
  "business_goal": ["field:customfield_10050"],
  "personas": ["field:customfield_10051"],
  "scope": ["description_section:scope"],
  "acceptance_criteria": ["field:customfield_10052"],
  "dependencies": ["field:customfield_10053"],
  "nfrs": ["field:customfield_10054"],
  "success_metrics": ["field:customfield_10055"],
  "rollout_plan": ["field:customfield_10056"]
}
```

If a map is not provided, the function checks structured sections in description (for example `Scope:` or `Acceptance Criteria:`), not generic keyword matching.

## Template Hint Mode

Optional app setting:

- `ENABLE_TEMPLATE_HINT=true|false` (default `true`)

When enabled, if an Epic is clearly under-structured and missing readiness data, the function can suggest posting a one-time template hint. The workflow uses label `dor-template-shared` to avoid repeating it.

## Deploy

Use:

```bash
bash scripts/deploy-review-function.sh
```

The script updates `.env` with:

- `REVIEW_ENDPOINT_URL`
- `REVIEW_ENDPOINT_API_KEY`
