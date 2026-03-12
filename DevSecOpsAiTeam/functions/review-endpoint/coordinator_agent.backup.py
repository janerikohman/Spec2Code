"""Agent-core coordinator.

Rules enforced:
- Coordinator agent is the only orchestration decision-maker.
- No static sequencing, no legacy orchestration paths, no fallback behavior.
- Azure Function and this class are execution shells/tool adapters only.
"""

import base64
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

import requests

from foundry_agents import FoundryAgentManager
from keyvault_secrets import jira_email, jira_api_token  # RULE_15 / RULE_16

logger = logging.getLogger("CoordinatorAgent")

# Non-secret configuration — safe to keep in Application Settings / env vars.
# Credentials (email, tokens) are fetched from Azure Key Vault at call time (RULE_15).
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

            # Coordinator may return a structured delivery_package dict, or a
            # natural-language raw_response (text/markdown). Both are valid.
            delivery_package = coordinator_output.get("delivery_package")
            if not isinstance(delivery_package, dict):
                # Build a minimal delivery_package from whatever the coordinator returned.
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
                },
            )

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
                        "step": "coordinator_agent_completed",
                        "confidence": coordinator_output.get("confidence", 0.0),
                        "outcome": coordinator_output.get("outcome", "unknown"),
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

Hard rules:
1) You are the only orchestrator and final decision-maker.
2) If any doubt exists, request clarification between responsible specialist agents and resolve it.
3) Jira, Confluence, Bitbucket, Azure are tools used by agents.
4) No static/fallback behavior is allowed.

