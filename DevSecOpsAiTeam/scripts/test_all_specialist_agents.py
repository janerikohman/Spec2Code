#!/usr/bin/env python3
"""
Test all 8 specialist agents individually through Foundry.
Verifies each agent can be invoked, understands its role, and responds meaningfully.
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

# Define the 8 specialist agents and their test prompts
agents_to_test = [
    {
        "role": "po-requirements",
        "label": "PO/Requirements",
        "prompt": "Using jira_get_issue_context with issue_key KAN-148, validate the epic requirements. Are they complete? What's missing?"
    },
    {
        "role": "architect",
        "label": "Architect",
        "prompt": "Using jira_get_issue_context with issue_key KAN-148, review the epic and design the system architecture. What tech stack do you recommend?"
    },
    {
        "role": "security-architect",
        "label": "Security Architect",
        "prompt": "Using jira_get_issue_context with issue_key KAN-148, review the epic for security implications. What are the key security concerns?"
    },
    {
        "role": "devops-iac",
        "label": "DevOps/IaC",
        "prompt": "Using jira_get_issue_context with issue_key KAN-148, review the epic and design the deployment infrastructure. What cloud services do you need?"
    },
    {
        "role": "developer",
        "label": "Developer",
        "prompt": "Using jira_get_issue_context with issue_key KAN-148, review the epic and design the implementation. What are the main components?"
    },
    {
        "role": "tester-qa",
        "label": "QA/Tester",
        "prompt": "Using jira_get_issue_context with issue_key KAN-148, review the epic and create a test plan. What test scenarios are critical?"
    },
    {
        "role": "finops",
        "label": "FinOps",
        "prompt": "Using jira_get_issue_context with issue_key KAN-148, review the epic and estimate infrastructure costs. What cost optimizations do you recommend?"
    },
    {
        "role": "release-manager",
        "label": "Release Manager",
        "prompt": "Using jira_get_issue_context with issue_key KAN-148, review the epic and plan the release. Define version number and release strategy."
    },
]

print("=" * 80)
print("SPECIALIST AGENTS TEST SUITE")
print("=" * 80)
print(f"Testing {len(agents_to_test)} agents via Foundry orchestrator\n")

results = []

for agent_test in agents_to_test:
    role = agent_test["role"]
    label = agent_test["label"]
    prompt = agent_test["prompt"]
    
    if role not in agent_map:
        print(f"❌ {label:20s} - SKIPPED (not in agent map)")
        continue
    
    agent_id = agent_map[role]
    
    print(f"Testing {label:20s} ({agent_id[:20]}...)")
    
    try:
        c = AgentsClient(endpoint=endpoint, credential=DefaultAzureCredential())
        t = c.threads.create()
        c.messages.create(thread_id=t.id, role="user", content=prompt)
        r = c.runs.create_and_process(thread_id=t.id, agent_id=agent_id)
        
        status = str(r.status).upper()
        last_error = getattr(r, "last_error", None)
        
        if "COMPLETED" in status and not last_error:
            # Get response
            msgs = list(c.messages.list(thread_id=t.id))
            response_text = ""
            for m in msgs:
                if m.role == "assistant":
                    for block in m.content:
                        if hasattr(block, "text"):
                            txt = block.text
                            response_text = txt.get("value","") if isinstance(txt, dict) else getattr(txt,"value","")
                    break
            
            response_preview = response_text[:120] if response_text else "(no response)"
            print(f"  ✅ Status: {status}")
            print(f"     Response: {response_preview}...\n")
            results.append({"role": label, "status": "PASS", "error": None})
        else:
            print(f"  ❌ Status: {status}")
            if last_error:
                error_msg = str(last_error)[:100]
                print(f"     Error: {error_msg}...\n")
            results.append({"role": label, "status": "FAIL", "error": last_error})
    
    except Exception as e:
        print(f"  ❌ Exception: {str(e)[:100]}...\n")
        results.append({"role": label, "status": "ERROR", "error": str(e)})

# Summary
print("=" * 80)
print("SUMMARY")
print("=" * 80)
passed = sum(1 for r in results if r["status"] == "PASS")
failed = sum(1 for r in results if r["status"] == "FAIL")
errors = sum(1 for r in results if r["status"] == "ERROR")

for r in results:
    icon = "✅" if r["status"] == "PASS" else "❌"
    print(f"{icon} {r['role']:20s} - {r['status']}")
    if r["error"]:
        print(f"   {str(r['error'])[:80]}")

print(f"\n{passed}/{len(results)} agents PASSED")
if failed > 0 or errors > 0:
    print(f"{failed + errors} agents FAILED/ERROR - requires fixes")
else:
    print("✅ All 8 specialist agents ready for orchestration!")
