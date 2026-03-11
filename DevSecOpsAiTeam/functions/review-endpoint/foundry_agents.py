"""
AI Foundry Agent Manager - strict agent invocation (no static fallback).

Current SDK in this project exposes agent discovery, but not thread/run runtime APIs,
so execution uses the Foundry OpenAI client responses endpoint while preserving
agent-role system prompts and strict fail-fast behavior.
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from agent_prompts import ROLE_SYSTEM_PROMPTS

logger = logging.getLogger("FoundryAgents")


@dataclass
class AgentConfig:
    role: str
    assistant_id: Optional[str] = None
    name: str = ""
    model: str = "gpt-4"
    description: str = ""


class FoundryAgentManager:
    """Manages AI Foundry agent discovery and strict invocation."""

    AGENT_CONFIGS = {
        "coordinator": AgentConfig(role="coordinator", name="Coordinator Agent"),
        "po": AgentConfig(role="po", name="Product Owner / Requirements Agent"),
        "architect": AgentConfig(role="architect", name="Solution Architect Agent"),
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
        self._openai_client: Any = None
        self._role_model_map = self._load_role_model_map()
        self._last_response_request_at = 0.0
        logger.info("FoundryAgentManager initialized")

    def _load_role_model_map(self) -> Dict[str, str]:
        raw_map = os.environ.get("AI_FOUNDRY_ROLE_MODEL_MAP_JSON", "")
        if not raw_map:
            return {}
        try:
            parsed = json.loads(raw_map)
            role_model_map: Dict[str, str] = {}
            for raw_role_name, model_name in parsed.items():
                short_role = self._extract_role_from_name(raw_role_name)
                if short_role and model_name:
                    role_model_map[short_role] = str(model_name)
            return role_model_map
        except Exception as map_err:
            logger.warning(f"Could not parse AI_FOUNDRY_ROLE_MODEL_MAP_JSON: {map_err}")
            return {}

    def _get_openai_client(self) -> Any:
        if self._openai_client is not None:
            return self._openai_client
        if self.client is None:
            raise RuntimeError("AI Foundry client not initialized")
        self._openai_client = self.client.get_openai_client()
        return self._openai_client

    async def discover_agents(self) -> Dict[str, str]:
        logger.info("Discovering agents in AI Foundry project...")

        env_map_json = os.environ.get("AI_FOUNDRY_ROLE_AGENT_MAP_JSON", "")
        if env_map_json:
            try:
                env_map: Dict[str, str] = json.loads(env_map_json)
                discovered: Dict[str, str] = {}
                for raw_role_name, assistant_id in env_map.items():
                    short_role = self._extract_role_from_name(raw_role_name)
                    if short_role:
                        discovered[short_role] = assistant_id
                if discovered:
                    self._discovered_assistants = discovered
                    logger.info(f"Loaded {len(discovered)} role mappings from env")
                    return discovered
            except Exception as env_err:
                logger.warning(f"Could not parse AI_FOUNDRY_ROLE_AGENT_MAP_JSON: {env_err}")

        try:
            discovered = {}
            assistants = self.client.agents.list()
            for assistant in assistants:
                role = self._extract_role_from_assistant(assistant)
                if role:
                    discovered[role] = assistant.id
                    self._assistant_cache[assistant.id] = {
                        "name": getattr(assistant, "name", "unknown"),
                        "model": getattr(assistant, "model", "unknown"),
                    }
            self._discovered_assistants = discovered
            return discovered
        except Exception as e:
            logger.error(f"Agent discovery failed: {e}", exc_info=True)
            return {}

    def _extract_role_from_name(self, name: str) -> Optional[str]:
        name_lower = name.lower()
        role_patterns = {
            "coordinator": ["coordinator", "orchestrator"],
            "po": ["po-requirements", "po_requirements", "product owner", "requirements", "po"],
            "security": ["security"],
            "architect": ["architect"],
            "devops": ["devops"],
            "developer": ["developer"],
            "qa": ["tester-qa", "tester_qa", "tester", "qa"],
            "finops": ["finops"],
            "release": ["release"],
        }
        for role, patterns in role_patterns.items():
            if any(pattern in name_lower or name_lower == pattern for pattern in patterns):
                return role
        return None

    def _extract_role_from_assistant(self, assistant: Any) -> Optional[str]:
        if not hasattr(assistant, "name"):
            return None
        return self._extract_role_from_name(assistant.name)

    def _model_for_role(self, agent_role: str) -> str:
        return self._role_model_map.get(
            agent_role,
            os.environ.get("AI_FOUNDRY_MODEL_DEPLOYMENT", "gpt-4.1-mini-agents"),
        )

    def _system_prompt_for_role(self, agent_role: str) -> Optional[str]:
        return ROLE_SYSTEM_PROMPTS.get(agent_role)

    async def invoke_agent(
        self,
        agent_role: str,
        instruction: str,
        context: Dict[str, Any] = None,
        timeout_seconds: int = 300,
    ) -> Dict[str, Any]:
        logger.info(f"Invoking agent: {agent_role}")

        system_prompt = self._system_prompt_for_role(agent_role)
        if not system_prompt:
            raise RuntimeError(f"No system prompt configured for role {agent_role}")

        if self.client is None:
            raise RuntimeError(f"AI Foundry client is None -- cannot invoke {agent_role}")

        openai_client = self._get_openai_client()
        model_name = self._model_for_role(agent_role)

        response = await self._run_agent_with_responses(
            openai_client=openai_client,
            agent_role=agent_role,
            model_name=model_name,
            system_prompt=system_prompt,
            instruction=instruction,
            context=context,
            timeout_seconds=timeout_seconds,
        )
        logger.info(f"{agent_role} agent completed")
        return response

    async def _run_agent_with_responses(
        self,
        openai_client: Any,
        agent_role: str,
        model_name: str,
        system_prompt: str,
        instruction: str,
        context: Optional[Dict[str, Any]],
        timeout_seconds: int,
    ) -> Dict[str, Any]:
        message_text = self._format_agent_message(instruction, context)
        max_attempts = 5
        default_model_name = os.environ.get("AI_FOUNDRY_MODEL_DEPLOYMENT", "gpt-4.1-mini-agents")
        current_model_name = model_name

        for attempt in range(1, max_attempts + 1):
            try:
                min_spacing_seconds = 2.0
                elapsed = time.monotonic() - self._last_response_request_at
                if elapsed < min_spacing_seconds:
                    await asyncio.sleep(min_spacing_seconds - elapsed)

                response = await asyncio.wait_for(
                    asyncio.to_thread(
                        openai_client.responses.create,
                        model=current_model_name,
                        instructions=system_prompt,
                        input=message_text,
                        max_output_tokens=1800,
                    ),
                    timeout=timeout_seconds,
                )
                self._last_response_request_at = time.monotonic()
                content = self._extract_response_text(response)
                return self._parse_agent_response(content)

            except Exception as e:
                self._last_response_request_at = time.monotonic()
                error_text = f"{type(e).__name__}: {e}".lower()
                is_rate_limit = "429" in error_text or "too_many_requests" in error_text

                if is_rate_limit and attempt < max_attempts:
                    if current_model_name != default_model_name:
                        current_model_name = default_model_name
                    await asyncio.sleep(min(30, 3 * attempt))
                    continue

                raise RuntimeError(f"Agent response failed for {agent_role}: {type(e).__name__}: {e}")

        raise RuntimeError(f"Responses API exhausted retries for {agent_role}")

    def _format_agent_message(self, instruction: str, context: Optional[Dict[str, Any]]) -> str:
        message = instruction
        if context:
            message += "\n\n## Context:"
            for key, value in context.items():
                if isinstance(value, (dict, list)):
                    message += f"\n- {key}:\n```json\n{json.dumps(value, indent=2)}\n```"
                else:
                    message += f"\n- {key}: {value}"
        return message

    def _extract_response_text(self, response: Any) -> str:
        output_text = getattr(response, "output_text", None)
        if output_text:
            return output_text

        text_parts: List[str] = []
        for item in getattr(response, "output", []) or []:
            for part in getattr(item, "content", []) or []:
                text_value = getattr(part, "text", None)
                if isinstance(text_value, str):
                    text_parts.append(text_value)
                elif text_value is not None and hasattr(text_value, "value"):
                    text_parts.append(text_value.value)

        return "\n".join(part for part in text_parts if part)

    def _parse_agent_response(self, content: str) -> Dict[str, Any]:
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
