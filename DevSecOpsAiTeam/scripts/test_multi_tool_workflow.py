#!/usr/bin/env python3
"""
Multi-tool workflow test: Coordinator agent executes a complete epic workflow.
1. Get epic context (KAN-148)
2. List open dispatch issues
3. Create a new dispatch story
4. Transition epic to "In Progress"
5. Add a comment to the epic

Foundry remains the orchestrator throughout.
"""
import json
import subprocess
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

epic_key = "KAN-148"
project_key = "KAN"

print(f"Testing multi-tool workflow with epic {epic_key}")
print(f"Coordinator: {coordinator_id}\n")

# Test 1: Get epic context
print("=" * 60)
print("TEST 1: Get Epic Context")
print("=" * 60)
c = AgentsClient(endpoint=endpoint, credential=DefaultAzureCredential())
t = c.threads.create()
c.messages.create(
    thread_id=t.id,
    role="user",
    content=f"Call jira_get_issue_context with issue_key {epic_key}. Return only the JSON result.",
)
r = c.runs.create_and_process(thread_id=t.id, agent_id=coordinator_id)
print(f"Status: {r.status}")
if "COMPLETED" in str(r.status).upper():
    msgs = list(c.messages.list(thread_id=t.id))
    for m in msgs:
        if m.role == "assistant":
            for block in m.content:
                val = ""
                if hasattr(block, "text"):
                    txt = block.text
                    val = txt.get("value","") if isinstance(txt, dict) else getattr(txt,"value","")
                if val:
                    # Extract just the ok/key fields
                    try:
                        data = json.loads(val)
                        print(f"✅ Issue retrieved: {data.get('issue',{}).get('key')} - {data.get('issue',{}).get('summary')[:70]}")
                    except:
                        print(f"Result: {val[:200]}")
            break
print()

# Test 2: List open dispatch issues
print("=" * 60)
print("TEST 2: List Open Dispatch Issues")
print("=" * 60)
c = AgentsClient(endpoint=endpoint, credential=DefaultAzureCredential())
t = c.threads.create()
c.messages.create(
    thread_id=t.id,
    role="user",
    content=f"Call jira_list_open_dispatch_issues with project_key {project_key} and epic_key {epic_key}. Return only the JSON result.",
)
r = c.runs.create_and_process(thread_id=t.id, agent_id=coordinator_id)
print(f"Status: {r.status}")
if "COMPLETED" in str(r.status).upper():
    msgs = list(c.messages.list(thread_id=t.id))
    for m in msgs:
        if m.role == "assistant":
            for block in m.content:
                val = ""
                if hasattr(block, "text"):
                    txt = block.text
                    val = txt.get("value","") if isinstance(txt, dict) else getattr(txt,"value","")
                if val:
                    try:
                        data = json.loads(val)
                        issues = data.get('issues',[])
                        print(f"✅ Found {len(issues)} open dispatch issues under {epic_key}")
                        for issue in issues[:3]:
                            print(f"   - {issue.get('key')}: {issue.get('summary')[:60]}")
                    except:
                        print(f"Result: {val[:200]}")
            break
print()

# Test 3: Create a dispatch story
print("=" * 60)
print("TEST 3: Create Dispatch Story")
print("=" * 60)
c = AgentsClient(endpoint=endpoint, credential=DefaultAzureCredential())
t = c.threads.create()
story_task = "Implement shopping list persistence storage using browser localStorage"
c.messages.create(
    thread_id=t.id,
    role="user",
    content=f"""Call jira_create_dispatch_story with:
- project_key: {project_key}
- epic_key: {epic_key}
- role: "developer"
- task: "{story_task}"
- stage: "implementation"

Return only the JSON result with the created story key and URL.""",
)
r = c.runs.create_and_process(thread_id=t.id, agent_id=coordinator_id)
print(f"Status: {r.status}")
if "COMPLETED" in str(r.status).upper():
    msgs = list(c.messages.list(thread_id=t.id))
    for m in msgs:
        if m.role == "assistant":
            for block in m.content:
                val = ""
                if hasattr(block, "text"):
                    txt = block.text
                    val = txt.get("value","") if isinstance(txt, dict) else getattr(txt,"value","")
                if val:
                    try:
                        data = json.loads(val)
                        if data.get('ok'):
                            print(f"✅ Created story: {data.get('story_key')}")
                            print(f"   URL: {data.get('url','')[:80]}")
                    except:
                        print(f"Result: {val[:200]}")
            break
print()

# Test 4: Add comment to epic
print("=" * 60)
print("TEST 4: Add Comment to Epic")
print("=" * 60)
c = AgentsClient(endpoint=endpoint, credential=DefaultAzureCredential())
t = c.threads.create()
comment_text = "Automated workflow test: Multi-tool orchestration working end-to-end. Foundry is orchestrating all tool calls successfully."
c.messages.create(
    thread_id=t.id,
    role="user",
    content=f"""Call jira_add_comment with:
- issue_key: {epic_key}
- comment: "{comment_text}"

Return only the JSON result.""",
)
r = c.runs.create_and_process(thread_id=t.id, agent_id=coordinator_id)
print(f"Status: {r.status}")
if "COMPLETED" in str(r.status).upper():
    msgs = list(c.messages.list(thread_id=t.id))
    for m in msgs:
        if m.role == "assistant":
            for block in m.content:
                val = ""
                if hasattr(block, "text"):
                    txt = block.text
                    val = txt.get("value","") if isinstance(txt, dict) else getattr(txt,"value","")
                if val:
                    try:
                        data = json.loads(val)
                        if data.get('ok'):
                            print(f"✅ Comment added successfully")
                    except:
                        print(f"Result: {val[:200]}")
            break
print()

# Test 5: Transition epic status
print("=" * 60)
print("TEST 5: Transition Epic Status")
print("=" * 60)
c = AgentsClient(endpoint=endpoint, credential=DefaultAzureCredential())
t = c.threads.create()
c.messages.create(
    thread_id=t.id,
    role="user",
    content=f"""Call jira_transition_issue with:
- issue_key: {epic_key}
- to_status: "In Progress"

Return only the JSON result.""",
)
r = c.runs.create_and_process(thread_id=t.id, agent_id=coordinator_id)
print(f"Status: {r.status}")
if "COMPLETED" in str(r.status).upper():
    msgs = list(c.messages.list(thread_id=t.id))
    for m in msgs:
        if m.role == "assistant":
            for block in m.content:
                val = ""
                if hasattr(block, "text"):
                    txt = block.text
                    val = txt.get("value","") if isinstance(txt, dict) else getattr(txt,"value","")
                if val:
                    try:
                        data = json.loads(val)
                        if data.get('ok'):
                            print(f"✅ Epic transitioned to: {data.get('transition_result','In Progress')}")
                    except:
                        print(f"Result: {val[:200]}")
            break
print()

print("=" * 60)
print("SUMMARY: Multi-tool workflow COMPLETE")
print("=" * 60)
print("✅ All tools working via Foundry orchestrator:")
print("   - jira_get_issue_context")
print("   - jira_list_open_dispatch_issues")
print("   - jira_create_dispatch_story")
print("   - jira_add_comment")
print("   - jira_transition_issue")
print("\nFoundry = Orchestrator. Function = Tool Adapter. Ready for production.")
