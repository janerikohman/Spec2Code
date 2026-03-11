targetScope = 'resourceGroup'

@description('Name of the web app')
param appName string

@description('Name of the app service plan')
param planName string

@description('App Service plan SKU (B1 recommended for low-cost demo)')
param skuName string = 'B1'

@description('Azure region')
param location string = resourceGroup().location

@description('Optional tags')
param tags object = {
  application: 'shopping-list-app'
  environment: 'demo'
  owner: 'ai-agents'
}

resource plan 'Microsoft.Web/serverfarms@2023-01-01' = {
  name: planName
  location: location
  kind: 'linux'
  sku: {
    name: skuName
    tier: startsWith(skuName, 'B') ? 'Basic' : 'Standard'
    size: skuName
    capacity: 1
  }
  properties: {
    reserved: true
  }
  tags: tags
}

resource webApp 'Microsoft.Web/sites@2023-01-01' = {
  name: appName
  location: location
  kind: 'app,linux'
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      linuxFxVersion: 'JAVA|21-java21'
      alwaysOn: true
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
      appSettings: [
        {
          name: 'WEBSITE_RUN_FROM_PACKAGE'
          value: '1'
        }
        {
          name: 'JAVA_OPTS'
          value: '-XX:MaxRAMPercentage=75.0'
        }
      ]
    }
  }
  tags: tags
}

output appUrl string = 'https://${webApp.properties.defaultHostName}'
