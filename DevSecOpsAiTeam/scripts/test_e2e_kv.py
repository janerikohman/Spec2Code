#!/usr/bin/env python3
"""
Test end-to-end: Foundry coordinator agent calls the tool adapter which reads from KV.
Fetches a real Jira issue key first, then runs the coordinator agent against it.
"""
import json
import subprocess
import urllib.request
import base64
import warnings
warnings.filterwarnings("ignore")

from azure.identity import DefaultAzureCredential
from azure.ai.agents import AgentsClient

def kv_secret(vault, name):
    r = subprocess.run(
        ["az", "keyvault", "secret", "show", "--vault-name", vault, "--name", name, "--query", "value", "-o", "tsv"],
        capture_output=True, text=True, check=True
    )
    return r.stdout.strip()

# Load config
cfg = {}
with open(".env") as f:
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()

jira_base = cfg["JIRA_BASE_URL"]
project_key = cfg.get("JIRA_PROJECT_KEY", "KAN")
kv_name = cfg["AZURE_KEY_VAULT_NAME"]

print(f"Fetching Jira credentials from Key Vault {kv_name}...")
jira_email = kv_secret(kv_name, cfg["JIRA_EMAIL_SECRET_NAME"])
jira_token = kv_secret(kv_name, cfg["JIRA_API_TOKEN_SECRET_NAME"])
print(f"  email: {jira_email}")

print(f"\nFetching recent issues from project {project_key}...")
creds = base64.b64encode(f"{jira_email}:{jira_token}".encode()).decode()
req = urllib.request.Request(
    f"{jira_base}/rest/api/3/issue/search?jql=project={project_key}+ORDER+BY+created+DESC&maxResults=5&fields=summary,issuetype,status",
    headers={"Authorization": f"Basic {creds}", "Accept": "application/json"}
)
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read())

issues = data.get("issues", [])
if not issues:
    print("No issues found in project. Cannot run end-to-end test.")
    exit(1)

for iss in issues:
    print(f"  {iss['key']}: [{iss['fields']['issuetype']['name']}] {iss['fields']['summary'][:60]}")

test_key = issues[0]["key"]
print(f"\nUsing issue key: {test_key}")

# Now run through Foundry coordinator
endpoint = cfg["AI_FOUNDRY_PROJECT_ENDPOINT"]
agent_map = json.loads(cfg["AI_FOUNDRY_ROLE_AGENT_MAP_JSON"])
coordinator_id = agent_map["coordinator"]
print(f"Coordinator agent ID: {coordinator_id}")

c = AgentsClient(endpoint=endpoint, credential=DefaultAzureCredential())
t = c.threads.create()
c.messages.create(
    thread_id=t.id,
    role="user",
    content=f"Call jira_get_issue_context with issue_key {test_key} and return the result as compact JSON.",
)
print("Running through Foundry orchestrator...")
r = c.runs.create_and_process(thread_id=t.id, agent_id=coordinator_id)
print(f"status: {r.status}")
print(f"last_error: {getattr(r, 'last_error', None)}")

if "COMPLETED" in str(r.status):
    msgs = list(c.messages.list(thread_id=t.id))
    for m in msgs:
        if m.role == "assistant":
            for block in m.content:
                val = ""
                if hasattr(block, "text"):
                    val = block.text.get("value", "") if isinstance(block.text, dict) else getattr(block.text, "value", "")
                print(f"\nassistant response:\n{val[:1000]}")
            break
    print("\nSUCCESS: Foundry -> Function -> Jira (KV creds) chain is fully working!")
else:
    print("\nRun did not complete successfully.")
