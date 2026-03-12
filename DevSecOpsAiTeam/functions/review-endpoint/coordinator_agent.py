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
                timeout_seconds=600,
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
        summary: Dict[str, Any] = {
            "planned": roles,
            "invoked": 0,
            "completed": 0,
            "failed": 0,
            "failed_roles": [],
            "details": [],
        }

        for role in roles:
            if role not in discovered_agents:
                summary["details"].append(
                    {"role": role, "status": "skipped", "reason": "agent_not_discovered"}
                )
                continue

            summary["invoked"] += 1
            role_success = False
            last_error = ""

            for attempt in range(1, 3):
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
                        timeout_seconds=900,
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
                    last_error = f"{type(role_error).__name__}: {str(role_error)[:200]}"
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
        """
        Specialist agent instruction with minimal context requirement.
        Agents MUST read full Epic details from Jira using [Jira_GetIssue] tool.
        """
        return f"""
Execute your specialist {role} role for epic {epic_key}.

CONTEXT SETUP:
You will receive MINIMAL invocation context (epic_key, role, orchestration_id only).
This is required for Foundry to stay under 256KB message limits.

CRITICAL FIRST ACTION:
1. Call [Jira_GetIssue] with issue_key={epic_key} to fetch full Epic details
2. Read Epic description, acceptance criteria, linked issues
3. Understand all requirements for your role from the Epic

YOUR ROLE RESPONSIBILITIES ({role}):
- Perform real, tool-backed work for your role
- Do NOT return analysis-only output
- Execute actual actions (code, infrastructure, tests, etc.)
- Return strict JSON format with tool_actions and evidence_links

OUTPUT FORMAT:
{{
  "outcome": "completed|blocked|needs_input",
  "confidence": 0.0-1.0,
  "tool_actions": [list of executed tool calls],
  "evidence_links": [links to artifacts, deployed resources, test results],
  "blocked_reasons": [if blocked, why blocked],
  "summary": "brief description of work completed"
}}

If blocked, provide exact reasons and required next steps.
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
