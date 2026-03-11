#!/usr/bin/env python3

import argparse
import base64
import json
import os
import subprocess
from pathlib import Path

import requests

RG = os.environ.get("AZURE_RESOURCE_GROUP", "")
APP = os.environ.get("REVIEW_FUNCTION_APP_NAME", "")
JIRA_BASE = os.environ.get("JIRA_BASE_URL", "")
JIRA_EMAIL = os.environ.get("JIRA_EMAIL", "")


def run_az(args: list[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    return result.stdout.strip()


def get_jira_token() -> str:
    return run_az(
        [
            "az",
            "functionapp",
            "config",
            "appsettings",
            "list",
            "--resource-group",
            RG,
            "--name",
            APP,
            "--query",
            "[?name=='JIRA_API_TOKEN'].value | [0]",
            "-o",
            "tsv",
        ]
    )


def get_function_key() -> str:
    return run_az(
        [
            "az",
            "functionapp",
            "keys",
            "list",
            "--resource-group",
            RG,
            "--name",
            APP,
            "--query",
            "functionKeys.default",
            "-o",
            "tsv",
        ]
    )


def create_epic(description: str, summary: str) -> str:
    token = get_jira_token()
    if not token:
        raise RuntimeError("Missing JIRA_API_TOKEN in function app settings")

    auth = base64.b64encode(f"{JIRA_EMAIL}:{token}".encode()).decode()
    headers = {
        "Authorization": f"Basic {auth}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    payload = {
        "fields": {
            "project": {"key": "KAN"},
            "summary": summary,
            "description": description,
            "issuetype": {"name": "Epic"},
            "labels": ["orchestration-test", "shopping-list", "mvp-ready", "no-fallback"],
        }
    }

    response = requests.post(f"{JIRA_BASE}/rest/api/2/issue", headers=headers, json=payload, timeout=60)
    if response.status_code not in (200, 201):
        raise RuntimeError(f"Failed to create epic: {response.status_code} {response.text[:400]}")

    return response.json()["key"]


def run_orchestration(epic_key: str) -> dict:
    function_key = get_function_key()
    if not function_key:
        raise RuntimeError("Missing function key")

    response = requests.post(
        f"https://{APP}.azurewebsites.net/api/execute_orchestrator_cycle",
        headers={"x-functions-key": function_key, "Content-Type": "application/json"},
        json={"epic_key": epic_key, "cycle_type": "full_review"},
        timeout=480,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Orchestration failed: {response.status_code} {response.text[:400]}")

    return response.json()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--draft",
        default="DevSecOpsAiTeam/docs/SHOPPING_LIST_EPIC.md",
        help="Path to epic draft markdown",
    )
    parser.add_argument(
        "--summary",
        default="Shopping List Web App MVP (Agent Validation Epic)",
        help="Jira summary",
    )
    args = parser.parse_args()

    draft_text = Path(args.draft).read_text(encoding="utf-8")

    epic_key = create_epic(draft_text, args.summary)
    print(f"epic_key: {epic_key}")
    print(f"epic_url: {JIRA_BASE}/browse/{epic_key}")

    result = run_orchestration(epic_key)
    print(f"orchestrator_status: 200")
    print(f"orchestration_id: {result.get('orchestration_id')}")
    print(f"status: {result.get('status')}")

    delivery_package = result.get("delivery_package", {})
    execution_summary = delivery_package.get("execution_summary", {})
    print(f"all_gates_passed: {delivery_package.get('all_gates_passed')}")
    print(f"agents_invoked: {execution_summary.get('total_agents_invoked')}")
    print(f"trace_len: {len(result.get('execution_trace', []))}")

    Path("/tmp/latest_epic_key.txt").write_text(epic_key, encoding="utf-8")
    Path("/tmp/latest_orchestration_result.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print("result_file: /tmp/latest_orchestration_result.json")


if __name__ == "__main__":
    main()
