"""
Epic Scheduler Function
Queries Jira every 5 minutes for pending epics and triggers orchestration via review-endpoint
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Tuple, Optional
import azure.functions as func

try:
    import requests
except Exception:
    requests = None

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
RECENT_ORCHESTRATION_WINDOW_HOURS = 1


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


# ==================== JIRA QUERIES ====================
def query_pending_epics(jira_client: Any) -> List[str]:
    """
    Query Jira for epics in ready states
    
    Args:
        jira_client: Authenticated Jira client
        
    Returns:
        List of epic keys (e.g., ["KAN-133", "KAN-134"])
    """
    jql = f"""
        project = {JIRA_PROJECT_KEY} 
        AND type = Epic 
        AND status IN ({', '.join(f'"{s}"' for s in READY_STATES)})
        ORDER BY created DESC
    """
    
    try:
        if jira_client is None:
            if requests is None:
                raise RuntimeError("requests dependency is not available in the function runtime")

            response = requests.get(
                f"{JIRA_BASE_URL}/rest/api/3/search",
                headers=_jira_auth_headers(),
                params={"jql": jql, "maxResults": 100, "fields": "key"},
                timeout=30,
            )
            response.raise_for_status()
            issues = response.json().get("issues", [])
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


def get_recent_orchestration_comment(
    jira_client: Any,
    epic_key: str, 
    window_hours: int = RECENT_ORCHESTRATION_WINDOW_HOURS
) -> Optional[str]:
    """
    Check if epic has recent orchestration trigger comment
    
    Args:
        jira_client: Authenticated Jira client
        epic_key: Epic key (e.g., "KAN-133")
        window_hours: Look back window in hours (default 1)
        
    Returns:
        Comment ID if found, None otherwise
    """
    try:
        if jira_client is None:
            if requests is None:
                return None

            response = requests.get(
                f"{JIRA_BASE_URL}/rest/api/3/issue/{epic_key}/comment",
                headers=_jira_auth_headers(),
                timeout=30,
            )
            response.raise_for_status()
            comments = response.json().get("comments", [])
            cutoff_time = datetime.utcnow() - timedelta(hours=window_hours)

            for comment in comments:
                comment_created_raw = comment.get("created", "")
                if not comment_created_raw:
                    continue
                comment_created = datetime.fromisoformat(comment_created_raw.replace('Z', '+00:00')).replace(tzinfo=None)
                if comment_created <= cutoff_time:
                    continue

                body = comment.get("body")
                if isinstance(body, str):
                    text = body
                else:
                    parts: List[str] = []
                    for block in body.get("content", []) if isinstance(body, dict) else []:
                        for node in block.get("content", []):
                            if isinstance(node, dict) and "text" in node:
                                parts.append(node["text"])
                    text = " ".join(parts)

                if "Orchestration triggered" in text or "ORCHESTRATION_TRIGGERED" in text:
                    comment_id = str(comment.get("id", ""))
                    logger.info(f"Found recent orchestration comment on {epic_key} via REST")
                    return comment_id or None

            return None

        issue = jira_client.issue(epic_key, expand="changelog")
        cutoff_time = datetime.utcnow() - timedelta(hours=window_hours)
        
        # Check comments for orchestration trigger marker
        for comment in issue.fields.comment.comments:
            comment_created = datetime.fromisoformat(
                comment.created.replace('Z', '+00:00')
            )
            if comment_created > cutoff_time:
                if "Orchestration triggered" in comment.body or "ORCHESTRATION_TRIGGERED" in comment.body:
                    logger.info(f"Found recent orchestration comment on {epic_key}")
                    return comment.id
        
        return None
    except JIRAError as e:
        logger.warning(f"Failed to get comments for {epic_key}: {e}")
        return None
    except Exception as e:
        logger.warning(f"Failed to get comments for {epic_key} via REST: {e}")
        return None


def add_orchestration_comment(jira_client: Any, epic_key: str, comment: str) -> None:
    """Add scheduler marker comment using jira SDK or REST fallback."""
    if jira_client is not None:
        jira_client.add_comment(epic_key, comment)
        return

    if requests is None:
        raise RuntimeError("requests dependency is not available in the function runtime")

    payload = {"body": comment}
    response = requests.post(
        f"{JIRA_BASE_URL}/rest/api/2/issue/{epic_key}/comment",
        headers=_jira_auth_headers(),
        json=payload,
        timeout=30,
    )
    response.raise_for_status()


# ==================== ORCHESTRATION TRIGGER ====================
def trigger_orchestration(epic_key: str) -> Tuple[bool, str]:
    """
    Trigger orchestration for epic via review-endpoint
    
    Args:
        epic_key: Epic key (e.g., "KAN-133")
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    if requests is None:
        logger.error("requests dependency is not available in the function runtime")
        return False, "Missing requests dependency"

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
        response = requests.post(
            endpoint_url,
            json=payload,
            headers=headers,
            timeout=30
        )
        
        if response.status_code in [200, 202]:
            logger.info(f"Successfully triggered orchestration for {epic_key}")
            return True, f"Status {response.status_code}"
        else:
            error_msg = f"Status {response.status_code}: {response.text}"
            logger.error(f"Failed to trigger orchestration for {epic_key}: {error_msg}")
            return False, error_msg
            
    except requests.exceptions.Timeout:
        logger.error(f"Timeout triggering orchestration for {epic_key}")
        return False, "Timeout"
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to trigger orchestration for {epic_key}: {e}")
        return False, str(e)


# ==================== SCHEDULER CYCLE ====================
def run_scheduler_cycle() -> Dict[str, int]:
    """
    Execute one scheduler cycle:
    1. Query Jira for pending epics
    2. Check for recent orchestration (deduplicate)
    3. Trigger orchestration for new epics
    
    Returns:
        Dict with results:
        {
            "total_checked": int,
            "triggered": int,
            "skipped_recent": int,
            "errors": int
        }
    """
    results = {
        "total_checked": 0,
        "triggered": 0,
        "skipped_recent": 0,
        "errors": 0
    }
    
    try:
        jira_client = get_jira_client()
        pending_epics = query_pending_epics(jira_client)
        results["total_checked"] = len(pending_epics)
        
        for epic_key in pending_epics:
            try:
                # Check for recent orchestration
                recent_comment = get_recent_orchestration_comment(jira_client, epic_key)
                if recent_comment:
                    logger.info(f"Skipping {epic_key}: recent orchestration found")
                    results["skipped_recent"] += 1
                    continue
                
                # Trigger orchestration
                success, message = trigger_orchestration(epic_key)
                if success:
                    # Add comment to Jira to mark orchestration triggered
                    try:
                        add_orchestration_comment(
                            jira_client,
                            epic_key,
                            f"[AUTOMATED] Orchestration triggered by epic-scheduler at {datetime.utcnow().isoformat()}Z"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to add comment to {epic_key}: {e}")
                    
                    results["triggered"] += 1
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
            f"skipped={results['skipped_recent']}, "
            f"errors={results['errors']}"
        )
    except Exception as e:
        logger.error(f"Fatal error in scheduler: {e}")
        raise
