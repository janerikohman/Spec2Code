"""
Epic Scheduler Function
Queries Jira every 5 minutes for pending epics and triggers orchestration via review-endpoint
"""
import os
import json
import logging
import socket
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple, Optional
import azure.functions as func

try:
    from jira import JIRA
    from jira.exceptions import JIRAError
except Exception:
    JIRA = None

    class JIRAError(Exception):
        pass

# Create the function app instance for Azure Functions v4
app = func.FunctionApp()

# ==================== CONFIGURATION ====================
JIRA_BASE_URL = os.getenv("JIRA_BASE_URL", "https://your-org.atlassian.net")
JIRA_EMAIL = os.getenv("JIRA_EMAIL", "")
JIRA_API_TOKEN = os.getenv("JIRA_API_TOKEN", "")
REVIEW_ENDPOINT_BASE_URL = os.getenv("REVIEW_ENDPOINT_BASE_URL", "")
REVIEW_ENDPOINT_API_KEY = os.getenv("REVIEW_ENDPOINT_API_KEY", "")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "KAN")

# ==================== LOGGING ====================
logger = logging.getLogger("epic-scheduler")

# ==================== CONSTANTS ====================
READY_STATES = [
    "To Do",
    "TO DO",
    "New",
    "Ready for Orchestration",
    "READY_FOR_ORCHESTRATION",
    "new",
    "ready",
]


# ==================== JIRA CLIENT ====================
def get_jira_client() -> Any:
    """
    Create authenticated Jira client
    
    Returns:
        JIRA: Authenticated Jira client instance
        
    Raises:
        ValueError: If credentials are not configured
    """
    if not JIRA_EMAIL or not JIRA_API_TOKEN:
        raise ValueError("JIRA_EMAIL and JIRA_API_TOKEN must be configured")

    if JIRA is None:
        logger.warning("jira dependency is not available in runtime, using Jira REST fallback")
        return None
    
    return JIRA(
        server=JIRA_BASE_URL,
        basic_auth=(JIRA_EMAIL, JIRA_API_TOKEN),
        options={"agile_rest_path": "agile/1.0"}
    )


def _jira_auth_headers() -> Dict[str, str]:
    """Build Basic Auth headers for Jira REST API fallback."""
    import base64

    token = base64.b64encode(f"{JIRA_EMAIL}:{JIRA_API_TOKEN}".encode()).decode()
    return {
        "Authorization": f"Basic {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _http_json_request(
    method: str,
    url: str,
    headers: Dict[str, str],
    timeout: int = 30,
    params: Optional[Dict[str, Any]] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Tuple[int, Dict[str, Any], str]:
    """Perform HTTP request using stdlib and return (status, json_body, raw_body)."""
    if params:
        query = urllib.parse.urlencode(params)
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{query}"

    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=data, headers=headers, method=method)

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.getcode()
            raw_body = response.read().decode("utf-8")
            json_body = json.loads(raw_body) if raw_body else {}
            return status, json_body, raw_body
    except urllib.error.HTTPError as exc:
        raw_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {raw_body}") from exc
    except (urllib.error.URLError, socket.timeout) as exc:
        raise RuntimeError(str(exc)) from exc


# ==================== JIRA QUERIES ====================
def query_pending_epics(jira_client: Any) -> List[str]:
    """
    Query Jira for epics in ready states
    
    Args:
        jira_client: Authenticated Jira client
        
    Returns:
        List of epic keys (e.g., ["KAN-133", "KAN-134"])
    """
    jql = (
        f"project = {JIRA_PROJECT_KEY} AND issuetype = Epic "
        f"AND status IN ({', '.join(f'{chr(34)}{s}{chr(34)}' for s in READY_STATES)}) "
        f"ORDER BY created DESC"
    )

    try:
        if jira_client is None:
            _, body, _ = _http_json_request(
                "GET",
                f"{JIRA_BASE_URL}/rest/api/3/search/jql",
                headers=_jira_auth_headers(),
                params={"jql": jql, "maxResults": 100, "fields": "key"},
                timeout=30,
            )
            issues = body.get("issues", [])
            epic_keys = [issue.get("key") for issue in issues if issue.get("key")]
            logger.info(f"Found {len(epic_keys)} pending epics via REST: {epic_keys}")
            return epic_keys

        issues = jira_client.search_issues(jql, maxResults=100)
        epic_keys = [issue.key for issue in issues]
        logger.info(f"Found {len(epic_keys)} pending epics: {epic_keys}")
        return epic_keys
    except JIRAError as e:
        logger.error(f"Failed to query Jira for pending epics: {e}")
        raise



