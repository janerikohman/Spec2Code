#!/usr/bin/env python3
"""
Manual Epic Creation and Orchestration Test

This script:
1. Creates an epic manually via Jira API
2. Verifies the orchestration endpoint with the created epic
3. Validates agent invocation

The APIv3 endpoint uses a different payloadthan v2.
"""

import requests
import base64
import json
import time
import os
import subprocess

JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")
JIRA_BASE = os.environ.get("JIRA_BASE_URL", "")
FUNCTION_URL = os.environ.get("REVIEW_ENDPOINT_BASE_URL", "").replace("/api", "").rstrip("/")

def get_jira_token():
    """Get Jira token from environment or .env file"""
    token = os.getenv('JIRA_API_TOKEN', '')
    
    if not token:
        try:
            with open('/.env', 'r') as f:
                for line in f:
                    if 'JIRA_API_TOKEN' in line:
                        token = line.split('=')[1].strip()
                        break
        except:
            pass
    
    return token

def get_function_key():
    """Get function key from Azure"""
    try:
        rg = os.environ.get("AZURE_RESOURCE_GROUP", "")
        func_app = os.environ.get("REVIEW_FUNCTION_APP_NAME", "")
        
        result = subprocess.run([
            'az', 'functionapp', 'function', 'keys', 'list',
            '-n', func_app,
            '-g', rg,
            '--function-name', 'execute_orchestrator_cycle',
            '-o', 'tsv',
            '--query', 'value'
        ], capture_output=True, text=True, timeout=30)
        
        if result.returncode == 0:
            lines = result.stdout.strip().split('\n')
            if lines and lines[0]:
                return lines[0]
    except Exception as e:
        print(f"⚠️  Could not fetch function key via Azure: {e}")
    
    return None

def create_epic_v3(token):
    """
    Create an epic using Jira API v3.
    API v3 has a different payload structure than v2.
    """
    if not token:
        print("❌ No Jira API token available")
        return None
    
    auth = base64.b64encode(f"{JIRA_EMAIL}:{token}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    payload = {
        "fields": {
            "project": {"key": "KAN"},
            "summary": "Test Shopping List Orchestration",
            "description": "Epic for testing real agent orchestration with shopping list scenario",
            "issuetype": {"name": "Epic"},
            "labels": ["orchestration-test", "agent-integration"],
            "components": [{"name": "Orchestration"}, {"name": "DevSecOpsAgents"}]
        }
    }
    
    print("📝 Creating epic via Jira API v3...")
    print(f"🎯 Project: KAN")
    print(f"📌 Summary: {payload['fields']['summary']}")
    
    try:
        url = f"{JIRA_BASE}/rest/api/3/issue"
        print(f"   POST {url}")
        
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        
        print(f"   Status: {resp.status_code}")
        
        if resp.status_code in [200, 201]:
            data = resp.json()
            epic_key = data.get('key', '')
            epic_id = data.get('id', '')
            
            print(f"\n✅ Epic created successfully!")
            print(f"   Key: {epic_key}")
            print(f"   ID: {epic_id}")
            print(f"   🔗 URL: {JIRA_BASE}/browse/{epic_key}")
            
            return epic_key
        
        else:
            print(f"❌ Failed: {resp.status_code}")
            print(f"   Response: {resp.text[:300]}")
            
            if resp.status_code == 404:
                print("\n💡 API v3 endpoint not found. Trying alternative...")
            
            return None
    
    except requests.exceptions.Timeout:
        print("❌ Request timeout")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def test_orchestration(epic_key, func_key):
    """Test orchestration endpoint with the created epic"""
    if not epic_key or not func_key:
        print("❌ Missing epic key or function key")
        return False
    
    print(f"\n🚀 Testing orchestration with epic {epic_key}...")
    
    try:
        url = f"{FUNCTION_URL}/api/execute_orchestrator_cycle"
        headers = {"Content-Type": "application/json", "x-functions-key": func_key}
        payload = {"epic_key": epic_key}
        
        print(f"   POST {url}")
        print(f"   Payload: {json.dumps(payload)}")
        
        resp = requests.post(url, headers=headers, json=payload, timeout=300)
        
        print(f"   Status: {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            print(f"\n✅ Orchestration triggered successfully!")
            print(f"   ID: {data.get('orchestration_id', 'N/A')}")
            print(f"   Status: {data.get('status', 'N/A')}")
            
            if data.get('status') == 'FAILED':
                print(f"   Error: {data.get('error', 'N/A')}")
                return False
            
            return True
        
        else:
            print(f"❌ Failed: {resp.status_code}")
            print(f"   Response: {resp.text[:500]}")
            return False
    
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def main():
    print("=" * 70)
    print("🧪 Manual Epic Creation and Orchestration Test")
    print("=" * 70)
    
    token = get_jira_token()
    func_key = get_function_key()
    
    print(f"\n📊 Configuration:")
    print(f"   Jira: {JIRA_BASE}")
    print(f"   Token: {'✅ Found' if token else '❌ Not found'}")
    print(f"   Function App: {os.environ.get('REVIEW_FUNCTION_APP_NAME', '<unset>')} ({os.environ.get('AZURE_RESOURCE_GROUP', '<unset>')})")
    print(f"   Function Key: {'✅ Found' if func_key else '❌ Not found'}")
    
    if not token:
        print("\n💡 To proceed, set JIRA_API_TOKEN environment variable:")
        print("   export JIRA_API_TOKEN=<your-token>")
        return 1
    
    if not func_key:
        print("\n⚠️  Could not retrieve function key. Using fallback...")
        func_key = os.getenv('AZURE_FUNCTION_KEY', '')
        
        if not func_key:
            print("   Set AZURE_FUNCTION_KEY environment variable")
            return 1
    
    print("\n" + "=" * 70)
    
    epic_key = create_epic_v3(token)
    
    if not epic_key:
        print("\n💡 Alternative: Create epic manually in Jira UI and run:")
        print("   python3 manual_epic_test.py <epic_key>")
        
        import sys
        if len(sys.argv) > 1:
            epic_key = sys.argv[1]
            print(f"\n✅ Using provided epic key: {epic_key}")
        else:
            return 1
    
    print("\n" + "=" * 70)
    
    success = test_orchestration(epic_key, func_key)
    
    print("\n" + "=" * 70)
    
    if success:
        print("✨ Test completed successfully!")
        print(f"\n📌 Next: Check the orchestration output and verify agent invocation")
        print(f"   Epic: {JIRA_BASE}/browse/{epic_key}")
        print(f"   Logs: Azure Function App > Functions > execute_orchestrator_cycle")
        return 0
    else:
        print("⚠️  Test encountered issues. Check output above.")
        return 1

if __name__ == '__main__':
    import sys
    sys.exit(main())
