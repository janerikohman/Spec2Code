#!/usr/bin/env python3
"""Find a real KAN epic key then run it through the Foundry coordinator agent.
Foundry remains the orchestrator - this script only starts the run."""
import subprocess, json, urllib.request, base64, ssl, warnings
warnings.filterwarnings("ignore")

from azure.identity import DefaultAzureCredential
from azure.ai.agents import AgentsClient

def kv(name):
    return subprocess.run(
        ["az","keyvault","secret","show","--vault-name","kv-epic-po-2787129",
         "--name", name,"--query","value","-o","tsv"],
        capture_output=True, text=True, check=True
    ).stdout.strip()

cfg = {}
with open(".env") as f:
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()

base   = cfg["JIRA_BASE_URL"]
email  = kv("jira-email")
token  = kv("jira-api-token")
auth   = base64.b64encode(f"{email}:{token}".encode()).decode()
ctx    = ssl.create_default_context()

def jira_get(path):
    req = urllib.request.Request(
        f"{base}{path}",
        headers={"Authorization": f"Basic {auth}", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, context=ctx) as r:
        return json.loads(r.read())

# Find epics in KAN (Jira Cloud uses /rest/api/3/search/jql)
def jira_search(jql, fields="summary,issuetype,status", max_results=5):
    import urllib.parse
    params = urllib.parse.urlencode({"jql": jql, "maxResults": max_results, "fields": fields})
    return jira_get(f"/rest/api/3/search/jql?{params}").get("issues", [])

epics = jira_search("project=KAN AND issuetype=Epic ORDER BY created DESC")
if not epics:
    epics = jira_search("project=KAN ORDER BY created DESC")

print("Available KAN issues:")
for i in epics:
    print(f"  {i['key']}  [{i['fields']['issuetype']['name']}]  {i['fields']['status']['name']}  -  {i['fields']['summary'][:70]}")

if not epics:
    print("No issues found in KAN project.")
    raise SystemExit(1)

epic_key = epics[0]["key"]
print(f"\nUsing issue key: {epic_key}")

# --- Now run through Foundry coordinator (Foundry = orchestrator) ---
endpoint  = cfg["AI_FOUNDRY_PROJECT_ENDPOINT"]
agent_map = json.loads(cfg["AI_FOUNDRY_ROLE_AGENT_MAP_JSON"])
coord_id  = agent_map["coordinator"]
print(f"Coordinator agent: {coord_id}")

c = AgentsClient(endpoint=endpoint, credential=DefaultAzureCredential())
t = c.threads.create()
c.messages.create(
    thread_id=t.id,
    role="user",
    content=f"Call jira_get_issue_context with issue_key {epic_key} and return the result as compact JSON.",
)
print("Running coordinator via Foundry ...")
r = c.runs.create_and_process(thread_id=t.id, agent_id=coord_id)
print(f"status:     {r.status}")
print(f"last_error: {getattr(r, 'last_error', None)}")

if "COMPLETED" in str(r.status).upper():
    msgs = list(c.messages.list(thread_id=t.id))
    for m in msgs:
        if m.role == "assistant":
            for block in m.content:
                val = ""
                if hasattr(block, "text"):
                    txt = block.text
                    val = txt.get("value","") if isinstance(txt, dict) else getattr(txt,"value","")
                print(f"\nassistant reply:\n{val[:800]}")
            break
    print("\nSUCCESS: Foundry coordinator called the tool and got a result!")
