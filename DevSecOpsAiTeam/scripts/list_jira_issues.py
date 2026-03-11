#!/usr/bin/env python3
import json, subprocess, base64
import requests

def kv_secret(vault, name):
    r = subprocess.run(["az","keyvault","secret","show","--vault-name",vault,"--name",name,"--query","value","-o","tsv"],capture_output=True,text=True,check=True)
    return r.stdout.strip()

cfg = {}
with open(".env") as f:
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()

jira_base = cfg["JIRA_BASE_URL"]
kv_name = cfg["AZURE_KEY_VAULT_NAME"]
email = kv_secret(kv_name, cfg["JIRA_EMAIL_SECRET_NAME"])
token = kv_secret(kv_name, cfg["JIRA_API_TOKEN_SECRET_NAME"])
auth = (email, token)

r = requests.get(f"{jira_base}/rest/api/3/issue/search", auth=auth, params={"jql":"project=KAN ORDER BY created DESC","maxResults":5,"fields":"summary,issuetype,status"})
print(f"HTTP {r.status_code}")
if r.ok:
    data = r.json()
    print(f"Total: {data.get('total',0)}")
    for iss in data.get("issues",[]):
        print(f"  {iss['key']}: [{iss['fields']['issuetype']['name']}] {iss['fields']['summary'][:70]}")
else:
    print(r.text[:500])
