#!/usr/bin/env python3
"""
Test that the coordinator agent can successfully invoke a tool.
Run from DevSecOpsAiTeam/ directory.
"""
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
print(f"Coordinator agent ID: {coordinator_id}")

c = AgentsClient(endpoint=endpoint, credential=DefaultAzureCredential())
t = c.threads.create()
c.messages.create(
    thread_id=t.id,
    role="user",
    content="Call jira_get_issue_context with issue_key S2C-1 and return the result as JSON.",
)
print("Running coordinator agent...")
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
                print(f"assistant: {val[:500]}")
            break
    print("\nSUCCESS: Tool call went through Foundry coordinator!")
else:
    print("\nFAILED: Run did not complete")
