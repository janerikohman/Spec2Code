import os, requests, base64
env = {}
with open(os.path.join(os.path.dirname(__file__), '..', '.env')) as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip()

from azure.keyvault.secrets import SecretClient
from azure.identity import DefaultAzureCredential
kv_name = env.get('AZURE_KEY_VAULT_NAME', 'kv-epic-po-2787129')
client = SecretClient(vault_url=f'https://{kv_name}.vault.azure.net', credential=DefaultAzureCredential())
token = client.get_secret('bitbucket-api-token').value
email = env.get('BITBUCKET_EMAIL', 'shaho.sa@gmail.com')
ws = env.get('BITBUCKET_WORKSPACE', 'shahosa')

creds = base64.b64encode(f'{email}:{token}'.encode()).decode()
resp = requests.get(
    f'https://api.bitbucket.org/2.0/repositories/{ws}',
    headers={'Authorization': f'Basic {creds}'},
    timeout=10,
)
print(f'status={resp.status_code}')
if resp.status_code == 200:
    print('token=VALID')
else:
    print(f'error={resp.text[:200]}')
