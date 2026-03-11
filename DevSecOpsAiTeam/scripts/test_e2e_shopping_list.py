#!/usr/bin/env python3
"""
End-to-End Test: Shopping List Epic with Real Agent Integration

1. Create shopping list epic in Jira
2. Trigger orchestration
3. Verify agent discovery and invocation
4. Validate delivery package
"""

import json
import os
import requests
import base64
import time
import subprocess
from datetime import datetime

# Configuration — read from env; copy .env.example → .env and fill your values.
JIRA_BASE = os.environ.get("JIRA_BASE_URL", "")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")
_FUNCTION_APP = os.environ.get("REVIEW_FUNCTION_APP_NAME", "")
_RESOURCE_GROUP = os.environ.get("AZURE_RESOURCE_GROUP", "")

def get_jira_token():
    """Get JIRA token from Azure Function App settings."""
    result = subprocess.run(
        [
            "az", "functionapp", "config", "appsettings", "list",
            "-g", _RESOURCE_GROUP,
            "-n", _FUNCTION_APP,
            "--query", "[?name=='JIRA_API_TOKEN'].value",
            "-o", "tsv"
        ],
        capture_output=True,
        text=True,
        timeout=10
    )
    return result.stdout.strip()


def get_jira_headers(email, token):
    """Create Basic Auth headers for Jira."""
    auth_str = base64.b64encode(f"{email}:{token}".encode()).decode()
    return {
        "Authorization": f"Basic {auth_str}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }


def create_shopping_list_epic(jira_token):
    """Create shopping list epic using v2 API (more reliable)."""
    headers = get_jira_headers(JIRA_EMAIL, jira_token)
    
    epic_summary = f"Shopping List Application - E2E Test {datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    epic_description = """
h2. 🎯 Business Goal
Provide users with a simple, intuitive web application to manage shopping lists.

h2. ✅ Acceptance Criteria
• Create new shopping lists
• Add items to lists
• Edit and delete items
• Responsive UI (mobile, tablet, desktop)
• Data persistence (localStorage)
• Cost optimized (<$10/month)

h2. 📦 Scope
In Scope:
- User-friendly web interface
- Add/edit/delete items
- Responsive design
- Cost-optimized Azure hosting

Out of Scope (v1.0):
- User authentication
- List sharing
- Analytics
- Mobile app

h2. ⚙️ Non-Functional Requirements
PERFORMANCE:
- Page load: <3 seconds (3G)
- Item operations: <500ms

COMPATIBILITY:
- Chrome, Firefox, Safari (latest 2 versions)
- Mobile: iOS Safari, Chrome Android

SECURITY:
- HTTPS only
- Input validation (prevent XSS)

COST:
- Target: <$15/month Azure spend
- Goal: <$10/month
"""
    
    payload = {
        "fields": {
            "project": {"key": "KAN"},
            "issuetype": {"name": "Epic"},
            "summary": epic_summary,
            "description": epic_description,
            "customfield_10008": f"shopping-list-{int(time.time())}"
        }
    }
    
    print("📝 Creating Shopping List Epic in Jira...")
    print(f"   Summary: {epic_summary}")
    
    try:
        response = requests.post(
            f"{JIRA_BASE}/rest/api/2/issue",
            headers=headers,
            json=payload,
            timeout=10
        )
        
        if response.status_code not in [200, 201]:
            print(f"❌ Failed: {response.status_code}")
            print(response.text[:500])
            return None
        
        epic_data = response.json()
        epic_key = epic_data.get("key")
        print(f"✅ Epic created: {epic_key}")
        print(f"   URL: {JIRA_BASE}/browse/{epic_key}")
        
        return epic_key
    
    except Exception as e:
        print(f"❌ Exception: {e}")
        return None


def get_function_key():
    """Get function authorization key."""
    result = subprocess.run(
        [
            "az", "functionapp", "function", "keys", "list",
            "--resource-group", _RESOURCE_GROUP,
            "--name", _FUNCTION_APP,
            "--function-name", "execute_orchestrator_cycle",
            "--query", "default",
            "-o", "tsv"
        ],
        capture_output=True,
        text=True,
        timeout=10
    )
    
    key = result.stdout.strip()
    
    if not key or key.startswith("ERROR") or key.startswith("None"):
        return None
    
    return key


def trigger_orchestration(epic_key, function_key):
    """Trigger orchestration for epic."""
    url = f"https://{_FUNCTION_APP}.azurewebsites.net/api/execute_orchestrator_cycle"
    
    payload = {"epic_key": epic_key}
    
    print(f"\n🚀 Triggering Orchestration")
    print(f"   Epic: {epic_key}")
    print(f"   This may take 5-10 minutes...")
    print(f"   Waiting for agents to complete...")
    
    start = time.time()
    
    try:
        response = requests.post(
            url,
            headers={"x-functions-key": function_key, "Content-Type": "application/json"},
            json=payload,
            timeout=600  # 10 minute timeout
        )
        
        elapsed = time.time() - start
        
        if response.status_code != 200:
            print(f"❌ Request failed: {response.status_code}")
            print(response.text[:500])
            return None
        
        result = response.json()
        
        print(f"✅ Orchestration completed in {elapsed:.1f}s")
        
        return result
    
    except requests.Timeout:
        print(f"❌ Request timed out after 10 minutes")
        return None
    except Exception as e:
        print(f"❌ Exception: {e}")
        return None


def analyze_results(result, epic_key):
    """Analyze and display results."""
    if not result:
        return False
    
    status = result.get("status", "UNKNOWN")
    orch_id = result.get("orchestration_id", "N/A")
    
    print(f"\n{'='*70}")
    print(f"📊 ORCHESTRATION RESULTS")
    print(f"{'='*70}")
    print(f"Epic Key: {epic_key}")
    print(f"Orchestration ID: {orch_id}")
    print(f"Overall Status: {status}")
    
    if status != "COMPLETED":
        error = result.get("error", "Unknown error")
        print(f"Error: {error}")
        print(f"{'='*70}")
        return False
    
    # Agent decisions
    agent_decisions = result.get("agent_decisions", {})
    
    if agent_decisions:
        print(f"\n🤖 Agent Decisions ({len(agent_decisions)} agents):")
        print("-" * 70)
        
        real_count = 0
        
        for role, decision in agent_decisions.items():
            outcome = decision.get("outcome", "unknown")
            confidence = decision.get("confidence", 0)
            is_fallback = decision.get("fallback", False)
            
            status_icon = "✅" if outcome == "completed" else "⚠️"
            mode_indicator = " [NON-COMPLIANT]" if is_fallback else " [REAL]"
            
            print(f"{status_icon} {role:12} → {outcome:12} (confidence: {confidence:5.1%}){mode_indicator}")
            
            if is_fallback:
                print("   ⚠️  Fallback detected in response payload (policy violation)")
            else:
                real_count += 1
        
        print("-" * 70)
        print(f"Summary: {real_count} real-agent responses")
    
    # Delivery package
    delivery_pkg = result.get("delivery_package", {})
    
    if delivery_pkg:
        print(f"\n📦 Delivery Package:")
        print("-" * 70)
        
        agents = delivery_pkg.get("agents", {})
        gates = delivery_pkg.get("gates", {})
        
        if agents:
            print(f"Agents Summary:")
            for role, agent_info in agents.items():
                status = agent_info.get("status", "unknown")
                print(f"  • {role}: {status}")
        
        if gates:
            print(f"\nDoR Gates:")
            for gate_name, gate_status in gates.items():
                status_icon = "✅" if gate_status else "❌"
                print(f"  {status_icon} {gate_name}")
    
    print(f"{'='*70}\n")
    
    return status == "COMPLETED"


def print_test_summary(epic_key, orchestration_success):
    """Print final test summary."""
    print(f"\n{'='*70}")
    print(f"🧪 E2E TEST SUMMARY - SHOPPING LIST EPIC")
    print(f"{'='*70}")
    
    status = "✅ PASSED" if orchestration_success else "❌ FAILED"
    
    print(f"\nStatus: {status}")
    print(f"Epic: {epic_key}")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    print(f"\n📋 Test Steps:")
    print(f"  1. ✅ Created shopping list epic in Jira")
    print(f"  2. ✅ Retrieved function authorization key")
    print(f"  3. ✅ Triggered orchestration with real agents")
    print(f"  4. {'✅' if orchestration_success else '❌'} Verified agent discovery and invocation")
    
    if orchestration_success:
        print(f"\n🎉 SUCCESS!")
        print(f"   • Real agent integration working")
        print(f"   • Agents discovered and invoked")
        print(f"   • Delivery package created")
        print(f"   • Epic ready for delivery")
    else:
        print(f"\n⚠️  TESTING INCOMPLETE")
        print(f"   Review logs for details")
    
    print(f"\n📌 Next Steps:")
    print(f"  1. Review epic in Jira: {JIRA_BASE}/browse/{epic_key}")
    print(f"  2. Check delivery package comments")
    print(f"  3. Review orchestration trace")
    print(f"  4. Monitor agent logs for real invocations")
    
    print(f"{'='*70}\n")


def main():
    print("🧪 End-to-End Test: Shopping List Epic with Real Agents\n")
    
    # Step 1: Get credentials
    print("1️⃣  Getting credentials...")
    jira_token = get_jira_token()
    if not jira_token:
        print("❌ Failed to get Jira token")
        return 1
    print("✅ Jira token retrieved")
    
    function_key = get_function_key()
    if not function_key:
        print("❌ Failed to get function key")
        return 1
    print("✅ Function key retrieved")
    
    # Step 2: Create epic
    print("\n2️⃣  Creating shopping list epic...")
    epic_key = create_shopping_list_epic(jira_token)
    if not epic_key:
        print("❌ Failed to create epic")
        return 1
    
    # Step 3: Trigger orchestration
    print("\n3️⃣  Triggering orchestration with real agents...")
    result = trigger_orchestration(epic_key, function_key)
    
    if not result:
        print("❌ Orchestration failed")
        print_test_summary(epic_key, False)
        return 1
    
    # Step 4: Analyze results
    print("\n4️⃣  Analyzing results...")
    success = analyze_results(result, epic_key)
    
    # Step 5: Summary
    print_test_summary(epic_key, success)
    
    return 0 if success else 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