You must return valid JSON and include:
- outcome, confidence
- clarification_loops
- signoffs for all specialist roles
- delivery_package with status/specification/gates_verified/all_gates_passed/execution_summary
- blocked_reasons and next_required_inputs when not ready
""".strip()

    def _jira_headers(self) -> Dict[str, str]:
        # RULE_15: credentials fetched from Key Vault at call time, never hardcoded.
        # RULE_16: Jira and Confluence share the same email + API token.
        if not JIRA_BASE_URL:
            raise RuntimeError("JIRA_BASE_URL application setting is missing")
        _email = _usable_secret_value(JIRA_EMAIL_ENV) or jira_email()
        _token = _usable_secret_value(JIRA_API_TOKEN_ENV) or jira_api_token()
        encoded = base64.b64encode(f"{_email}:{_token}".encode("utf-8")).decode("utf-8")
        return {
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _confluence_headers(self) -> Dict[str, str]:
        # RULE_15: credentials fetched from Key Vault at call time, never hardcoded.
        # RULE_16: Confluence uses the SAME email + API token as Jira.
        if not CONFLUENCE_BASE_URL:
            raise RuntimeError("CONFLUENCE_BASE_URL application setting is missing")
        _email = _usable_secret_value(JIRA_EMAIL_ENV) or jira_email()
        _token = _usable_secret_value(JIRA_API_TOKEN_ENV) or jira_api_token()
        encoded = base64.b64encode(f"{_email}:{_token}".encode("utf-8")).decode("utf-8")
        return {
            "Authorization": f"Basic {encoded}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _get_jira_issue_context(self, epic_key: str) -> Dict[str, Any]:
        headers = self._jira_headers()
        response = requests.get(
            f"{JIRA_BASE_URL}/rest/api/2/issue/{epic_key}",
            headers=headers,
            timeout=30,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Jira API error: {response.status_code} - {response.text[:400]}")
        return response.json()

    async def _store_orchestration_results(
        self,
        epic_key: str,
        delivery_package: Dict[str, Any],
        coordinator_output: Dict[str, Any],
    ) -> None:
        jira_comment = self._build_jira_comment(delivery_package, coordinator_output)
        self._add_jira_comment(epic_key, jira_comment)

        confluence_link: Optional[str] = None
        try:
            confluence_html = self._build_confluence_page_html(epic_key, delivery_package, coordinator_output)
            confluence_link = self._create_confluence_page(
                title=f"Delivery Package: {epic_key}",
                storage_html=confluence_html,
            )
        except Exception as confluence_error:
            logger.warning(f"Confluence write skipped: {confluence_error}")

        if confluence_link:
            self._safe_add_jira_comment(epic_key, f"📚 Delivery package page: {confluence_link}")

    def _build_jira_comment(self, delivery_package: Dict[str, Any], coordinator_output: Dict[str, Any]) -> str:
        gates = delivery_package.get("gates_verified", {})
        specification = delivery_package.get("specification", {})

        signoff_lines = []
        for role in ["po", "architect", "security", "devops", "developer", "qa", "finops", "release"]:
            role_data = specification.get(role, {}) if isinstance(specification, dict) else {}
            role_outcome = role_data.get("outcome", "not_run")
            role_conf = role_data.get("confidence", "n/a")
            signoff_lines.append(f"* {role.upper()}: {role_outcome} (confidence={role_conf})")

        loop_items = coordinator_output.get("clarification_loops", [])
        loop_lines = []
        for loop in loop_items:
            frm = loop.get("from_agent", "?")
            to = loop.get("to_agent", "?")
            resolved = loop.get("resolved", False)
            loop_lines.append(f"* {frm} → {to}: {'✅ resolved' if resolved else '⚠️ open'}")
        if not loop_lines:
            loop_lines = ["* No clarification loops returned"]

        gate_lines = [
            f"* {gate}: {'✅ PASS' if status else '❌ FAIL'}"
            for gate, status in gates.items()
        ]
        if not gate_lines:
            gate_lines = ["* No gate verification returned"]

        return (
            "h3. 🤖 Agent-Core Orchestration Result\n\n"
            f"*Delivery Status:* {delivery_package.get('status', 'UNKNOWN')}\n"
            f"*Orchestration ID:* {delivery_package.get('orchestration_id')}\n"
            f"*Coordinator Outcome:* {coordinator_output.get('outcome', 'unknown')}\n"
            f"*Coordinator Confidence:* {coordinator_output.get('confidence', 'n/a')}\n\n"
            "h4. Clarification Loops\n"
            f"{chr(10).join(loop_lines)}\n\n"
            "h4. Specialist Sign-offs\n"
            f"{chr(10).join(signoff_lines)}\n\n"
            "h4. Gate Verification\n"
            f"{chr(10).join(gate_lines)}"
        )

    def _build_confluence_page_html(
        self,
        epic_key: str,
        delivery_package: Dict[str, Any],
        coordinator_output: Dict[str, Any],
    ) -> str:
        specification = delivery_package.get("specification", {})
        gates = delivery_package.get("gates_verified", {})

        return (
            f"<h1>Delivery Package: {epic_key}</h1>"
            f"<p><strong>Status:</strong> {delivery_package.get('status')}</p>"
            f"<p><strong>Orchestration ID:</strong> {delivery_package.get('orchestration_id')}</p>"
            f"<p><strong>Coordinator Outcome:</strong> {coordinator_output.get('outcome')}</p>"
            f"<h2>Gates</h2><pre>{json.dumps(gates, indent=2)}</pre>"
            f"<h2>Specification</h2><pre>{json.dumps(specification, indent=2)}</pre>"
            f"<h2>Clarification Loops</h2><pre>{json.dumps(coordinator_output.get('clarification_loops', []), indent=2)}</pre>"
            f"<h2>Signoffs</h2><pre>{json.dumps(coordinator_output.get('signoffs', {}), indent=2)}</pre>"
        )

    def _add_jira_comment(self, issue_key: str, comment_text: str) -> None:
        headers = self._jira_headers()
        body = {"body": comment_text}
        response = requests.post(
            f"{JIRA_BASE_URL}/rest/api/2/issue/{issue_key}/comment",
            json=body,
            headers=headers,
            timeout=30,
        )
        if response.status_code not in (200, 201):
            raise RuntimeError(f"Jira API error: {response.status_code} - {response.text[:400]}")

    def _safe_add_jira_comment(self, issue_key: str, comment_text: str) -> None:
        try:
            self._add_jira_comment(issue_key, comment_text)
        except Exception as comment_error:
            logger.warning(f"Could not add Jira comment for {issue_key}: {comment_error}")

    def _create_confluence_page(self, title: str, storage_html: str) -> str:
        headers = self._confluence_headers()
        payload = {
            "type": "page",
            "title": title,
            "space": {"key": CONFLUENCE_SPACE_KEY},
            "body": {
                "storage": {
                    "value": storage_html,
                    "representation": "storage",
                }
            },
        }
        response = requests.post(
            f"{CONFLUENCE_BASE_URL}/rest/api/content",
            json=payload,
            headers=headers,
            timeout=30,
        )
        if response.status_code not in (200, 201):
            raise RuntimeError(f"Confluence API error: {response.status_code} - {response.text[:400]}")
        data = response.json()
        return f"{CONFLUENCE_BASE_URL}/wiki/spaces/{CONFLUENCE_SPACE_KEY}/pages/{data.get('id')}"

    async def _transition_epic(self, epic_key: str, to_status: str) -> None:
        headers = self._jira_headers()

        transitions_response = requests.get(
            f"{JIRA_BASE_URL}/rest/api/3/issue/{epic_key}/transitions",
            headers=headers,
            timeout=30,
        )
        if transitions_response.status_code != 200:
            raise RuntimeError(
                f"Jira transitions read failed: {transitions_response.status_code} - "
                f"{transitions_response.text[:400]}"
            )

        transitions = transitions_response.json().get("transitions", [])
        transition_id = None
        for transition in transitions:
            if transition.get("to", {}).get("name", "").lower() == to_status.lower():
                transition_id = transition.get("id")
                break

        if not transition_id:
            logger.warning(f"No Jira transition available from current status to {to_status}")
            return

        transition_response = requests.post(
            f"{JIRA_BASE_URL}/rest/api/3/issue/{epic_key}/transitions",
            headers=headers,
            json={"transition": {"id": transition_id}},
            timeout=30,
        )

        if transition_response.status_code not in (200, 204):
            raise RuntimeError(
                f"Jira transition failed: {transition_response.status_code} - "
                f"{transition_response.text[:400]}"
            )
