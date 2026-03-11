# KAN-148 PR Checklist

Repository: https://bitbucket.org/shahosa/kan148-shopping-list-app
Branch: `epic/kan-148-delivery-pack`

## Scope in this bootstrap PR
- Bitbucket pipeline scaffold
- Containerization scaffold
- Azure Bicep baseline
- Local smoke test helper

## Merge checklist
- [ ] Set Bitbucket repository variables/secrets
- [ ] Confirm PR pipeline succeeds
- [ ] Validate app build command matches pipeline expectations
- [ ] Validate deployment script parameters/environment names
- [ ] Merge PR to destination branch

## Required variables
- `AZURE_CLIENT_ID`
- `AZURE_CLIENT_SECRET`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_RESOURCE_GROUP`
- `AZURE_LOCATION`
- `AZURE_WEBAPP_NAME`
- `AZURE_PLAN_NAME`
- `AZURE_PLAN_SKU` (optional)
