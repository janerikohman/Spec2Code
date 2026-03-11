#!/usr/bin/env python3
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
agent_id = json.loads(cfg["AI_FOUNDRY_ROLE_AGENT_MAP_JSON"])["architect"]
prompt = "Using jira_get_issue_context with issue_key KAN-148, review the epic and design the system architecture. What tech stack do you recommend?"

client = AgentsClient(endpoint=endpoint, credential=DefaultAzureCredential())
thread = client.threads.create()
client.messages.create(thread_id=thread.id, role="user", content=prompt)
run = client.runs.create_and_process(thread_id=thread.id, agent_id=agent_id)

print("status:", run.status)
print("last_error:", getattr(run, "last_error", None))
print("required_action:", getattr(run, "required_action", None))
print("incomplete_details:", getattr(run, "incomplete_details", None))
print("run_id:", getattr(run, "id", None))
print("usage:", getattr(run, "usage", None))
print()

for message in list(client.messages.list(thread_id=thread.id))[:6]:
    print("message role:", message.role)
    for block in message.content:
        text = getattr(block, "text", None)
        if text is not None:
            value = text.get("value", "") if isinstance(text, dict) else getattr(text, "value", "")
            print(value[:3000])
            print("-" * 80)