# ==================== ORCHESTRATION TRIGGER ====================
def trigger_orchestration(epic_key: str) -> Tuple[bool, str]:
    """
    Trigger orchestration for epic via review-endpoint
    
    Args:
        epic_key: Epic key (e.g., "KAN-133")
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    if not REVIEW_ENDPOINT_BASE_URL or not REVIEW_ENDPOINT_API_KEY:
        logger.error("REVIEW_ENDPOINT_BASE_URL or REVIEW_ENDPOINT_API_KEY not configured")
        return False, "Endpoint not configured"
    
    # Prepare auth header (Function key)
    headers = {
        "x-functions-key": REVIEW_ENDPOINT_API_KEY,
        "Content-Type": "application/json"
    }
    
    payload = {
        "epic_key": epic_key,
        "epic_keys": [epic_key],
        "triggered_by": "epic-scheduler",
        "timestamp": datetime.utcnow().isoformat()
    }
    
    endpoint_url = f"{REVIEW_ENDPOINT_BASE_URL}/execute_orchestrator_cycle"
    
    try:
        status_code, _, raw_body = _http_json_request(
            "POST",
            endpoint_url,
            headers=headers,
            payload=payload,
            timeout=30
        )
        
        if status_code in [200, 202]:
            logger.info(f"Successfully triggered orchestration for {epic_key}")
            return True, f"Status {status_code}"
        else:
            error_msg = f"Status {status_code}: {raw_body}"
            logger.error(f"Failed to trigger orchestration for {epic_key}: {error_msg}")
            return False, error_msg

    except Exception as e:
        logger.error(f"Failed to trigger orchestration for {epic_key}: {e}")
        return False, str(e)


# ==================== SCHEDULER CYCLE ====================
def run_scheduler_cycle() -> Dict[str, int]:
    """
    Execute one scheduler cycle:
    1. Query Jira for pending epics
    2. Trigger orchestration (Foundry agents handle comments/state)
    
    Returns:
        Dict with results:
        {
            "total_checked": int,
            "triggered": int,
            "errors": int
        }
    """
    results = {
        "total_checked": 0,
        "triggered": 0,
        "errors": 0
    }
    
    try:
        jira_client = get_jira_client()
        pending_epics = query_pending_epics(jira_client)
        results["total_checked"] = len(pending_epics)
        
        for epic_key in pending_epics:
            try:
                # Trigger orchestration - Foundry agents handle everything else
                success, message = trigger_orchestration(epic_key)
                if success:
                    results["triggered"] += 1
                    logger.info(f"Triggered orchestration for {epic_key}")
                else:
                    logger.error(f"Failed to trigger orchestration for {epic_key}: {message}")
                    results["errors"] += 1
                    
            except Exception as e:
                logger.error(f"Error processing epic {epic_key}: {e}")
                results["errors"] += 1
        
        return results
        
    except Exception as e:
        logger.error(f"Fatal error in scheduler cycle: {e}")
        results["errors"] = results["total_checked"]
        return results


# ==================== AZURE FUNCTION ====================
@app.function_name(name="epic_scheduler")
@app.schedule(schedule="0 */5 * * * *", arg_name="mytimer", run_on_startup=False, use_monitor=True)
def epic_scheduler(mytimer: func.TimerRequest) -> None:
    """
    Azure Function timer trigger - runs every 5 minutes
    Queries Jira for pending epics and triggers orchestration
    
    Args:
        mytimer: Timer trigger context
    """
    utc_timestamp = datetime.utcnow().replace(microsecond=0).isoformat()
    
    if mytimer.past_due:
        logger.warning(f"Timer trigger at {utc_timestamp} is past due!")
    
    logger.info(f"Epic scheduler started at {utc_timestamp}")
    
    try:
        results = run_scheduler_cycle()
        logger.info(
            f"Scheduler cycle complete: "
            f"checked={results['total_checked']}, "
            f"triggered={results['triggered']}, "
            f"errors={results['errors']}"
        )
    except Exception as e:
        logger.error(f"Fatal error in scheduler: {e}")
        raise
