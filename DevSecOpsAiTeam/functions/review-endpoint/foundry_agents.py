"""
AI Foundry Agent Manager - Handles agent discovery and invocation via Foundry agent runtime.

Uses Azure AI Agents SDK persistent runtime APIs (threads/messages/runs) for proper
Foundry invocation with telemetry and governance support (NOT direct OpenAI API).
"""

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("FoundryAgents")


@dataclass
class AgentConfig:
    role: str
    assistant_id: Optional[str] = None
    name: str = ""
    model: str = "gpt-4"
    description: str = ""


class FoundryAgentManager:
    """Manages AI Foundry agent lifecycle and invocation via persistent runtime APIs."""

    AGENT_CONFIGS = {
        "coordinator": AgentConfig(role="coordinator", name="Coordinator Agent"),
        "po": AgentConfig(role="po", name="Product Owner / Requirements Agent"),
        "architect": AgentConfig(
            role="architect", name="Solution Architect Agent"
        ),
        "security": AgentConfig(role="security", name="Security Architect Agent"),
        "devops": AgentConfig(role="devops", name="DevOps/IaC Agent"),
        "developer": AgentConfig(role="developer", name="Developer Agent"),
        "qa": AgentConfig(role="qa", name="QA/Tester Agent"),
        "finops": AgentConfig(role="finops", name="FinOps/Cost Agent"),
        "release": AgentConfig(role="release", name="Release Manager Agent"),
    }

    def __init__(self, foundry_client: Any):
        self.client = foundry_client
        self._discovered_assistants: Dict[str, str] = {}
        self._assistant_cache: Dict[str, Any] = {}
        logger.info("FoundryAgentManager initialized")

    # -------------------------------------------------------------------------
    # Agent discovery
    # -------------------------------------------------------------------------

    async def discover_agents(self) -> Dict[str, str]:
        """Discover agents: env map first, then live API."""
        logger.info("Discovering agents in AI Foundry project...")

        # Priority 1: Pre-registered agent map from environment variable
        env_map_json = os.environ.get("AI_FOUNDRY_ROLE_AGENT_MAP_JSON", "")
        if env_map_json:
            try:
                env_map: Dict[str, str] = json.loads(env_map_json)
                discovered: Dict[str, str] = {}
                for raw_role_name, assistant_id in env_map.items():
                    short_role = self._extract_role_from_name(raw_role_name)
                    if short_role:
                        discovered[short_role] = assistant_id
                        logger.info(
                            f"Loaded {short_role} -> {assistant_id} "
                            f"(from env map key: {raw_role_name})"
                        )
                if discovered:
                    self._discovered_assistants = discovered
                    logger.info(
                        f"{len(discovered)} agents loaded from AI_FOUNDRY_ROLE_AGENT_MAP_JSON"
                    )
                    return discovered
            except Exception as env_err:
                logger.warning(
                    f"Could not parse AI_FOUNDRY_ROLE_AGENT_MAP_JSON: {env_err}"
                )

        # Priority 2: Live API discovery
        try:
            discovered = {}
            assistants = self.client.list_agents()
            for assistant in assistants:
                role = self._extract_role_from_assistant(assistant)
                if role:
                    discovered[role] = assistant.id
                    self._assistant_cache[assistant.id] = {
                        "name": getattr(assistant, "name", "unknown"),
                        "model": getattr(assistant, "model", "unknown"),
                    }
                    logger.info(
                        f"Found {role} agent via live discovery: {assistant.id}"
                    )

            self._discovered_assistants = discovered
            if discovered:
                logger.info(f"Discovered {len(discovered)} agents via live API")
            else:
                logger.warning("No agents discovered via live API")
            return discovered
        except Exception as e:
            logger.error(f"Agent discovery failed: {e}", exc_info=True)
            return {}

    def _extract_role_from_name(self, name: str) -> Optional[str]:
        """Map raw agent name to canonical short role key.

        NOTE: 'security' must precede 'architect' so that 'security-architect'
        maps to 'security', not 'architect'.
        """
        name_lower = name.lower()
        role_patterns = {
            "coordinator": ["coordinator", "orchestrator"],
            "po": [
                "po-requirements",
                "po_requirements",
                "product owner",
                "requirements",
                "po",
            ],
            "security": ["security"],
            "architect": ["architect"],
            "devops": ["devops"],
            "developer": ["developer"],
            "qa": ["tester-qa", "tester_qa", "tester", "qa"],
            "finops": ["finops"],
            "release": ["release"],
        }
        for role, patterns in role_patterns.items():
            for pattern in patterns:
                if pattern in name_lower or name_lower == pattern:
                    return role
        return None

    def _extract_role_from_assistant(self, assistant: Any) -> Optional[str]:
        """Extract role from a live assistant object."""
        if not hasattr(assistant, "name"):
            return None
        return self._extract_role_from_name(assistant.name)

    # -------------------------------------------------------------------------
    # Agent invocation
    # -------------------------------------------------------------------------

    async def invoke_agent(
        self,
        agent_role: str,
        instruction: str,
        context: Dict[str, Any] = None,
        timeout_seconds: int = 300,
    ) -> Dict[str, Any]:
        """Invoke an agent by role with the given instruction.
        
        Uses Foundry persistent thread/run/message APIs for proper telemetry.
        """
        logger.info(f"Invoking agent: {agent_role}")

        # Resolve assistant ID from discovery cache
        assistant_id = self._discovered_assistants.get(agent_role)

        # Defensive direct env-map lookup
        if not assistant_id:
            env_map_json = os.environ.get("AI_FOUNDRY_ROLE_AGENT_MAP_JSON", "")
            if env_map_json:
                try:
                    env_map: Dict[str, str] = json.loads(env_map_json)
                    for raw_key, aid in env_map.items():
                        if self._extract_role_from_name(raw_key) == agent_role:
                            assistant_id = aid
                            logger.info(
                                f"Resolved {agent_role} -> {assistant_id} "
                                f"(direct env lookup)"
                            )
                            self._discovered_assistants[agent_role] = assistant_id
                            break
                except Exception as lookup_err:
                    logger.warning(
                        f"Direct env lookup failed for {agent_role}: {lookup_err}"
                    )

        if not assistant_id:
            raise RuntimeError(f"Agent {agent_role} not found")

        # Guard: client must be initialised
        if self.client is None:
            logger.error(f"AI Foundry client is None -- cannot invoke {agent_role}")
            raise RuntimeError("AI Foundry client not initialized")

        if (
            not hasattr(self.client, "threads")
            or not hasattr(self.client, "runs")
            or not hasattr(self.client, "messages")
        ):
            raise RuntimeError(
                "AI Foundry persistent agent runtime client is unavailable. "
                "Install/upgrade azure-ai-agents SDK in the function runtime."
            )

        try:
            # Step 1: Create thread
            logger.info(
                f"Creating thread for {agent_role} (assistant={assistant_id})"
            )
            thread = self.client.threads.create()
            thread_id = thread.id
            logger.info(f"Thread created: {thread_id}")

            # Step 2: Run agent on thread with polling
            response = await self._run_agent_with_polling(
                thread_id=thread_id,
                assistant_id=assistant_id,
                agent_role=agent_role,
                instruction=instruction,
                context=context,
                timeout_seconds=timeout_seconds,
            )
            logger.info(f"{agent_role} agent completed")
            return response

        except asyncio.TimeoutError:
            logger.error(f"{agent_role} agent timeout after {timeout_seconds}s")
            raise
        except Exception as e:
            logger.error(f"Failed to invoke {agent_role}: {e}", exc_info=True)
            raise

    async def _run_agent_with_polling(
        self,
        thread_id: str,
        assistant_id: str,
        agent_role: str,
        instruction: str,
        context: Optional[Dict[str, Any]],
        timeout_seconds: int,
    ) -> Dict[str, Any]:
        """Post message, run agent, and collect assistant output via Foundry SDK APIs."""
        message_text = self._format_agent_message(instruction, context)
        logger.info(
            f"Preparing to run assistant {assistant_id} on thread {thread_id}"
        )

        try:
            logger.info(f"Adding message to thread {thread_id}")
            self.client.messages.create(
                thread_id=thread_id,
                role="user",
                content=message_text,
            )
            run = await asyncio.wait_for(
                asyncio.to_thread(
                    self.client.runs.create_and_process,
                    thread_id=thread_id,
                    agent_id=assistant_id,
                ),
                timeout=timeout_seconds,
            )
            run_id = getattr(run, "id", "unknown")
            run_status = getattr(run, "status", "unknown")
            logger.info(f"Run completed: {run_id}, status={run_status}")
        except Exception as e:
            logger.error(
                f"Failed to start run for assistant {assistant_id}: "
                f"{type(e).__name__}: {e}",
                exc_info=True,
            )
            raise

        if run_status in ("failed", "cancelled", "expired"):
            last_error = getattr(run, "last_error", None)
            raise RuntimeError(f"Run {run_status}: {last_error}")

        if run_status != "completed":
            raise RuntimeError(f"Run ended with unexpected status: {run_status}")

        messages = self.client.messages.list(thread_id=thread_id)
        for message in reversed(list(messages)):
            if getattr(message, "role", "") == "assistant":
                content = self._extract_assistant_message_text(message)
                if content:
                    logger.info(
                        f"Agent {agent_role} response received ({len(content)} chars)"
                    )
                    return self._parse_agent_response(content)

        return {
            "outcome": "completed",
            "confidence": 0.5,
            "reasoning": "Agent completed but returned no message",
        }

    def _extract_assistant_message_text(self, message: Any) -> str:
        text_chunks: List[str] = []

        direct_text = getattr(message, "text", None)
        if isinstance(direct_text, str) and direct_text.strip():
            text_chunks.append(direct_text)

        text_messages = getattr(message, "text_messages", None)
        if text_messages:
            for text_message in text_messages:
                text_obj = getattr(text_message, "text", None)
                text_val = getattr(text_obj, "value", None)
                if isinstance(text_val, str) and text_val.strip():
                    text_chunks.append(text_val)

        if text_chunks:
            return "\n".join(text_chunks)

        content_items = getattr(message, "content", None) or []
        for item in content_items:
            if isinstance(item, str) and item.strip():
                text_chunks.append(item)
                continue
            item_text = getattr(item, "text", None)
            item_value = getattr(item_text, "value", None)
            if isinstance(item_value, str) and item_value.strip():
                text_chunks.append(item_value)

        return "\n".join(text_chunks)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _format_agent_message(
        self, instruction: str, context: Optional[Dict[str, Any]]
    ) -> str:
        """Format instruction with context."""
        message = instruction
        if context:
            message += "\n\n## Context:"
            for key, value in context.items():
                if isinstance(value, (dict, list)):
                    message += (
                        f"\n- {key}:\n```json\n{json.dumps(value, indent=2)}\n```"
                    )
                else:
                    message += f"\n- {key}: {value}"
        return message

    def _parse_agent_response(self, content: str) -> Dict[str, Any]:
        """Parse JSON agent response; fail-fast if unparseable."""
        if not content:
            raise ValueError("Agent returned an empty response")

        clean = content.strip()
        if clean.startswith("```"):
            lines = clean.split("\n")
            clean = "\n".join(lines[1:-1]) if len(lines) > 2 else clean

        try:
            result = json.loads(clean)
            result.setdefault("outcome", "completed")
            result.setdefault("confidence", 0.85)
            return result
        except json.JSONDecodeError:
            raise ValueError(f"Agent response is not valid JSON: {content[:300]}")


class AgentInvocationError(Exception):
    """Raised when agent invocation fails unexpectedly."""


class AgentTimeoutError(Exception):
    """Raised when agent execution exceeds the timeout."""
