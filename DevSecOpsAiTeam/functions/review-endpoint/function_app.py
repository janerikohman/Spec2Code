"""
Minimal Azure Function App - 100% Agentic Architecture

This function is ONLY a webhook receiver and delegator.
All orchestration logic lives in the Coordinator Agent (running in AI Foundry).

Version: 2.0 (100% Agentic - No Legacy Function Orchestration)
"""

import json
import os
import logging
import base64
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

import azure.functions as func
import requests
from coordinator_agent import CoordinatorAgent
from keyvault_secrets import jira_email, jira_api_token

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Spec2Code")

try:
    from azure.ai.agents import AgentsClient
    from azure.identity import DefaultAzureCredential
except Exception:
    AgentsClient = None
    DefaultAzureCredential = None

AI_FOUNDRY_PROJECT_ENDPOINT = os.getenv("AI_FOUNDRY_PROJECT_ENDPOINT", "")


def _normalize_project_endpoint(endpoint: str) -> str:
    value = (endpoint or "").strip().rstrip("/")
    if not value:
        return ""

    if "/api/projects/" in value:
        return value

    if value.endswith(".services.ai.azure.com") or ".services.ai.azure.com/" in value:
        return value

    if value.endswith(".cognitiveservices.azure.com") or ".cognitiveservices.azure.com/" in value:
        return value

    return value


def resolve_foundry_project_endpoint() -> tuple[str, str]:
    configured_project_endpoint = _normalize_project_endpoint(
        os.getenv("AI_FOUNDRY_PROJECT_ENDPOINT", "")
    )
    if configured_project_endpoint:
        return configured_project_endpoint, "AI_FOUNDRY_PROJECT_ENDPOINT"

    return "", "UNSET"

# Initialize Azure clients
app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

foundry_client = None
sdk_bootstrap_error = ""
foundry_client_init_error = ""
foundry_endpoint_source = "UNSET"


def ensure_foundry_sdk_available() -> bool:
    global AgentsClient
    global DefaultAzureCredential
    global sdk_bootstrap_error

    sdk_bootstrap_error = ""

    if AgentsClient is not None and DefaultAzureCredential is not None:
        return True

    sdk_bootstrap_error = "import_error: azure-ai-agents or azure-identity unavailable"
    logger.error("❌ Required Foundry SDK packages are not importable at startup")
    return False


def get_foundry_client() -> Any:
    global foundry_client
    global foundry_client_init_error
    global foundry_endpoint_source
    if foundry_client is not None:
        return foundry_client

    foundry_client_init_error = ""

    if not ensure_foundry_sdk_available():
        logger.error("❌ Unable to load Azure AI Agents SDK")
        foundry_client_init_error = sdk_bootstrap_error or "sdk_bootstrap_failed"
        return None

    if AgentsClient is None or DefaultAzureCredential is None:
        logger.error("❌ Azure AI Agents SDK not available")
        foundry_client_init_error = "azure_ai_agents_sdk_unavailable"
        return None

    resolved_endpoint, endpoint_source = resolve_foundry_project_endpoint()
    foundry_endpoint_source = endpoint_source

    if not resolved_endpoint:
        logger.error("❌ AI Foundry endpoint not configured")
        foundry_client_init_error = "foundry_endpoint_not_configured"
        return None

    try:
        logger.info(f"🔄 Initializing AI Foundry client with endpoint: {resolved_endpoint} (source={endpoint_source})")
        credential = DefaultAzureCredential()
        foundry_client = AgentsClient(
            endpoint=resolved_endpoint,
            credential=credential
        )
        logger.info("✅ AI Foundry client initialized successfully")
        return foundry_client
    except Exception as e:
        logger.error(f"❌ Failed to initialize AI Foundry client: {type(e).__name__}: {e}", exc_info=True)
        foundry_client_init_error = f"{type(e).__name__}: {e}"
        return None


# ============================================================================
# WEBHOOK ENDPOINT - Main Entry Point
# ============================================================================

