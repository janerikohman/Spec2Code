#!/usr/bin/env python3
"""Debug one failing agent to see the full error."""
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

# Test PO agent (failing)
role = "po-requirements"
agent_id = agent_map[role]

c = AgentsClient(endpoint=endpoint, credential=DefaultAzureCredential())
t = c.threads.create()
c.messages.create(
    thread_id=t.id,
    role="user",
    content="For epic KAN-148, validate these requirements. Are they sufficient?"
)
r = c.runs.create_and_process(thread_id=t.id, agent_id=agent_id)

print(f"Agent: {role}")
print(f"Status: {r.status}")
error = getattr(r, "last_error", None)
if error:
    print(f"Last Error: {error}")
    if hasattr(error, '__dict__'):
        print(f"  Details: {error.__dict__}")
else:
    print("No error")

# Try to get messages
try:
    msgs = list(c.messages.list(thread_id=t.id))
    for m in msgs:
        print(f"\nMessage (role={m.role}):")
        for block in m.content:
            if hasattr(block, "text"):
                txt = block.text
                val = txt.get("value","") if isinstance(txt, dict) else getattr(txt,"value","")
                print(f"  {val[:300]}")
except Exception as e:
    print(f"Could not get messages: {e}")
