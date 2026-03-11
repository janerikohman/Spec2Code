#!/usr/bin/env python3
"""
Fix function-tools-connection credentials via ARM REST API.
Uses DefaultAzureCredential (az login session).
"""
import subprocess
import json
import urllib.request

SUBSCRIPTION = "cb618913-1871-4b42-a194-915f6eb0ac8c"
RESOURCE_GROUP = "AgenticDevSecOps"
ACCOUNT = "AgenticDevSecOpsTeam-resource"
PROJECT = "AgenticDevSecOpsTeam"
CONNECTION = "function-tools-connection"
FUNCTION_URL = "https://epicreview257529268.azurewebsites.net"

def get_token(resource):
    result = subprocess.run(
        ["az", "account", "get-access-token", "--resource", resource, "--query", "accessToken", "-o", "tsv"],
        capture_output=True, text=True, check=True
    )
    return result.stdout.strip()

def get_function_host_key():
    result = subprocess.run(
        ["az", "functionapp", "keys", "list",
         "--name", "epicreview257529268",
         "--resource-group", "AgenticDevSecOps",
         "--query", "functionKeys.default", "-o", "tsv"],
        capture_output=True, text=True, check=True
    )
    return result.stdout.strip()

def put_connection(token, host_key):
    url = (
        f"https://management.azure.com/subscriptions/{SUBSCRIPTION}"
        f"/resourceGroups/{RESOURCE_GROUP}"
        f"/providers/Microsoft.CognitiveServices/accounts/{ACCOUNT}"
        f"/projects/{PROJECT}"
        f"/connections/{CONNECTION}?api-version=2025-04-01-preview"
    )
    body = {
        "properties": {
            "authType": "ApiKey",
            "category": "ApiKey",
            "target": FUNCTION_URL,
            "credentials": {"key": host_key},
            "metadata": {
                "ApiType": "Web",
                "description": "Azure Function tool adapter"
            }
        }
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="PUT")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def get_connection(token):
    url = (
        f"https://management.azure.com/subscriptions/{SUBSCRIPTION}"
        f"/resourceGroups/{RESOURCE_GROUP}"
        f"/providers/Microsoft.CognitiveServices/accounts/{ACCOUNT}"
        f"/projects/{PROJECT}"
        f"/connections/{CONNECTION}?api-version=2025-04-01-preview"
    )
    req = urllib.request.Request(url, method="GET")
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

if __name__ == "__main__":
    print("Getting ARM token...")
    token = get_token("https://management.azure.com")
    print("Getting Function host key...")
    host_key = get_function_host_key()
    print(f"Host key prefix: {host_key[:8]}...")
    print("Sending ARM PUT to set connection credentials...")
    try:
        result = put_connection(token, host_key)
        creds = result.get("properties", {}).get("credentials")
        print(f"PUT succeeded. credentials field: {creds}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        print(f"PUT failed HTTP {e.code}: {body}")
        raise

    print("\nVerifying with GET...")
    verify = get_connection(token)
    creds_after = verify.get("properties", {}).get("credentials")
    auth_type = verify.get("properties", {}).get("authType")
    target = verify.get("properties", {}).get("target")
    print(f"authType: {auth_type}")
    print(f"target: {target}")
    print(f"credentials after PUT: {creds_after}")
    if creds_after and creds_after.get("key"):
        print("\nSUCCESS: credentials.key is set")
    else:
        print("\nWARNING: credentials still null/empty after PUT")
