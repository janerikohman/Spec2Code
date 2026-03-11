#!/usr/bin/env python3
"""
Simplified E2E Test: Test with existing epic or create new one
"""

import json
import os
import time
import subprocess
import requests
import base64
from datetime import datetime

JIRA_BASE = os.environ.get("JIRA_BASE_URL", "")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")
_FUNCTION_APP = os.environ.get("REVIEW_FUNCTION_APP_NAME", "")
_RESOURCE_GROUP = os.environ.get("AZURE_RESOURCE_GROUP", "")

# Fetch Jira token via subprocess
result = subprocess.run([
    "az", "functionapp", "config", "appsettings", "list",
    "-g", _RESOURCE_GROUP,
    "-n", _FUNCTION_APP,
    "--query", "[?name=='JIRA_API_TOKEN'].value",
    "-o", "tsv"
], capture_output=True, text=True, timeout=10)

JIRA_TOKEN = result.stdout.strip()


def get_function_key():
    result = subprocess.run([
        "az", "functionapp", "keys", "list",
        "-g", _RESOURCE_GROUP,
        "-n", _FUNCTION_APP,
        "--query", "functionKeys.default",
        "-o", "tsv"
    ], capture_output=True, text=True, timeout=15)
    return result.stdout.strip()

def get_jira_headers():
    auth = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_TOKEN}".encode()).decode()
    return {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/json",
    }


def create_or_use_epic():
    """Create epic and return its key."""
    headers = get_jira_headers()
    
    # Try to create
    data = {
        "fields": {
            "project": {"key": "KAN"},
            "issuetype": {"name": "Epic"},
            "summary": f"Shopping List E2E {int(time.time())}",
            "description": "E2E test for real agent integration"
        }
    }
    
    print("📝 Creating shopping list epic...")
    resp = requests.post(
        f"{JIRA_BASE}/rest/api/2/issue",
        headers=headers,
        json=data,
        timeout=10
    )
    
    if resp.status_code in [200, 201]:
        epic_key = resp.json().get("key")
        print(f"✅ Epic created: {epic_key}")
        return epic_key
    
    print(f"⚠️  Epic creation returned {resp.status_code}")
    print(f"   Trying alternate approach...")
    
    # Look for existing epic
    search = requests.get(
        f"{JIRA_BASE}/rest/api/2/search",
        headers=headers,
        params={"jql": 'project=KAN AND type=Epic ORDER BY created DESC', "maxResults": 1},
        timeout=10
    )
    
    if search.status_code == 200:
        issues = search.json().get("issues", [])
        if issues:
            epic_key = issues[0]["key"]
            print(f"✅ Using existing epic: {epic_key}")
            return epic_key
    
    raise RuntimeError("Could not create or find epic")


def trigger_orchestration(epic_key):
    """Trigger orchestration."""
    key = get_function_key()
    if not key:
        print("❌ Could not retrieve function key from Azure")
        return None
    url = f"https://{_FUNCTION_APP}.azurewebsites.net/api/execute_orchestrator_cycle"
    
    print(f"\n🚀 Triggering orchestration for {epic_key}...")
    
    start = time.time()
    resp = requests.post(
        url,
        headers={"x-functions-key": key, "Content-Type": "application/json"},
        json={"epic_key": epic_key},
        timeout=600
    )
    elapsed = time.time() - start
    
    if resp.status_code == 200:
        print(f"✅ Completed in {elapsed:.1f}s")
        return resp.json()
    else:
        print(f"❌ Failed: {resp.status_code}")
        return None


def display_results(result, epic_key):
    """Display orchestration results."""
    if not result:
        print("\n❌ No result returned")
        return False
    
    status = result.get("status")
    print(f"\n{'='*70}")
    print(f"📊 ORCHESTRATION COMPLETE")
    print(f"{'='*70}")
    print(f"Epic: {epic_key}")
    print(f"Status: {status}")
    
    agents = result.get("agent_decisions", {})
    if agents:
        print(f"\n🤖 Agents ({len(agents)}):")
        for role, data in agents.items():
            outcome = data.get("outcome", "unknown")
            confidence = data.get("confidence", 0)
            fallback = "FALLBACK" if data.get("fallback") else "REAL"
            print(f"   {role:12} → {outcome:12} [{fallback}]  (confidence: {confidence:.1%})")
    
    error = result.get("error")
    if error:
        print(f"\nError: {error}")
        return False
    
    print(f"{'='*70}\n")
    return status == "COMPLETED"


def main():
    print("🧪 E2E Test: Shopping List Epic with Real Agents\n")
    
    try:
        # Create/find epic
        epic_key = create_or_use_epic()
        
        # Trigger
        result = trigger_orchestration(epic_key)
        
        # Display
        success = display_results(result, epic_key)
        
        if success:
            print("✅ E2E TEST PASSED!")
            print(f"   Epic: {JIRA_BASE}/browse/{epic_key}")
            return 0
        else:
            print("⚠️  E2E test encountered issues")
            return 1
    
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
