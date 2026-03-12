"""Agent-core coordinator with specialist execution loop.

Rules enforced:
- Coordinator agent is the only orchestration decision-maker.
- Specialist agents execute real work (code, infra deployment, testing).
- Minimal context passing: Foundry 256KB message limit requires lean payloads.
- Agents fetch detailed context from Jira using tools, not via message payload.
"""

import base64
import json
import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

import requests

from foundry_agents import FoundryAgentManager
from keyvault_secrets import jira_email, jira_api_token  # RULE_15 / RULE_16

logger = logging.getLogger("CoordinatorAgent")

# Non-secret configuration
JIRA_BASE_URL = os.environ.get("JIRA_BASE_URL", "")
CONFLUENCE_BASE_URL = os.environ.get("CONFLUENCE_BASE_URL", "")
CONFLUENCE_SPACE_KEY = os.environ.get("CONFLUENCE_SPACE_KEY", "")
JIRA_EMAIL_ENV = os.environ.get("JIRA_EMAIL", "")
JIRA_API_TOKEN_ENV = os.environ.get("JIRA_API_TOKEN", "")
COORDINATOR_TIMEOUT_SECONDS = int(os.environ.get("COORDINATOR_TIMEOUT_SECONDS", "120"))
SPECIALIST_TIMEOUT_SECONDS = int(os.environ.get("SPECIALIST_TIMEOUT_SECONDS", "45"))
SPECIALIST_MAX_ATTEMPTS = int(os.environ.get("SPECIALIST_MAX_ATTEMPTS", "1"))
ORCHESTRATION_RUNTIME_BUDGET_SECONDS = int(os.environ.get("ORCHESTRATION_RUNTIME_BUDGET_SECONDS", "170"))


def _usable_secret_value(value: str) -> str:
    candidate = (value or "").strip()
    if not candidate:
        return ""
    if candidate.startswith("@Microsoft.KeyVault("):
        return ""
    return candidate


