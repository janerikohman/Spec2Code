#!/usr/bin/env python3
"""
🔄 Epic Orchestration Sync
Syncs orchestration with a manually-created Jira epic

Usage:
  python3 sync_epic_orchestration.py <EPIC_KEY>
  python3 sync_epic_orchestration.py KAN-250
  python3 sync_epic_orchestration.py KAN-250 --status
"""

import os
import sys
import time
import requests
import base64
import subprocess
import json
from datetime import datetime

JIRA_BASE = os.environ.get("JIRA_BASE_URL", "")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")
FUNCTION_APP = os.environ.get("REVIEW_FUNCTION_APP_NAME", "")
RESOURCE_GROUP = os.environ.get("AZURE_RESOURCE_GROUP", "")


def get_jira_token():
    """Get Jira token from Azure"""
    try:
        result = subprocess.run([
            "az", "functionapp", "config", "appsettings", "list",
            "-g", RESOURCE_GROUP,
            "-n", FUNCTION_APP,
            "--query", "[?name=='JIRA_API_TOKEN'].value",
            "-o", "tsv"
        ], capture_output=True, text=True, timeout=15)
        
        token = result.stdout.strip()
        return token if token else None
    except:
        return None


def get_function_key():
    """Get function key from Azure"""
    try:
        result = subprocess.run([
            "az", "functionapp", "keys", "list",
            "-g", RESOURCE_GROUP,
            "-n", FUNCTION_APP,
            "--query", "functionKeys.default",
            "-o", "tsv"
        ], capture_output=True, text=True, timeout=15)
        key = result.stdout.strip()
        return key if key else None
    except Exception:
        return None

