#!/usr/bin/env python3
import json, subprocess, urllib.request, base64

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
creds = base64.b64encode(f"{email}:{token}".encode()).decode()

req = urllib.request.Request(f"{jira_base}/rest/api/3/project/search",headers={"Authorization":f"Basic {creds}","Accept":"application/json"})
with urllib.request.urlopen(req) as r:
    data = json.loads(r.read())

for p in data.get("values",[]):
    print(f"  {p['key']}: {p['name']}")
