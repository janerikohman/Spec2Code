# Epic Scheduler Function

Automated Azure Function that runs every 5 minutes to:
1. Query Jira for pending epics in "Ready for Orchestration" state
2. Check for recent orchestration triggers (avoid duplicates)
3. Trigger orchestration via the review-endpoint function

## Architecture

```
┌─────────────────────────┐
│  Azure Timer Trigger    │ Every 5 minutes
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│   Epic Scheduler Fn     │
├─────────────────────────┤
│ 1. Query Jira (JQL)     │
│ 2. Dedup recent runs    │
│ 3. Trigger orchestrate  │
│ 4. Post comment (mark)  │
└────────────┬────────────┘
             │
             ▼
┌─────────────────────────┐
│  Review Endpoint Fn     │
├─────────────────────────┤
│ Orchestrate Epic:       │
│ - Invoke 9 agents       │
│ - Manage state          │
│ - Create stories        │
└─────────────────────────┘
             │
             ▼
┌─────────────────────────┐
│  Jira Epic & Comments   │
│  Confluence Design Docs │
│  Bitbucket Pipelines    │
└─────────────────────────┘
```

## Configuration

Set these environment variables in Azure Function App settings:

### Required
- `JIRA_BASE_URL` - Jira Cloud instance URL (e.g., `https://org.atlassian.net`)
- `JIRA_EMAIL` - Email for Jira API auth
- `JIRA_API_TOKEN` - Jira API token (store in Key Vault)
- `REVIEW_ENDPOINT_BASE_URL` - URL of review-endpoint function (e.g., `https://func-app.azurewebsites.net/api`)
- `REVIEW_ENDPOINT_API_KEY` - API key for review-endpoint (store in Key Vault)

### Optional
- `JIRA_PROJECT_KEY` - Jira project key (default: `KAN`)

## Local Development

### Prerequisites
- Python 3.11+
- Azure Functions Core Tools (`func` CLI)
- Virtual environment: `python3 -m venv venv && source venv/bin/activate`

### Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Create local settings file
cp local.settings.example.json local.settings.json
# Edit local.settings.json with your values
```

### Run Locally
```bash
# Start the function runtime
func start

# Test manually
curl -X POST http://localhost:7071/admin/functions/epic_scheduler \
  -H "Content-Type: application/json"
```

### Testing
```bash
# Install test dependencies
pip install pytest pytest-mock

# Run tests
pytest test_function_app.py -v
```

## Deployment to Azure

### Prerequisites
- Azure CLI (`az`) authenticated: `az account show`
- Function App created in Azure
- Secrets stored in Key Vault

### Deploy with Script
```bash
# From repository root
./scripts/deploy-epic-scheduler.sh

# Env vars automatically read from .env file
# Function app name can be specified via EPIC_SCHEDULER_FUNCTION_APP_NAME
```

### Manual Deployment
```bash
# Build zip package
(cd functions/epic-scheduler && zip -r ../../epic-scheduler.zip .)

# Deploy to Azure Function App
az functionapp deployment source config-zip \
  --name <function-app-name> \
  --resource-group <resource-group> \
  --src epic-scheduler.zip

# Configure app settings
az functionapp config appsettings set \
  --name <function-app-name> \
  --resource-group <resource-group> \
  --settings \
    JIRA_BASE_URL="https://org.atlassian.net" \
    JIRA_EMAIL="bot@example.com" \
    JIRA_API_TOKEN="@Microsoft.KeyVault(SecretUri=...)" \
    REVIEW_ENDPOINT_BASE_URL="https://func-app.azurewebsites.net/api" \
    REVIEW_ENDPOINT_API_KEY="@Microsoft.KeyVault(SecretUri=...)"
```

## Monitoring

### View Logs
```bash
# Stream live logs
az functionapp log tail \
  --name <function-app-name> \
  --resource-group <resource-group>

# Show recent logs
az functionapp log show \
  --name <function-app-name> \
  --resource-group <resource-group> \
  --max-lines 50
```

### Application Insights
The function reports metrics to Application Insights:
- Execution time per cycle
- Success/error counts
- Epics discovered and triggered
- API call durations

Query example:
```kusto
traces
| where cloud_RoleName == "epic-scheduler"
| where severityLevel >= 2
| summarize count() by tostring(customDimensions.epic_key)
```

### Alerts
Recommended alert conditions:
1. Failed executions: `exceptions.count() > 5 in 1 hour`
2. Slow cycles: `customMetrics."FunctionExecutionTime" > 30s`
3. API failures: `traces | where message contains "Failed to trigger" | count() > 3`

## Operational Behavior

### Query JQL
```
project = KAN AND type = Epic AND status IN ("New", "Ready for Orchestration", "READY_FOR_ORCHESTRATION")
```

### Deduplication
Checks for recent orchestration comments within past N hours (default: 1 hour). Prevents re-orchestrating the same epic too frequently.

Comment pattern: `[AUTOMATED] Orchestration triggered by epic-scheduler at ...`

### Failure Handling
- **Jira connection failure**: Entire cycle aborts with logging
- **Individual epic error**: Logs error, continues processing other epics
- **API timeout**: Retries not implemented (timer will trigger again in 5 min)
- **Missing configuration**: Fails with clear error messages

### Performance
- Typical cycle: 10-20 seconds for 5-10 epics
- Timeout: 5 minutes (Azure Function timeout)
- Timeout handling: Retry automatically on next 5-minute tick

## Troubleshooting

### "JIRA_EMAIL and JIRA_API_TOKEN must be configured"
- Verify app settings in Azure Function App
- Check Key Vault secret URIs are correct
- Use `az functionapp config appsettings show` to verify

### "Failed to trigger orchestration: Status 401"
- Check REVIEW_ENDPOINT_API_KEY is correct
- Verify review-endpoint function is running
- Check REVIEW_ENDPOINT_BASE_URL is accessible

### "Found 0 pending epics"
- Check Jira JQL returns results: `project = KAN AND type = Epic`
- Verify epic status matches READY_STATES
- Check Jira credentials have read permission

### "Orchestration triggered but no agents running"
- Verify review-endpoint is deployed and functional
- Check Azure AI Foundry agents are registered
- Review review-endpoint logs for agent invocation errors

## API Contract

The scheduler sends a POST to Review Endpoint:
```json
{
  "epic_key": "KAN-133",
  "triggered_by": "epic-scheduler",
  "timestamp": "2024-01-15T10:30:00.000000Z"
}
```

Review Endpoint should respond with:
- `200/202` - Orchestration started
- `400` - Invalid epic key
- `401` - API key invalid
- `500` - Server error

## Related Documentation
- [Review Endpoint Function](../review-endpoint/README.md)
- [Architecture](/docs/architecture.md)
- [Orchestration Model](../epic-scheduler-deployment-guide.md)