def get_jira_headers(token):
    """Get Jira API headers"""
    auth = base64.b64encode(f"{JIRA_EMAIL}:{token}".encode()).decode()
    return {
        "Authorization": f"Basic {auth}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

def check_epic_exists(epic_key, token):
    """Check if epic exists in Jira"""
    if not token:
        return False, "No Jira token"
    
    headers = get_jira_headers(token)
    
    try:
        url = f"{JIRA_BASE}/rest/api/2/issue/{epic_key}"
        resp = requests.get(url, headers=headers, timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            summary = data.get('fields', {}).get('summary', '')
            status = data.get('fields', {}).get('status', {}).get('name', 'Unknown')
            return True, f"{epic_key}: {summary} (Status: {status})"
        elif resp.status_code == 404:
            return False, f"Epic {epic_key} not found in Jira"
        else:
            return False, f"API error: {resp.status_code}"
    except Exception as e:
        return False, f"Error checking epic: {e}"

def trigger_orchestration(epic_key, function_key):
    """Trigger orchestration for the epic"""
    url = f"https://{FUNCTION_APP}.azurewebsites.net/api/execute_orchestrator_cycle"
    
    print(f"🚀 Triggering orchestration for {epic_key}...")
    
    try:
        start = time.time()
        resp = requests.post(
            url,
            headers={"x-functions-key": function_key, "Content-Type": "application/json"},
            json={"epic_key": epic_key},
            timeout=600
        )
        elapsed = time.time() - start
        
        if resp.status_code == 200:
            data = resp.json()
            
            print(f"\n✅ Orchestration triggered successfully!")
            print(f"   Duration: {elapsed:.1f}s")
            print(f"   Orchestration ID: {data.get('orchestration_id', 'N/A')}")
            print(f"   Status: {data.get('status', 'N/A')}")
            print(f"   Epic: {JIRA_BASE}/browse/{epic_key}")
            
            # Show trace if available
            trace = data.get('execution_trace', [])
            if trace:
                print(f"\n   📋 Execution Trace ({len(trace)} steps):")
                for i, step in enumerate(trace[:10], 1):
                    print(f"      {i}. {step.get('step', 'Unknown step')}")
                if len(trace) > 10:
                    print(f"      ... and {len(trace) - 10} more")
            
            # Show errors if any
            error = data.get('error')
            if error:
                print(f"\n   ⚠️  Error: {error}")
            
            return data
        
        else:
            print(f"❌ HTTP {resp.status_code}")
            print(f"Response: {resp.text[:500]}")
            return None
    
    except requests.exceptions.Timeout:
        print(f"⚠️  Request timeout")
        print(f"   Orchestration may still be processing in the background")
        print(f"   Check Azure logs: az functionapp log tail -n {FUNCTION_APP} -g {RESOURCE_GROUP}")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def show_status(epic_key, token):
    """Show current status of epic"""
    print(f"\n📊 Checking epic status...")
    
    exists, info = check_epic_exists(epic_key, token)
    
    if exists:
        print(f"   ✅ {info}")
        print(f"   URL: {JIRA_BASE}/browse/{epic_key}")
    else:
        print(f"   ❌ {info}")
    
    return exists

def main():
    if len(sys.argv) < 2:
        print("Usage: python3 sync_epic_orchestration.py <EPIC_KEY> [--status]")
        print("Example: python3 sync_epic_orchestration.py KAN-250")
        print("Example: python3 sync_epic_orchestration.py KAN-250 --status")
        return 1
    
    epic_key = sys.argv[1].upper()
    check_status_only = "--status" in sys.argv
    
    print("=" * 70)
    print(f"🔄 Epic Orchestration Sync")
    print("=" * 70)
    
    print(f"\n📌 Epic Key: {epic_key}")
    print(f"   Jira: {JIRA_BASE}")
    print(f"   Function App: {FUNCTION_APP}")
    
    # Get Jira token
    token = get_jira_token()
    function_key = get_function_key()
    
    if not token:
        print("\n❌ Could not retrieve Jira token from Azure")
        return 1

    if not function_key:
        print("\n❌ Could not retrieve function key from Azure")
        return 1
    
    print(f"\n✅ Configuration loaded")
    
    # Check if epic exists
    print(f"\n🔍 Verifying epic exists...")
    exists, info = check_epic_exists(epic_key, token)
    
    if not exists:
        print(f"   ❌ {info}")
        print(f"\n   Please create the epic first:")
        print(f"   1. Go to: {JIRA_BASE}")
        print(f"   2. Click 'Create' → 'Epic'")
        print(f"   3. Fill in 'Simple Shopping List Application'")
        print(f"   4. Add labels: shopping-list, web-app, mvp, real-agent-orchestration")
        print(f"   5. Note the epic key (e.g., KAN-250)")
        return 1
    
    print(f"   ✅ {info}")
    
    # If only checking status, stop here
    if check_status_only:
        print(f"\n   Ready for orchestration. Run without --status to trigger:")
        print(f"   python3 sync_epic_orchestration.py {epic_key}")
        return 0
    
    # Trigger orchestration
    print(f"\n" + "=" * 70)
    
    result = trigger_orchestration(epic_key, function_key)
    
    print(f"\n" + "=" * 70)
    
    if result:
        status = result.get('status', 'UNKNOWN')
        
        if status == 'COMPLETED':
            print(f"\n✨ Orchestration COMPLETED!")
            print(f"\n📋 Results:")
            print(f"   • Agent decisions logged to epic")
            print(f"   • Comments posted to Jira")
            print(f"   • Delivery packages generated")
            print(f"   • Epic updated with orchestration results")
        
        elif status == 'FAILED':
            print(f"\n⚠️  Orchestration FAILED")
            error = result.get('error', 'Unknown error')
            print(f"   Error: {error}")
        
        else:
            print(f"\n⏳ Orchestration Status: {status}")
            print(f"   Check Jira epic for updates")
            print(f"   View logs: az functionapp log tail -n {FUNCTION_APP} -g {RESOURCE_GROUP}")
        
        print(f"\n📌 Epic: {JIRA_BASE}/browse/{epic_key}")
        print(f"   Check Jira epic for agent decisions and comments")
        
        return 0 if status in ['COMPLETED', 'RUNNING'] else 1
    
    else:
        print(f"\n⚠️  Could not trigger orchestration")
        return 1

if __name__ == '__main__':
    sys.exit(main())
