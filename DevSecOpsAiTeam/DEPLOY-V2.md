# 🚀 Azure Simple Cleanup & Deploy

**Approach**: Delete old → Deploy fresh v2.0  
**Downtime**: Acceptable  
**Keep**: Key Vault only  

---

## 📋 Delete These (v1.0 Artifacts)

### 1. Function App Code (Delete & Redeploy)
```bash
# Get current function app name
FUNC_NAME=<your-function-app-name>
RG=<your-resource-group>

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
| **Key Vault** | `<your-key-vault-name>` | Has all secrets |
| **Function App** | `<your-function-app-name>` | Just redeploy code |
| **App Service Plan** | `SwedenCentralLinuxDynamicPlan` | Reuse, same spec |
| **Storage Account** | `st<your-function-app-name>` | Reuse |
| **App Insights** | `<your-function-app-name>` | Reuse |

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
FUNC_NAME=<your-function-app-name>
RG=<your-resource-group>

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
    JIRA_BASE_URL="https://your-jira-instance.atlassian.net" \
    JIRA_API_TOKEN="@Microsoft.KeyVault(SecretUri=https://<your-key-vault-name>.vault.azure.net/secrets/jira-api-token/)" \
    CONFLUENCE_BASE_URL="https://your-jira-instance.atlassian.net/wiki" \
    CONFLUENCE_API_TOKEN="@Microsoft.KeyVault(SecretUri=https://<your-key-vault-name>.vault.azure.net/secrets/atlassian-admin-api-token/)" \
    FOUNDRY_PROJECT_ID="your-foundry-project-id" \
    ORCHESTRATION_MODE="agentic-v2" \
    LOGLEVEL="INFO"
```

### Step 4: Test Health
```bash
# Get function key
FUNC_KEY=$(az functionapp keys list \
  --name $FUNC_NAME \
  --resource-group $RG \
  --query 'functionKeys[0].value' -o tsv)

# Test endpoint
curl -X GET "https://$FUNC_NAME.azurewebsites.net/api/health" \
  -H "x-functions-key: $FUNC_KEY"

# Expected response:
# {"status": "healthy", "version": "2.0-agentic", ...}
```

---

## 📝 Complete Deployment Script

Save as `deploy-v2.sh`:

```bash
#!/bin/bash
set -e

FUNC_NAME="<your-function-app-name>"
RG="<your-resource-group>"
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

- [ ] v2.0 code ready locally
- [ ] `.env.agentic` configured with Foundry project ID
- [ ] Key Vault secrets verified (Jira, Confluence tokens)
- [ ] AI Foundry agents created (manual check)
- [ ] Run deploy script (2 minute deployment)
- [ ] Test health endpoint returns "healthy"
- [ ] Create 3 test epics in Jira
- [ ] Run orchestration tests
- [ ] Get approval

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

**Status**: Ready to deploy  
**Next**: Execute deploy script above