@app.route(route="execute_orchestrator_cycle", methods=["POST"])
async def execute_orchestrator_cycle(req: func.HttpRequest) -> func.HttpResponse:
    """
    Minimal webhook receiver for epic orchestration.
    
    ✅ DOES:
    - Validate webhook payload
    - Delegate to Coordinator Agent
    - Return result
    
    ❌ DOES NOT (all moved to Coordinator Agent):
    - Parse epic data
    - Determine agent sequence
    - Invoke individual agents
    - Enforce DoR gates
    - Manage feedback loops
    - Handle conflict resolution
    - Transition epic status
    """
    
    try:
        # 1. Parse request
        payload = req.get_json()
        epic_key = payload.get("epic_key", "").strip()
        
        if not epic_key:
            logger.warning("❌ Missing epic_key in request")
            return func.HttpResponse(
                json.dumps({"error": "epic_key is required"}),
                status_code=400,
                mimetype="application/json"
            )
        
        logger.info(f"🚀 Starting orchestration for epic: {epic_key}")
        
        # 2. Validate Foundry client
        foundry = get_foundry_client()
        if not foundry:
            return func.HttpResponse(
                json.dumps({
                    "error": "AI Foundry client not initialized",
                    "hint": "Check endpoint settings and credential access (managed identity / service principal)",
                    "sdk_bootstrap_error": sdk_bootstrap_error,
                    "client_init_error": foundry_client_init_error,
                    "endpoint_source": foundry_endpoint_source
                }),
                status_code=500,
                mimetype="application/json"
            )
        
        # 3. Delegate to Coordinator Agent
        coordinator = CoordinatorAgent(foundry)
        result = await coordinator.orchestrate_epic(epic_key)
        
        logger.info(f"✅ Orchestration completed for epic: {epic_key}")
        
        # 4. Return result
        return func.HttpResponse(
            json.dumps(result),
            status_code=200,
            mimetype="application/json"
        )
    
    except ValueError:
        logger.error("❌ Invalid JSON in request body")
        return func.HttpResponse(
            json.dumps({"error": "Invalid JSON body"}),
            status_code=400,
            mimetype="application/json"
        )
    
    except Exception as e:
        logger.error(f"❌ Orchestration failed: {str(e)}", exc_info=True)
        return func.HttpResponse(
            json.dumps({
                "error": "orchestration_failed",
                "details": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }),
            status_code=500,
            mimetype="application/json"
        )


# ============================================================================
# HEALTH CHECK ENDPOINT
# ============================================================================

@app.route(route="health", methods=["GET"])
def health_check(req: func.HttpRequest) -> func.HttpResponse:
    """Simple health check endpoint."""
    return func.HttpResponse(
        json.dumps({
            "status": "healthy",
            "service": "Spec2Code Orchestration",
            "version": "2.0-agentic",
            "timestamp": datetime.utcnow().isoformat()
        }),
        status_code=200,
        mimetype="application/json"
    )


