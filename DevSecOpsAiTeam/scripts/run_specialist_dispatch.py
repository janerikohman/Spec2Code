#!/usr/bin/env python3
"""
Run all specialist agents on KAN-148 and ask each to publish their artifact to Confluence.
Usage: python scripts/run_specialist_dispatch.py [--epic KAN-148]
"""
import json
import os
import sys
import time
import argparse
from datetime import datetime

# ── Load .env ───────────────────────────────────────────────────────────────
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(env_path):
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

from azure.identity import DefaultAzureCredential
from azure.ai.agents import AgentsClient

parser = argparse.ArgumentParser()
parser.add_argument("--epic", default="KAN-148")
args = parser.parse_args()
EPIC = args.epic

endpoint = os.environ["AI_FOUNDRY_PROJECT_ENDPOINT"]
agent_map = json.loads(os.environ["AI_FOUNDRY_ROLE_AGENT_MAP_JSON"])

ROLES = [
    ("po-requirements",    "po-requirements",    f"Analyse the Jira epic {EPIC} (call jira_get_issue_context). Review requirements completeness against DoR. Publish a structured requirements analysis page to Confluence (call confluence_create_page) titled '{EPIC} – Requirements Analysis'. Return a summary."),
    ("architect",          "architect",          f"Analyse the Jira epic {EPIC} (call jira_get_issue_context). Produce a high-level architecture design. Publish an architecture decision record to Confluence (call confluence_create_page) titled '{EPIC} – Architecture Design'. Return a summary."),
    ("security-architect", "security-architect", f"Analyse the Jira epic {EPIC} (call jira_get_issue_context). Produce a security threat model and risk assessment. Publish to Confluence (call confluence_create_page) titled '{EPIC} – Security Assessment'. Return a summary."),
    ("devops-iac",         "devops-iac",         f"Analyse the Jira epic {EPIC} (call jira_get_issue_context). Produce an IaC and pipeline design. Publish to Confluence (call confluence_create_page) titled '{EPIC} – DevOps & IaC Design'. Return a summary."),
    ("developer",          "developer",          f"Analyse the Jira epic {EPIC} (call jira_get_issue_context). Produce a developer implementation plan. Publish to Confluence (call confluence_create_page) titled '{EPIC} – Developer Implementation Plan'. Return a summary."),
    ("tester-qa",          "tester-qa",          f"Analyse the Jira epic {EPIC} (call jira_get_issue_context). Produce a test strategy and quality gate criteria. Publish to Confluence (call confluence_create_page) titled '{EPIC} – Test Strategy'. Return a summary."),
    ("finops",             "finops",             f"Analyse the Jira epic {EPIC} (call jira_get_issue_context). Produce a cost estimate and FinOps analysis. Publish to Confluence (call confluence_create_page) titled '{EPIC} – FinOps Cost Analysis'. Return a summary."),
    ("release-manager",    "release-manager",    f"Analyse the Jira epic {EPIC} (call jira_get_issue_context). Produce a release plan and runbook. Publish to Confluence (call confluence_create_page) titled '{EPIC} – Release Plan'. Return a summary."),
]

client = AgentsClient(endpoint=endpoint, credential=DefaultAzureCredential())

print("=" * 80)
print(f"SPECIALIST DISPATCH — {EPIC}")
print(f"Confluence space: S2C  |  {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}")
print("=" * 80)

results = []
for label, role, prompt in ROLES:
    agent_id = agent_map.get(role)
    if not agent_id:
        print(f"\n⚠️  No agent ID for role '{role}' — skipping")
        continue

    print(f"\n[{label}] → {agent_id[:20]}…")
    t0 = time.time()
    try:
        thread = client.threads.create()
        client.messages.create(thread_id=thread.id, role="user", content=prompt)
        run = client.runs.create_and_process(thread_id=thread.id, agent_id=agent_id)
        elapsed = round(time.time() - t0, 1)

        # Extract response text
        response_text = ""
        for m in client.messages.list(thread_id=thread.id):
            if m.role == "assistant":
                for block in m.content:
                    if hasattr(block, "text"):
                        txt = block.text
                        response_text = txt.get("value", "") if isinstance(txt, dict) else getattr(txt, "value", "")
                        break
                if response_text:
                    break

        status = str(run.status)
        ok = "COMPLETED" in status.upper()
        icon = "✅" if ok else "❌"
        print(f"  {icon} {status} ({elapsed}s)")
        print(f"     {response_text[:200].replace(chr(10),' ')}…")
        results.append((label, ok, status, elapsed))
    except Exception as e:
        elapsed = round(time.time() - t0, 1)
        print(f"  ❌ EXCEPTION ({elapsed}s): {e}")
        results.append((label, False, str(e), elapsed))

print("\n" + "=" * 80)
print("DISPATCH SUMMARY")
print("=" * 80)
passed = sum(1 for _, ok, _, _ in results if ok)
for label, ok, status, elapsed in results:
    icon = "✅" if ok else "❌"
    print(f"  {icon} {label:<22} {status:<20} {elapsed}s")

print(f"\n{passed}/{len(results)} agents completed")
print(f"\nConfluence space: https://shahosa.atlassian.net/wiki/spaces/S2C")
print(f"Jira epic:        https://shahosa.atlassian.net/browse/{EPIC}")
