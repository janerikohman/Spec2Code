#!/usr/bin/env python3
"""Trigger orchestration for test epics"""

import os
import requests
import json
import sys

_FUNCTION_APP = os.environ.get("REVIEW_FUNCTION_APP_NAME", "")
_JIRA_BASE = os.environ.get("JIRA_BASE_URL", "")

def trigger_epic_orchestration(epic_key):
    """Trigger orchestration for an epic"""
    function_app_url = f"https://{_FUNCTION_APP}.azurewebsites.net"
    
    print(f"🚀 Triggering orchestration for {epic_key}...\n")
    
    payload = {
        "epic_key": epic_key,
        "trigger": "manual"
    }
    
    try:
        response = requests.post(
            f"{function_app_url}/api/execute_orchestrator_cycle",
            json=payload,
            timeout=300
        )
        
        print(f"Status Code: {response.status_code}\n")
        
        if response.status_code in [200, 202]:
            try:
                result = response.json()
                print(f"Response:\n{json.dumps(result, indent=2)}")
            except:
                print(f"Response:\n{response.text[:500]}")
            
            print(f"\n✅ Orchestration started for {epic_key}")
            return True
        else:
            print(f"⚠️ Status: {response.status_code}")
            print(f"Response: {response.text[:500]}")
            return False
            
    except requests.exceptions.Timeout:
        print(f"⏱️ Request timeout (orchestration running - this is normal)")
        return True
    except requests.exceptions.ConnectionError as e:
        print(f"❌ Connection error: {e}")
        return False
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    epics = ["KAN-133", "KAN-134", "KAN-135"]
    
    print("="*70)
    print("  ORCHESTRATION TRIGGER FOR 3 TEST EPICS")
    print("="*70)
    print()
    
    results = {}
    for epic in epics:
        success = trigger_epic_orchestration(epic)
        results[epic] = "✅ Started" if success else "❌ Failed"
        print()
    
    # Summary
    print("="*70)
    print("  SUMMARY")
    print("="*70)
    for epic, status in results.items():
        print(f"  {epic}: {status}")
    print()
    
    print("⏳ NEXT STEPS - MONITOR PROGRESS:")
    print("="*70)
    print()
    print("1️⃣  WATCH JIRA EPICS (for Coordinator comments & status changes):")
    print(f"   • KAN-133: {_JIRA_BASE}/browse/KAN-133")
    print(f"   • KAN-134: {_JIRA_BASE}/browse/KAN-134")
    print(f"   • KAN-135: {_JIRA_BASE}/browse/KAN-135")
    print()
    print("2️⃣  MONITOR CONFLUENCE (for Delivery Package pages):")
    print(f"   • {_JIRA_BASE}/wiki/spaces/DEV/pages")
    print("   • Look for pages named 'Delivery Package: KAN-XXX'")
    print()
    print("3️⃣  CHECK AZURE LOGS (for real-time orchestration details):")
    print(f"   • Function App: {_FUNCTION_APP}")
    print(f"   • Application Insights: {_FUNCTION_APP}")
    print()
    print("4️⃣  EXPECTED OUTCOMES (per epic):")
    print("   • KAN-133 (8 agents): ~20-25 minutes")
    print("     - Full path: PO → Architect → Security → DevOps → Dev → QA → FinOps → Release")
    print()
    print("   • KAN-134 (5 agents): ~15-20 minutes")
    print("     - Infrastructure path: PO → Architect → DevOps → FinOps → Release")
    print()
    print("   • KAN-135 (4 agents): ~10-15 minutes")
    print("     - Bug fix path: PO → Developer → QA → Release")
    print()
    print("5️⃣  SUCCESS INDICATORS:")
    print("   ✓ Jira comment from Coordinator Agent")
    print("   ✓ Epic status → READY_FOR_DELIVERY")
    print("   ✓ Confluence page created")
    print("   ✓ Implementation story auto-created")
    print("   ✓ No errors in Azure logs")
    print()
    print("="*70)

if __name__ == "__main__":
    main()
