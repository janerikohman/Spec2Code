#!/usr/bin/env python3
"""Debug: Check why jira_create_dispatch_story failed."""
import json
import warnings
warnings.filterwarnings("ignore")

from azure.identity import DefaultAzureCredential
from azure.ai.agents import AgentsClient

cfg = {}
with open(".env") as f:
    for line in f:
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()

endpoint = cfg["AI_FOUNDRY_PROJECT_ENDPOINT"]
agent_map = json.loads(cfg["AI_FOUNDRY_ROLE_AGENT_MAP_JSON"])
coordinator_id = agent_map["coordinator"]

c = AgentsClient(endpoint=endpoint, credential=DefaultAzureCredential())
t = c.threads.create()
c.messages.create(
    thread_id=t.id,
    role="user",
    content="""Call jira_create_dispatch_story with:
- project_key: "KAN"
- epic_key: "KAN-148"
- role: "developer"
- task: "Implement shopping list persistence"
- stage: "implementation"

Return the full JSON result.""",
)
r = c.runs.create_and_process(thread_id=t.id, agent_id=coordinator_id)
print(f"Status: {r.status}")
print(f"Error: {getattr(r, 'last_error', 'None')}")

# Get messages to see what happened
msgs = list(c.messages.list(thread_id=t.id))
for m in msgs:
    if m.role == "assistant":
        for block in m.content:
            val = ""
            if hasattr(block, "text"):
                txt = block.text
                val = txt.get("value","") if isinstance(txt, dict) else getattr(txt,"value","")
            if val:
                print(f"\nAssistant:\n{val}")
        break
