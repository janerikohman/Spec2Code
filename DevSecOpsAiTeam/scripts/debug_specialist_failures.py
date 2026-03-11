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
agent_map = json.loads(cfg["AI_FOUNDRY_ROLE_AGENT_MAP_JSON"])

cases = [
    (
        "security-architect",
        "Using jira_get_issue_context with issue_key KAN-148, review the epic for security implications. What are the key security concerns?",
    ),
    (
        "developer",
        "Using jira_get_issue_context with issue_key KAN-148, review the epic and design the implementation. What are the main components?",
    ),
    (
        "tester-qa",
        "Using jira_get_issue_context with issue_key KAN-148, review the epic and create a test plan. What test scenarios are critical?",
    ),
]

for role, prompt in cases:
    print("\n" + "=" * 32)
    print(role)
    print("=" * 32)
    client = AgentsClient(endpoint=endpoint, credential=DefaultAzureCredential())
    thread = client.threads.create()
    client.messages.create(thread_id=thread.id, role="user", content=prompt)
    run = client.runs.create_and_process(thread_id=thread.id, agent_id=agent_map[role])
    print("status:", run.status)
    print("last_error:", getattr(run, "last_error", None))
    print("required_action:", getattr(run, "required_action", None))
    print("incomplete_details:", getattr(run, "incomplete_details", None))
    print("usage:", getattr(run, "usage", None))
    print("run_id:", getattr(run, "id", None))

    messages = list(client.messages.list(thread_id=thread.id))
    for message in messages[:6]:
        print(f"message role: {message.role}")
        for block in message.content:
            text = getattr(block, "text", None)
            if text is not None:
                value = text.get("value", "") if isinstance(text, dict) else getattr(text, "value", "")
                print(value[:1500])
                print("-" * 60)