class CoordinatorAgent:
    """Execution shell that delegates orchestration to coordinator Foundry agent."""

    def __init__(self, foundry_client: Any):
        self.client = foundry_client
        self.orchestration_id = str(uuid4())
        self.agent_manager = FoundryAgentManager(foundry_client)
        logger.info(f"Coordinator shell initialized: {self.orchestration_id}")

    async def orchestrate_epic(self, epic_key: str) -> Dict[str, Any]:
        logger.info(f"Starting agent-core orchestration for {epic_key}")

        try:
            discovered_agents = await self.agent_manager.discover_agents()
            if not discovered_agents:
                raise RuntimeError("No agents discovered in AI Foundry")
            if "coordinator" not in discovered_agents:
                raise RuntimeError("No coordinator agent discovered")

            # CRITICAL: Reduce Jira context to minimal fields only.
            # Do NOT pass full issue with comments/attachments.
            # Specialists will fetch full context via tools.
            jira_context = self._get_jira_issue_context(epic_key)

            coordinator_instruction = self._build_coordinator_instruction(epic_key)
            coordinator_output = await self.agent_manager.invoke_agent(
                agent_role="coordinator",
                instruction=coordinator_instruction,
                context={
                    "epic_key": epic_key,
                    "jira_context": jira_context,
                    "discovered_agents": discovered_agents,
                    "orchestration_id": self.orchestration_id,
                    "timestamp": datetime.utcnow().isoformat(),
                },
                timeout_seconds=COORDINATOR_TIMEOUT_SECONDS,
            )

            delivery_package = coordinator_output.get("delivery_package")
            if not isinstance(delivery_package, dict):
                logger.info(
                    "Coordinator did not return delivery_package dict; "
                    "building minimal package from coordinator output."
                )
                delivery_package = {
                    "raw_response": coordinator_output.get("raw_response", ""),
                    "coordinator_outcome": coordinator_output.get("outcome", "completed"),
                }

            delivery_package.setdefault("epic_key", epic_key)
            delivery_package.setdefault("orchestration_id", self.orchestration_id)
            delivery_package.setdefault("generated_at", datetime.utcnow().isoformat())
            delivery_package.setdefault("status", "BLOCKED")
            delivery_package.setdefault("specification", {})
            delivery_package.setdefault("gates_verified", {})
            delivery_package.setdefault("all_gates_passed", False)
            delivery_package.setdefault(
                "execution_summary",
                {
                    "total_agents_invoked": len(discovered_agents),
                    "agents": list(discovered_agents.keys()),
                    "execution_trace_length": 1,
                    "execution_time_minutes": 0,
                    "specialist_execution": {},
                },
            )

            # RUN SPECIALIST EXECUTION LOOP
            # Invoke all specialist roles (po, architect, developer, etc.) to perform real work.
            # Pass MINIMAL context (epic_key + role only) to stay under 256KB Foundry limit.
            specialist_execution = await self._run_specialist_execution_loop(
                epic_key=epic_key,
                discovered_agents=discovered_agents,
                coordinator_output=coordinator_output,
                delivery_package=delivery_package,
            )
            delivery_package["execution_summary"]["specialist_execution"] = specialist_execution

            await self._store_orchestration_results(epic_key, delivery_package, coordinator_output)

            if delivery_package.get("all_gates_passed") is True:
                await self._transition_epic(epic_key, "READY_FOR_DELIVERY")

            return {
                "orchestration_id": self.orchestration_id,
                "epic_key": epic_key,
                "status": "COMPLETED",
                "delivery_package": delivery_package,
                "coordinator_output": coordinator_output,
                "execution_trace": [
                    {
                        "timestamp": datetime.utcnow().isoformat(),
                        "step": "coordinator_and_specialists_completed",
                        "confidence": coordinator_output.get("confidence", 0.0),
                        "outcome": coordinator_output.get("outcome", "unknown"),
                        "specialist_count": specialist_execution.get("completed", 0),
                    }
                ],
                "timestamp": datetime.utcnow().isoformat(),
            }

        except Exception as orchestration_error:
            logger.error(f"Orchestration failed: {orchestration_error}", exc_info=True)
            self._safe_add_jira_comment(
                epic_key,
                f"h3. ❌ Agent-Core Orchestration Failed\n\n"
                f"*Orchestration ID:* {self.orchestration_id}\n"
                f"*Error:* {orchestration_error}\n"
                f"*Timestamp:* {datetime.utcnow().isoformat()}",
            )
            return {
                "orchestration_id": self.orchestration_id,
                "epic_key": epic_key,
                "status": "FAILED",
                "error": str(orchestration_error),
                "execution_trace": [],
                "timestamp": datetime.utcnow().isoformat(),
            }

    def _build_coordinator_instruction(self, epic_key: str) -> str:
        return f"""
Execute full agent-core orchestration for epic {epic_key}.
Analyze the Epic requirements and coordinate specialist agents to execute the work.
Return structured delivery_package with specification containing specialist outputs.
"""

    async def _run_specialist_execution_loop(
        self,
        epic_key: str,
        discovered_agents: Dict[str, str],
        coordinator_output: Dict[str, Any],
        delivery_package: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Invoke all specialist roles to perform real work for the epic.
        Pass ONLY minimal context (epic_key, role, orchestration_id) to stay under 256KB.
        Specialists fetch full context from Jira using Jira_GetIssue tool.
        """
        specification = delivery_package.get("specification", {})
        if not isinstance(specification, dict):
            specification = {}
            delivery_package["specification"] = specification

        roles = ["po", "architect", "security", "devops", "developer", "qa", "finops", "release"]
        loop_started_at = time.monotonic()
        summary: Dict[str, Any] = {
            "planned": roles,
            "invoked": 0,
            "completed": 0,
            "failed": 0,
            "deferred": 0,
            "failed_roles": [],
            "deferred_roles": [],
            "details": [],
        }

        for role in roles:
            elapsed = int(time.monotonic() - loop_started_at)
            if elapsed >= ORCHESTRATION_RUNTIME_BUDGET_SECONDS:
                summary["deferred"] += 1
                summary["deferred_roles"].append(role)
                summary["details"].append(
                    {
                        "role": role,
                        "status": "deferred",
                        "reason": "runtime_budget_exceeded",
                        "elapsed_seconds": elapsed,
                    }
                )
                specification[role] = {
                    "role": role,
                    "outcome": "needs_input",
                    "blocked_reasons": ["deferred_due_to_runtime_budget"],
                    "evidence_links": [],
                    "tool_actions": [],
                }
                continue

            if role not in discovered_agents:
                summary["details"].append(
                    {"role": role, "status": "skipped", "reason": "agent_not_discovered"}
                )
                continue

            summary["invoked"] += 1
            role_success = False
            last_error = ""

            for attempt in range(1, SPECIALIST_MAX_ATTEMPTS + 1):
                try:
                    instruction = self._build_specialist_instruction(role, epic_key)
                    # CRITICAL: Minimal context only (epic_key, role, orchestration_id)
                    # Do NOT pass coordinator_output or delivery_package.
                    # Agents MUST read Epic details from Jira using Jira_GetIssue tool.
                    output = await self.agent_manager.invoke_agent(
                        agent_role=role,
                        instruction=instruction,
                        context={
                            "epic_key": epic_key,
                            "role": role,
                            "orchestration_id": self.orchestration_id,
                            "attempt": attempt,
                        },
                        timeout_seconds=SPECIALIST_TIMEOUT_SECONDS,
                    )
                    
                    normalized = self._normalize_specialist_output(role, output, attempt)
                    specification[role] = normalized
                    outcome = str(normalized.get("outcome", "completed")).strip().lower()
                    
                    if outcome in {"blocked", "needs_input", "failed"}:
                        last_error = f"role returned outcome={outcome}"
                        continue

                    summary["completed"] += 1
                    summary["details"].append(
                        {
                            "role": role,
                            "status": "completed",
                            "attempt": attempt,
                            "outcome": outcome,
                            "evidence_links": len(normalized.get("evidence_links", [])),
                            "tool_actions": len(normalized.get("tool_actions", [])),
                        }
                    )
                    role_success = True
                    break
                    
                except Exception as role_error:
                    last_error = f"{type(role_error).__name__}: {str(role_error)[:1000]}"
                    logger.warning(f"Specialist {role} attempt {attempt} failed: {last_error}")

            if not role_success:
                summary["failed"] += 1
                summary["failed_roles"].append(role)
                specification[role] = {
                    "role": role,
                    "outcome": "blocked",
                    "blocked_reasons": [last_error or "specialist_execution_failed"],
                    "evidence_links": [],
                    "tool_actions": [],
                }
                summary["details"].append(
                    {
                        "role": role,
                        "status": "failed",
                        "error": last_error or "specialist_execution_failed",
                    }
                )

        return summary

    def _build_specialist_instruction(self, role: str, epic_key: str) -> str:
        """Generate role-specific instruction with concrete fallback behaviors."""
        
        base = f"""
Execute your specialist {role} role for epic {epic_key}.

CRITICAL RULES:
- NEVER return outcome=needs_input (not allowed)
- Always return outcome=completed or outcome=blocked
- Use reasonable defaults when requirements are ambiguous
- Document assumptions you make

CONTEXT SETUP:
You will receive MINIMAL invocation context (epic_key, role, orchestration_id only).
This is required for Foundry to stay under 256KB message limits.

CRITICAL FIRST ACTION:
1. Call [Jira_GetIssue] with issue_key={epic_key} to fetch full Epic details
2. Read Epic description, acceptance criteria, linked issues
3. Understand all requirements for your role from the Epic

DECISION TREE FOR MISSING INFO:
- If requirements unclear: Use Epic summary to infer intent
- If acceptance criteria missing: Define reasonable defaults
- If constraints not specified: Use industry best practices
- If timeline not clear: Assume 1-sprint capability

YOUR RESPONSIBILITIES:
- Perform real, tool-backed work for your role
- Execute actual actions (code, infra, tests, designs, etc.)
- Return strict JSON with tool_actions and evidence_links
- Document assumptions made for missing information
- NEVER ask for input; proceed with best-effort

OUTPUT FORMAT (MANDATORY):
{{
  "outcome": "completed",
  "confidence": 0.0-1.0,
  "tool_actions": [executed or planned actions],
  "evidence_links": [artifact/resource/document links],
  "assumptions_made": [assumptions for missing info],
  "summary": "what was accomplished"
}}

Or if hard blocker:
{{
  "outcome": "blocked",
  "confidence": 0.0-1.0,
  "blocked_reasons": ["exact error or reason"],
  "tool_actions": [],
  "evidence_links": [],
  "summary": "why blocked"
}}
"""

        if role == "po":
            return base + """
PO-SPECIFIC GUIDANCE:
- Validate requirements from Epic description and linked issues
- Define acceptance criteria from Epic scope
- Create/update requirements document (structure: overview, AC, constraints)
- DEFAULT AC if not specified: "Epic works as described with no critical bugs"
- Link requirements document or Epic itself as evidence_links
- ALWAYS outcome=completed with requirements finalized
- tool_actions: ["validated_requirements", "defined_acceptance_criteria"]
"""
        elif role == "architect":
            return base + """
ARCHITECT-SPECIFIC GUIDANCE:
- Design system architecture based on requirements
- Propose technology stack (backend, frontend, infrastructure)
- Create architecture diagram or design document
- DEFAULT: Clean/layered architecture (UI → API → Business → Data layers)
- DEFAULT stack: React (frontend), Node.js (backend), PostgreSQL (DB), Azure (infra)
- DEFAULT: document design in Confluence or as markdown
- Include security, scalability, and maintainability considerations
- ALWAYS outcome=completed with design document link
- tool_actions: ["designed_architecture", "selected_technology_stack"]
"""
        elif role == "security":
            return base + """
SECURITY-SPECIFIC GUIDANCE:
- Review architecture for security risks
- Define authentication/authorization approach
- Document security requirements and threat model
- DEFAULT auth: OAuth2 for user apps, API keys for service-to-service
- DEFAULT access control: Role-based access control (RBAC)
- DEFAULT encryption: TLS/HTTPS in transit, encrypted at rest
- DEFAULT practices: Input validation, parameterized queries, secrets in Key Vault
- ALWAYS outcome=completed with security review document
- tool_actions: ["reviewed_architecture", "defined_security_controls"]
"""
        elif role == "devops":
            return base + """
DEVOPS-SPECIFIC GUIDANCE:
- Define infrastructure as code (Bicep or Terraform)
- Design CI/CD pipeline (build → test → deploy stages)
- Plan deployment strategy and monitoring
- DEFAULT infra: Azure resources (App Service/Container Apps, SQL DB, Container Registry, Key Vault)
- DEFAULT CI/CD: GitHub Actions or Azure Pipelines
- DEFAULT strategy: Staged deployments (dev → staging → prod)
- DEFAULT monitoring: Application Insights + Azure Monitor
- ALWAYS outcome=completed with IaC templates and pipeline config links
- tool_actions: ["defined_infrastructure", "designed_cicd_pipeline"]
"""
        elif role == "developer":
            return base + """
DEVELOPER-SPECIFIC GUIDANCE:
- Create initial project structure and codebase
- Implement features based on architecture and requirements
- Write unit tests and integration tests
- DEFAULT: Follow SOLID principles and clean code practices
- DEFAULT: 80%+ code coverage target
- DEFAULT: Modular structure with separation of concerns
- Include README, setup instructions, and development guide
- ALWAYS outcome=completed with code repository link and test summary
- tool_actions: ["created_project_structure", "implemented_features", "wrote_tests"]
"""
        elif role == "qa":
            return base + """
QA-SPECIFIC GUIDANCE:
- Define test strategy covering happy path, edge cases, error handling
- Create test cases or test automation
- Generate quality report with coverage metrics
- DEFAULT: Manual smoke testing + automated unit/integration tests
- DEFAULT: Test matrix covering browsers/devices if applicable
- DEFAULT: Quality gate = 80%+ coverage + 0 critical bugs
- ALWAYS outcome=completed with test report link
- tool_actions: ["created_test_plan", "executed_tests", "generated_quality_report"]
"""
        elif role == "finops":
            return base + """
FINOPS-SPECIFIC GUIDANCE:
- Estimate infrastructure costs using Azure pricing
- Propose cost optimization strategies
- Create cost breakdown by component (compute, storage, networking, services)
- DEFAULT: Calculate monthly cost for small/medium/large deployments
- DEFAULT optimizations: Reserved instances, auto-scaling, right-sizing, committed discounts
- DEFAULT report structure: Cost summary, breakdown, optimization recommendations
- ALWAYS outcome=completed with cost analysis document link
- tool_actions: ["estimated_infrastructure_costs", "proposed_optimizations"]
"""
        elif role == "release":
            return base + """
RELEASE-SPECIFIC GUIDANCE:
- Create release plan and deployment runbook
- Define rollback procedures
- Plan monitoring, alerting, and health checks
- DEFAULT strategy: Blue-green or canary deployments
- DEFAULT: 10% → 50% → 100% gradual rollout if canary
- DEFAULT: Automated health checks post-deployment
- DEFAULT: Rollback = revert to previous version + monitoring recovery
- ALWAYS outcome=completed with release plan and runbook links
- tool_actions: ["created_release_plan", "defined_rollback_strategy"]
"""
        else:
            return base + f"""
FALLBACK GUIDANCE FOR {role}:
- Execute the core responsibilities of your role
- Create necessary artifacts and documents
- ALWAYS outcome=completed with evidence links
"""

    def _normalize_specialist_output(self, role: str, output: Dict[str, Any], attempt: int) -> Dict[str, Any]:
        """Normalize specialist agent output to consistent format."""
        normalized: Dict[str, Any] = {
            "role": role,
            "outcome": output.get("outcome", "completed") if isinstance(output, dict) else "completed",
            "confidence": output.get("confidence", 0.75) if isinstance(output, dict) else 0.75,
            "attempt": attempt,
        }
        
        if isinstance(output, dict):
            for key, value in output.items():
                if key not in normalized:
                    normalized[key] = value

        evidence_links = normalized.get("evidence_links", [])
        normalized["evidence_links"] = evidence_links if isinstance(evidence_links, list) else []

        tool_actions = normalized.get("tool_actions", [])
        normalized["tool_actions"] = tool_actions if isinstance(tool_actions, list) else []
        
        return normalized

    def _get_jira_issue_context(self, epic_key: str) -> Dict[str, Any]:
        """
        Fetch MINIMAL Epic context for coordinator invocation.
        Do NOT fetch full issue with comments/attachments.
        Specialists will fetch details via Jira_GetIssue tool.
        """
        headers = self._jira_headers()
        # Fetch only essential fields to minimize payload
        fields = "key,summary,description,status,issuetype,created,updated"
        response = requests.get(
            f"{JIRA_BASE_URL}/rest/api/2/issue/{epic_key}?fields={fields}",
            headers=headers,
            timeout=30,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Jira API error: {response.status_code} - {response.text[:400]}")
        
        issue = response.json()
        # Return only minimal fields
        return {
            "key": issue.get("key"),
            "summary": issue.get("fields", {}).get("summary"),
            "description": issue.get("fields", {}).get("description", "")[:500],  # Cap at 500 chars
            "status": issue.get("fields", {}).get("status", {}).get("name", "unknown"),
            "issuetype": issue.get("fields", {}).get("issuetype", {}).get("name", "unknown"),
        }

    async def _store_orchestration_results(
        self,
        epic_key: str,
        delivery_package: Dict[str, Any],
        coordinator_output: Dict[str, Any],
    ) -> None:
        """Store orchestration results in Jira and Confluence."""
        jira_comment = self._build_jira_comment(delivery_package, coordinator_output)
        self._add_jira_comment(epic_key, jira_comment)

    def _build_jira_comment(self, delivery_package: Dict[str, Any], coordinator_output: Dict[str, Any]) -> str:
        """Build Jira comment summarizing orchestration results."""
        specification = delivery_package.get("specification", {})
        execution_summary = delivery_package.get("execution_summary", {})
        specialist_exec = execution_summary.get("specialist_execution", {})

        signoff_lines = []
        for role in ["po", "architect", "security", "devops", "developer", "qa", "finops", "release"]:
            role_data = specification.get(role, {}) if isinstance(specification, dict) else {}
            role_outcome = role_data.get("outcome", "not_run")
            role_conf = role_data.get("confidence", "n/a")
            signoff_lines.append(f"* {role.upper()}: {role_outcome} (confidence={role_conf})")

        specialist_lines = []
        for detail in specialist_exec.get("details", []):
            role = detail.get("role", "unknown")
            status = detail.get("status", "unknown")
            if status == "completed":
                specialist_lines.append(f"* ✅ {role}: COMPLETED")
            elif status == "failed":
                specialist_lines.append(f"* ❌ {role}: FAILED ({detail.get('error', 'unknown')})")
            else:
                specialist_lines.append(f"* ⚠️ {role}: {status}")

        return (
            "h3. 🤖 Agent-Core Orchestration Result\n\n"
            f"*Delivery Status:* {delivery_package.get('status', 'UNKNOWN')}\n"
            f"*Orchestration ID:* {delivery_package.get('orchestration_id')}\n"
            f"*Coordinator Outcome:* {coordinator_output.get('outcome', 'unknown')}\n\n"
            "h4. Specialist Execution\n"
            f"{chr(10).join(specialist_lines)}\n\n"
            "h4. Specialist Sign-offs\n"
            f"{chr(10).join(signoff_lines)}"
        )

    def _jira_headers(self) -> Dict[str, str]:
        if not JIRA_BASE_URL:
            raise RuntimeError("JIRA_BASE_URL application setting is missing")
        _email = _usable_secret_value(JIRA_EMAIL_ENV) or jira_email()
        _token = _usable_secret_value(JIRA_API_TOKEN_ENV) or jira_api_token()
        if not _email or not _token:
            raise RuntimeError("Jira email or API token not available")
        encoded = base64.b64encode(f"{_email}:{_token}".encode()).decode()
        return {
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _add_jira_comment(self, epic_key: str, comment_body: str) -> None:
        """Add comment to Jira issue."""
        headers = self._jira_headers()
        response = requests.post(
            f"{JIRA_BASE_URL}/rest/api/2/issue/{epic_key}/comment",
            headers=headers,
            json={"body": comment_body},
            timeout=30,
        )
        if response.status_code not in {200, 201}:
            logger.warning(f"Failed to add Jira comment: {response.status_code}")

    def _safe_add_jira_comment(self, epic_key: str, comment_body: str) -> None:
        """Safely add Jira comment, ignoring errors."""
        try:
            self._add_jira_comment(epic_key, comment_body)
        except Exception as e:
            logger.warning(f"Safe add Jira comment failed: {e}")

    async def _transition_epic(self, epic_key: str, target_status: str) -> None:
        """Transition epic to target status in Jira."""
        try:
            headers = self._jira_headers()
            # Get available transitions
            response = requests.get(
                f"{JIRA_BASE_URL}/rest/api/2/issue/{epic_key}/transitions",
                headers=headers,
                timeout=30,
            )
            if response.status_code == 200:
                transitions = response.json().get("transitions", [])
                for trans in transitions:
                    if trans.get("to", {}).get("name") == target_status:
                        # Execute transition
                        requests.post(
                            f"{JIRA_BASE_URL}/rest/api/2/issue/{epic_key}/transitions",
                            headers=headers,
                            json={"transition": {"id": trans.get("id")}},
                            timeout=30,
                        )
                        logger.info(f"Transitioned {epic_key} to {target_status}")
                        return
        except Exception as e:
            logger.warning(f"Failed to transition epic: {e}")
