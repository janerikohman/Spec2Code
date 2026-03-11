# 🚀 Azure Deploy — Spec2Code v2.0

**Approach**: Redeploy function code → re-register agents → verify  
**Downtime**: Acceptable  
**Keep**: Key Vault + Function App infra  

**Deployed resources**:
- Function App: `epicreview257529268` (tool adapter)
- Epic Scheduler: `epic-scheduler-agentic`
- Key Vault: `kv-epic-po-2787129`
- Resource Group: `AgenticDevSecOps`
- Region: `swedencentral`

---

## 📋 Delete These (v1.0 Artifacts)

### 1. Function App Code (Delete & Redeploy)
```bash
FUNC_NAME=epicreview257529268
RG=AgenticDevSecOps

# Delete current deployment
az functionapp deployment source delete \
  --name $FUNC_NAME \
  --resource-group $RG
```

### 2. Function App Slots (If Any)
```bash
# List slots
az functionapp deployment slot list \
  --name $FUNC_NAME \
  --resource-group $RG

# Delete non-production slots (optional)
# az functionapp deployment slot delete \
#   --name $FUNC_NAME \
#   --slot staging \
#   --resource-group $RG
```

### 3. Old App Settings (Clear Old Config)
```bash
# List current settings
az functionapp config appsettings list \
  --name $FUNC_NAME \
  --resource-group $RG | grep -v "WEBSITE_"

# Delete old v1.0 settings (optional, or just overwrite with v2.0)
# Not strictly necessary - v2.0 settings will override
```

---

## ✅ Keep These (Reuse for v2.0)

| Resource | Name | Reason |
|----------|------|--------|
| **Key Vault** | `kv-epic-po-2787129` | Has all secrets |
| **Function App** | `epicreview257529268` | Just redeploy code |
| **App Service Plan** | `SwedenCentralLinuxDynamicPlan` | Reuse, same spec |
| **Storage Account** | `stepicreview257529268` | Reuse |
| **App Insights** | `epicreview257529268` | Reuse |

---

## 🚀 Deploy v2.0 (Clean Fresh Start)

### Step 1: Build Package
```bash
cd functions/review-endpoint
mkdir -p dist

# Copy v2.0 files
cp function_app.py dist/
cp coordinator_agent.py dist/
cp requirements.txt dist/
cp host.json dist/

# Create zip
cd dist
zip -r ../function_app.zip . -x "*.pyc" "dist/*"
cd ..
```

### Step 2: Deploy to Azure
```bash
FUNC_NAME=epicreview257529268
RG=AgenticDevSecOps

az functionapp deployment source config-zip \
  --name $FUNC_NAME \
  --resource-group $RG \
  --src-file function_app.zip

# Wait for deployment
sleep 30

# Verify deployment
az functionapp show --name $FUNC_NAME \
  --resource-group $RG \
  --query "{Name:name, State:state}"
```

### Step 3: Configure App Settings (v2.0)
```bash
az functionapp config appsettings set \
  --name $FUNC_NAME \
  --resource-group $RG \
  --settings \
    JIRA_BASE_URL="https://shahosa.atlassian.net" \
    JIRA_EMAIL_SECRET_NAME="jira-email" \
    JIRA_API_TOKEN_SECRET_NAME="jira-api-token" \
    CONFLUENCE_BASE_URL="https://shahosa.atlassian.net" \
    CONFLUENCE_SPACE_KEY="S2C" \
    AI_FOUNDRY_PROJECT_ENDPOINT="https://agenticdevsecopsteam-resource.services.ai.azure.com/api/projects/AgenticDevSecOpsTeam" \
    AZURE_KEY_VAULT_NAME="kv-epic-po-2787129" \
    LOGLEVEL="INFO"
```

### Step 4: Test Health
```bash
# Get function key
FUNC_KEY=$(az functionapp keys list \
  --name $FUNC_NAME \
  --resource-group $RG \
  --query 'functionKeys[0].value' -o tsv)

# Test endpoint (ANONYMOUS — no key required)
curl -s https://epicreview257529268.azurewebsites.net/api/health

# Expected: {"status": "healthy", ...}
```

---

## 📝 Complete Deployment Script

Save as `deploy-v2.sh`:

```bash
#!/bin/bash
set -e

FUNC_NAME="epicreview257529268"
RG="AgenticDevSecOps"
REGION="swedencentral"

echo "════════════════════════════════════════"
echo "  Spec2Code v2.0 Azure Deployment"
echo "════════════════════════════════════════"
echo ""

# Step 1: Build
echo "1️⃣  Building deployment package..."
cd functions/review-endpoint
mkdir -p dist
cp function_app.py coordinator_agent.py requirements.txt host.json dist/
cd dist
zip -r ../function_app.zip . -x "*.pyc" "dist/*"
cd ..
echo "✅ Package built: function_app.zip"
echo ""

# Step 2: Deploy
echo "2️⃣  Deploying to Azure..."
az functionapp deployment source config-zip \
  --name $FUNC_NAME \
  --resource-group $RG \
  --src-file function_app.zip
echo "✅ Deployment complete"
echo ""

# Step 3: Configure
echo "3️⃣  Configuring environment..."
az functionapp config appsettings set \
  --name $FUNC_NAME \
  --resource-group $RG \
  --settings \
    ORCHESTRATION_MODE="agentic-v2" \
    LOGLEVEL="INFO"
echo "✅ Environment configured"
echo ""

# Step 4: Verify
echo "4️⃣  Testing deployment..."
FUNC_KEY=$(az functionapp keys list \
  --name $FUNC_NAME \
  --resource-group $RG \
  --query 'functionKeys[0].value' -o tsv)

RESPONSE=$(curl -s -X GET "https://$FUNC_NAME.azurewebsites.net/api/health" \
  -H "x-functions-key: $FUNC_KEY")

if echo "$RESPONSE" | grep -q "healthy"; then
  echo "✅ Health check passed"
  echo "✅ v2.0 is LIVE"
else
  echo "❌ Health check failed"
  echo "Response: $RESPONSE"
  exit 1
fi

echo ""
echo "════════════════════════════════════════"
echo "  🚀 DEPLOYMENT COMPLETE"
echo "════════════════════════════════════════"
```

Run it:
```bash
chmod +x deploy-v2.sh
./deploy-v2.sh
```

---

## ✅ Deployment Checklist

- [ ] `.env` configured (copy from `.env.example`)
- [ ] Key Vault secrets verified: `jira-email`, `jira-api-token`, `bitbucket-api-token`
- [ ] Run deploy script
- [ ] Health endpoint returns `{"status": "healthy"}`
- [ ] Re-register agents: `bash scripts/register-foundry-role-assistants.sh`
- [ ] Verify agents: `../.venv/bin/python scripts/test_all_specialist_agents.py` (expect 8/8)
- [ ] Run e2e test: `../.venv/bin/python scripts/test_full_orchestration.py`
- [ ] Confirm Confluence space `S2C` exists at `shahosa.atlassian.net/wiki/spaces/S2C`

---

## ⏱️ Total Time

```
Build:     2 min
Deploy:    3 min
Configure: 2 min
Test:      3 min
─────────────────
Total: ~10 minutes to live
```

Then run 3 test epics (60 min)
Then approval & go-live

---

**Status**: ✅ Deployed and production-verified (March 11, 2026)  
**Function URL**: `https://epicreview257529268.azurewebsites.net/api`
