"""
Minimal Azure Function App - 100% Agentic Architecture

This function is ONLY a webhook receiver and delegator.
All orchestration logic lives in the Coordinator Agent (running in AI Foundry).

Version: 2.0 (100% Agentic - No Legacy Function Orchestration)
"""

import json
import os
import logging
import importlib
import sys
import subprocess
from datetime import datetime
from typing import Any

import azure.functions as func
from coordinator_agent import CoordinatorAgent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Spec2Code")

try:
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential
except Exception:
    AIProjectClient = None
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
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

foundry_client = None
sdk_bootstrap_error = ""
foundry_client_init_error = ""
foundry_endpoint_source = "UNSET"


def ensure_foundry_sdk_available() -> bool:
    global AIProjectClient
    global DefaultAzureCredential
    global sdk_bootstrap_error

    sdk_bootstrap_error = ""

    if AIProjectClient is not None and DefaultAzureCredential is not None:
        return True

    runtime_site_packages = "/tmp/spec2code_site_packages"
    if runtime_site_packages not in sys.path:
        sys.path.insert(0, runtime_site_packages)

    try:
        ai_projects_module = importlib.import_module("azure.ai.projects")
        identity_module = importlib.import_module("azure.identity")
        AIProjectClient = getattr(ai_projects_module, "AIProjectClient", None)
        DefaultAzureCredential = getattr(identity_module, "DefaultAzureCredential", None)
        if AIProjectClient is not None and DefaultAzureCredential is not None:
            logger.info("✅ Foundry SDK loaded from runtime site-packages")
            return True
    except Exception as import_error:
        sdk_bootstrap_error = f"import_error: {type(import_error).__name__}: {import_error}"
        pass

    logger.warning("⚠️ Foundry SDK not available; attempting runtime install")
    try:
        importlib.invalidate_caches()
        for module_name in list(sys.modules.keys()):
            if module_name == "azure" or module_name.startswith("azure."):
                del sys.modules[module_name]

        subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--no-cache-dir",
                "--target",
                runtime_site_packages,
                "azure-ai-projects==2.0.0",
                "azure-identity>=1.15.0",
                "azure-core>=1.37.0",
                "openai>=1.40.0",
            ],
            check=True,
            timeout=300,
            capture_output=True,
            text=True,
        )

        importlib.invalidate_caches()
        ai_projects_module = importlib.import_module("azure.ai.projects")
        identity_module = importlib.import_module("azure.identity")
        AIProjectClient = getattr(ai_projects_module, "AIProjectClient", None)
        DefaultAzureCredential = getattr(identity_module, "DefaultAzureCredential", None)

        if AIProjectClient is not None and DefaultAzureCredential is not None:
            logger.info("✅ Foundry SDK installed and loaded at runtime")
            return True

        logger.error("❌ Runtime install completed but SDK still unavailable")
        return False
    except Exception as install_error:
        sdk_bootstrap_error = f"install_error: {type(install_error).__name__}: {install_error}"
        logger.error(f"❌ Runtime SDK install failed: {type(install_error).__name__}: {install_error}")
        return False


def get_foundry_client() -> Any:
    global foundry_client
    global foundry_client_init_error
    global foundry_endpoint_source
    if foundry_client is not None:
        return foundry_client

    foundry_client_init_error = ""

    if not ensure_foundry_sdk_available():
        logger.error("❌ Unable to load Azure AI Projects SDK")
        foundry_client_init_error = sdk_bootstrap_error or "sdk_bootstrap_failed"
        return None

    if AIProjectClient is None or DefaultAzureCredential is None:
        logger.error("❌ Azure AI Projects SDK not available")
        foundry_client_init_error = "azure_ai_projects_sdk_unavailable"
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
        foundry_client = AIProjectClient(
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
        "ai_projects_available": AIProjectClient is not None,
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
            if AIProjectClient and DefaultAzureCredential and resolved_endpoint:
                test_cred = DefaultAzureCredential()
                test_client = AIProjectClient(
                    endpoint=resolved_endpoint,
                    credential=test_cred
                )
                info["initialization_test"] = "SUCCESS"
        except Exception as e:
            info["initialization_test"] = "FAILED"
            info["initialization_error"] = f"{type(e).__name__}: {str(e)}"
    
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


# Agent-core mode: orchestration intelligence lives in AI Foundry coordinator agent.
