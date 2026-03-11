# Shopping List Delivery Pack

This template is intended for agent-driven execution in a target application repository.

## Contents

- `bitbucket-pipelines.yml`: build, dependency scan, infra deploy, app deploy.
- `infra/bicep/main.bicep`: Azure App Service Linux deployment baseline.
- `infra/bicep/deploy.sh`: manual infra deployment helper.
- `scripts/e2e-local.sh`: local build/run smoke test.
- `Dockerfile` and `.dockerignore`: container path option.

## Required Pipeline Variables

- `AZURE_CLIENT_ID`
- `AZURE_CLIENT_SECRET`
- `AZURE_TENANT_ID`
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_RESOURCE_GROUP`
- `AZURE_LOCATION`
- `AZURE_WEBAPP_NAME`
- `AZURE_PLAN_NAME`
- `AZURE_PLAN_SKU` (optional, default `B1`)

## Agent Execution Rules

- DevOps agent must copy these files into the target repo and open a PR.
- Developer agent must ensure app build artifact name matches pipeline deploy step.
- QA agent must run `scripts/e2e-local.sh` and attach evidence.