@app.route(route="debug", methods=["GET"])
def debug_info(req: func.HttpRequest) -> func.HttpResponse:
    """Debug information endpoint - shows AI Foundry client status"""
    import sys
    import subprocess
    
    info = {
        "timestamp": datetime.utcnow().isoformat(),
        "python_version": sys.version,
        "python_path": sys.executable,
        "ai_agents_available": AgentsClient is not None,
        "credential_available": DefaultAzureCredential is not None,
        "endpoint_configured": bool(resolve_foundry_project_endpoint()[0]),
        "endpoint_value": resolve_foundry_project_endpoint()[0] if resolve_foundry_project_endpoint()[0] else "NOT SET",
        "endpoint_source": resolve_foundry_project_endpoint()[1],
        "foundry_client_initialized": foundry_client is not None,
        "sdk_bootstrap_error": sdk_bootstrap_error,
        "client_init_error": foundry_client_init_error,
    }
    
    # Try to list installed packages
    try:
        result = subprocess.run([sys.executable, "-m", "pip", "list"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            azure_packages = [line for line in result.stdout.split('\n') if 'azure' in line.lower()]
            info["azure_packages"] = azure_packages
    except Exception as e:
        info["package_list_error"] = str(e)
    
    # Try to initialize and capture the error
    if not foundry_client:
        try:
            resolved_endpoint, _ = resolve_foundry_project_endpoint()
            if AgentsClient and DefaultAzureCredential and resolved_endpoint:
                test_cred = DefaultAzureCredential()
                test_client = AgentsClient(
                    endpoint=resolved_endpoint,
                    credential=test_cred
                )
                info["initialization_test"] = "SUCCESS"
        except Exception as e:
            info["initialization_test"] = "FAILED"
            info["initialization_error"] = f"{type(e).__name__}: {str(e)}"

    epic_key = (req.params.get("epic_key") or "").strip()
    if epic_key:
        try:
            email = jira_email()
            token = jira_api_token()
            encoded = base64.b64encode(f"{email}:{token}".encode("utf-8")).decode("utf-8")
            jira_base = os.environ.get("JIRA_BASE_URL", "")
            probe = requests.get(
                f"{jira_base}/rest/api/2/issue/{epic_key}",
                headers={
                    "Authorization": f"Basic {encoded}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=30,
            )
            info["jira_probe"] = {
                "epic_key": epic_key,
                "jira_base_url": jira_base,
                "email_preview": f"{email[:3]}***@***" if "@" in email else "set",
                "email_secret_name": os.environ.get("JIRA_EMAIL_SECRET_NAME", "JIRA-EMAIL"),
                "token_secret_name": os.environ.get("JIRA_API_TOKEN_SECRET_NAME", "JIRA-API-TOKEN"),
                "status_code": probe.status_code,
                "response_excerpt": probe.text[:400],
            }
        except Exception as e:
            info["jira_probe"] = {
                "epic_key": epic_key,
                "error": f"{type(e).__name__}: {str(e)}",
            }
    
    return func.HttpResponse(
        json.dumps(info, indent=2),
        status_code=200,
        mimetype="application/json"
    )


# ============================================================================
# CONFIGURATION ENDPOINT (Optional)
# ============================================================================

@app.route(route="config", methods=["GET"])
def get_config(req: func.HttpRequest) -> func.HttpResponse:
    """Get runtime configuration (non-sensitive)."""
    
    return func.HttpResponse(
        json.dumps({
            "foundry_client_initialized": foundry_client is not None,
            "coordinator_agent_available": True,
            "architecture": "100% Agentic (v2.0)",
            "agents": [
                "coordinator",
                "po-requirements",
                "architect",
                "security-architect",
                "devops-iac",
                "developer",
                "tester-qa",
                "finops",
                "release-manager"
            ]
        }),
        status_code=200,
        mimetype="application/json"
    )


# ============================================================================
# TOOL ADAPTER ENDPOINTS (used by Foundry OpenAPI tools)
# ============================================================================

def _tool_response(payload: Dict[str, Any], status_code: int = 200) -> func.HttpResponse:
    return func.HttpResponse(
        json.dumps(payload),
        status_code=status_code,
        mimetype="application/json",
    )


def _tool_error(error: str, status_code: int = 400, details: str = "") -> func.HttpResponse:
    body: Dict[str, Any] = {"ok": False, "error": error}
    if details:
        body["details"] = details
    return _tool_response(body, status_code=status_code)


def _resolve_epic_link_field_id(headers: Dict[str, str], jira_base_url: str) -> str:
    response = requests.get(
        f"{jira_base_url}/rest/api/3/field",
        headers=headers,
        timeout=30,
    )
    if response.status_code != 200:
        return ""

    for field in response.json():
        name = (field.get("name") or "").strip().lower()
        schema = field.get("schema") or {}
        custom_type = (schema.get("custom") or "").lower()
        if name == "epic link" or "epic-link" in custom_type:
            return field.get("id") or ""
    return ""


def _review_endpoint_root() -> Path:
    return Path(__file__).resolve().parent


def _project_root() -> Path:
    return _review_endpoint_root().parents[2]


def _run_whitelisted_script(action: str, epic_key: str = "") -> Dict[str, Any]:
    root = _project_root()
    allowed_actions: Dict[str, Dict[str, Any]] = {
        "prepare_bitbucket_repo": {
            "runner": "python",
            "script": root / "scripts" / "prepare_bitbucket_epic_repo.py",
            "args": ["--epic", epic_key] if epic_key else [],
        },
        "create_bitbucket_pr": {
            "runner": "python",
            "script": root / "scripts" / "create_bitbucket_pr.py",
            "args": ["--epic", epic_key] if epic_key else [],
        },
        "run_specialist_dispatch": {
            "runner": "python",
            "script": root / "scripts" / "run_specialist_dispatch.py",
            "args": ["--epic", epic_key] if epic_key else [],
        },
        "deploy_review_function": {
            "runner": "bash",
            "script": root / "scripts" / "deploy-review-function.sh",
            "args": [],
        },
        "deploy_epic_scheduler": {
            "runner": "bash",
            "script": root / "scripts" / "deploy-epic-scheduler.sh",
            "args": [],
        },
        "test_orchestrator_cycle": {
            "runner": "bash",
            "script": root / "scripts" / "test-orchestrator-cycle.sh",
            "args": [],
        },
    }

    selected = allowed_actions.get(action)
    if not selected:
        raise RuntimeError(f"Unsupported action: {action}")

    script_path = selected["script"]
    if not Path(script_path).exists():
        raise RuntimeError(f"Script not found: {script_path}")

    if selected["runner"] == "python":
        command: List[str] = ["python3", str(script_path), *selected["args"]]
    else:
        command = ["bash", str(script_path), *selected["args"]]

    result = subprocess.run(
        command,
        cwd=str(root),
        capture_output=True,
        text=True,
        timeout=900,
    )

    return {
        "ok": result.returncode == 0,
        "action": action,
        "command": command,
        "returncode": result.returncode,
        "stdout": (result.stdout or "")[:8000],
        "stderr": (result.stderr or "")[:8000],
    }


@app.route(route="tool/jira/get_issue_context", methods=["POST"])
def tool_jira_get_issue_context(req: func.HttpRequest) -> func.HttpResponse:
    try:
        payload = req.get_json()
        issue_key = (payload.get("issue_key") or "").strip()
        include_comments = bool(payload.get("include_comments", False))
        max_comments = int(payload.get("max_comments", 10) or 10)

        if not issue_key:
            return _tool_error("issue_key is required", 400)

        coordinator = CoordinatorAgent(get_foundry_client())
        issue = coordinator._get_jira_issue_context(issue_key)

        if not include_comments:
            fields = issue.get("fields", {})
            if isinstance(fields, dict) and isinstance(fields.get("comment"), dict):
                fields.pop("comment", None)
        else:
            fields = issue.get("fields", {})
            comment_block = fields.get("comment", {}) if isinstance(fields, dict) else {}
            comments = comment_block.get("comments", []) if isinstance(comment_block, dict) else []
            if isinstance(comment_block, dict):
                comment_block["comments"] = comments[:max(1, max_comments)]

        return _tool_response({"ok": True, "issue": issue})
    except Exception as e:
        return _tool_error("jira_get_issue_context_failed", 500, str(e))


@app.route(route="tool/jira/add_comment", methods=["POST"])
def tool_jira_add_comment(req: func.HttpRequest) -> func.HttpResponse:
    try:
        payload = req.get_json()
        issue_key = (payload.get("issue_key") or "").strip()
        comment = (payload.get("comment") or "").strip()

        if not issue_key or not comment:
            return _tool_error("issue_key and comment are required", 400)

        coordinator = CoordinatorAgent(get_foundry_client())
        coordinator._add_jira_comment(issue_key, comment)
        return _tool_response({"ok": True, "issue_key": issue_key})
    except Exception as e:
        return _tool_error("jira_add_comment_failed", 500, str(e))


@app.route(route="tool/jira/transition_issue", methods=["POST"])
async def tool_jira_transition_issue(req: func.HttpRequest) -> func.HttpResponse:
    try:
        payload = req.get_json()
        issue_key = (payload.get("issue_key") or "").strip()
        to_status = (payload.get("to_status") or "").strip()

        if not issue_key or not to_status:
            return _tool_error("issue_key and to_status are required", 400)

        coordinator = CoordinatorAgent(get_foundry_client())
        await coordinator._transition_epic(issue_key, to_status)
        return _tool_response({"ok": True, "issue_key": issue_key, "to_status": to_status})
    except Exception as e:
        return _tool_error("jira_transition_issue_failed", 500, str(e))


@app.route(route="tool/jira/list_open_dispatch_issues", methods=["POST"])
def tool_jira_list_open_dispatch_issues(req: func.HttpRequest) -> func.HttpResponse:
    try:
        payload = req.get_json()
        project_key = (payload.get("project_key") or "").strip()
        epic_key = (payload.get("epic_key") or "").strip()

        if not project_key or not epic_key:
            return _tool_error("project_key and epic_key are required", 400)

        coordinator = CoordinatorAgent(get_foundry_client())
        headers = coordinator._jira_headers()
        jira_base_url = os.environ.get("JIRA_BASE_URL", "").rstrip("/")
        jql = (
            f'project = "{project_key}" '
            f'AND "Epic Link" = "{epic_key}" '
            'AND statusCategory != Done '
            'ORDER BY updated DESC'
        )

        response = requests.get(
            f"{jira_base_url}/rest/api/3/search/jql",
            headers=headers,
            params={"jql": jql, "maxResults": 50, "fields": "key,status,summary,issuetype"},
            timeout=30,
        )
        if response.status_code != 200:
            return _tool_error(
                "jira_list_open_dispatch_issues_failed",
                500,
                f"{response.status_code}: {response.text[:400]}",
            )

        data = response.json()
        issues = []
        for issue in data.get("issues", []):
            fields = issue.get("fields", {})
            issues.append(
                {
                    "key": issue.get("key"),
                    "summary": fields.get("summary"),
                    "status": (fields.get("status") or {}).get("name"),
                    "issue_type": (fields.get("issuetype") or {}).get("name"),
                }
            )

        return _tool_response({"ok": True, "epic_key": epic_key, "issues": issues})
    except Exception as e:
        return _tool_error("jira_list_open_dispatch_issues_failed", 500, str(e))


@app.route(route="tool/jira/create_dispatch_story", methods=["POST"])
def tool_jira_create_dispatch_story(req: func.HttpRequest) -> func.HttpResponse:
    try:
        payload = req.get_json()
        project_key = (payload.get("project_key") or "").strip()
        epic_key = (payload.get("epic_key") or "").strip()
        role = (payload.get("role") or "").strip()
        task = (payload.get("task") or "").strip()
        stage = (payload.get("stage") or "").strip()

        if not project_key or not epic_key or not role or not task:
            return _tool_error("project_key, epic_key, role, and task are required", 400)

        coordinator = CoordinatorAgent(get_foundry_client())
        headers = coordinator._jira_headers()
        jira_base_url = os.environ.get("JIRA_BASE_URL", "").rstrip("/")
        dispatch_issue_type = os.environ.get("ORCHESTRATOR_DISPATCH_ISSUE_TYPE", "Story").strip() or "Story"

        summary = f"[{role}] {task[:160]}"
        description_lines = [
            f"Dispatch task for role: {role}",
            f"Epic: {epic_key}",
            f"Stage: {stage or 'unspecified'}",
            "",
            task,
        ]

        # Format description in Atlassian Document Format (ADF) for Jira Cloud v3 API
        adf_content = []
        for line in description_lines:
            if line.strip():
                adf_content.append({
                    "type": "paragraph",
                    "content": [{"type": "text", "text": line}]
                })
        
        description_adf = {
            "version": 1,
            "type": "doc",
            "content": adf_content if adf_content else [{"type": "paragraph", "content": []}]
        }

        base_fields: Dict[str, Any] = {
            "project": {"key": project_key},
            "summary": summary,
            "description": description_adf,
            "issuetype": {"name": dispatch_issue_type},
            "labels": [
                "agent-dispatch",
                f"role-{role.lower().replace('_', '-').replace(' ', '-')}",
                f"epic-{epic_key.lower()}",
            ],
        }

        attempt_payloads: List[Dict[str, Any]] = []

        parent_fields = dict(base_fields)
        parent_fields["parent"] = {"key": epic_key}
        attempt_payloads.append({"fields": parent_fields, "link_mode": "parent"})

        epic_link_field_id = _resolve_epic_link_field_id(headers, jira_base_url)
        if epic_link_field_id:
            epic_link_fields = dict(base_fields)
            epic_link_fields[epic_link_field_id] = epic_key
            attempt_payloads.append({"fields": epic_link_fields, "link_mode": f"{epic_link_field_id}"})

        attempt_payloads.append({"fields": base_fields, "link_mode": "unlinked"})

        last_error = ""
        for attempt in attempt_payloads:
            response = requests.post(
                f"{jira_base_url}/rest/api/3/issue",
                headers=headers,
                json={"fields": attempt["fields"]},
                timeout=30,
            )
            if response.status_code in (200, 201):
                created = response.json()
                return _tool_response(
                    {
                        "ok": True,
                        "issue_key": created.get("key"),
                        "issue_id": created.get("id"),
                        "epic_key": epic_key,
                        "link_mode": attempt["link_mode"],
                    }
                )
            last_error = f"{response.status_code}: {response.text[:400]}"

        return _tool_error("jira_create_dispatch_story_failed", 500, last_error)
    except Exception as e:
        return _tool_error("jira_create_dispatch_story_failed", 500, str(e))


@app.route(route="tool/confluence/create_page", methods=["POST"])
def tool_confluence_create_page(req: func.HttpRequest) -> func.HttpResponse:
    try:
        payload = req.get_json()
        title = (payload.get("title") or "").strip()
        storage_html = (payload.get("storage_html") or "").strip()

        if not title or not storage_html:
            return _tool_error("title and storage_html are required", 400)

        coordinator = CoordinatorAgent(get_foundry_client())
        page_url = coordinator._create_confluence_page(title=title, storage_html=storage_html)
        return _tool_response({"ok": True, "url": page_url, "title": title})
    except Exception as e:
        return _tool_error("confluence_create_page_failed", 500, str(e))


@app.route(route="tool/runtime/execute_script", methods=["POST"])
def tool_runtime_execute_script(req: func.HttpRequest) -> func.HttpResponse:
    try:
        payload = req.get_json()
        action = (payload.get("action") or "").strip()
        epic_key = (payload.get("epic_key") or "").strip()

        if not action:
            return _tool_error("action is required", 400)

        result = _run_whitelisted_script(action=action, epic_key=epic_key)
        status_code = 200 if result.get("ok") else 500
        return _tool_response(result, status_code=status_code)
    except subprocess.TimeoutExpired:
        return _tool_error("runtime_execute_script_timeout", 500, "Script execution timed out")
    except Exception as e:
        return _tool_error("runtime_execute_script_failed", 500, str(e))


@app.route(route="tool/runtime/check_url", methods=["POST"])
def tool_runtime_check_url(req: func.HttpRequest) -> func.HttpResponse:
    try:
        payload = req.get_json()
        url = (payload.get("url") or "").strip()
        if not url:
            return _tool_error("url is required", 400)

        response = requests.get(url, timeout=30)
        return _tool_response(
            {
                "ok": response.status_code < 400,
                "url": url,
                "status_code": response.status_code,
                "response_excerpt": (response.text or "")[:1000],
                "checked_at": datetime.utcnow().isoformat(),
            }
        )
    except Exception as e:
        return _tool_error("runtime_check_url_failed", 500, str(e))


# Agent-core mode: orchestration intelligence lives in AI Foundry coordinator agent.
