"""Capability handler registry for direct skill dispatch.

Maps ``aria:capability/*`` skill paths to real Python capability classes,
bypassing the LLM sandbox pipeline. Capability skills call actual APIs
(Exa, Composio, Hunter, etc.) and return real data.

Usage::

    handler = get_capability_handler("aria:capability/contact-enricher")
    if handler:
        result = await handler(user_id, task, skill_entry)
"""

import logging
import time
import traceback
from collections.abc import Awaitable, Callable
from typing import Any

from src.agents.base import AgentResult
from src.agents.capabilities.base import CapabilityResult, UserContext
from src.db.supabase import SupabaseClient
from src.skills.index import SkillIndexEntry

logger = logging.getLogger(__name__)

# Type alias for capability handler functions
CapabilityHandler = Callable[
    [str, dict[str, Any], SkillIndexEntry],
    Awaitable[AgentResult],
]


def _result_to_agent_result(result: CapabilityResult, skill_path: str) -> AgentResult:
    """Convert a CapabilityResult to an AgentResult.

    Args:
        result: The capability execution result.
        skill_path: The skill path for metadata.

    Returns:
        AgentResult with mapped fields.
    """
    return AgentResult(
        success=result.success,
        data={
            "skill_execution": True,
            "execution_mode": "capability_direct",
            "skill_path": skill_path,
            "result": result.data,
            "artifacts": result.artifacts,
            "extracted_facts": result.extracted_facts,
        },
        error=result.error,
        tokens_used=result.tokens_used,
        execution_time_ms=result.execution_time_ms,
    )


async def _execute_capability(
    capability_class: type,
    user_id: str,
    task: dict[str, Any],
    skill_entry: SkillIndexEntry,
) -> AgentResult:
    """Generic handler that instantiates a capability class and executes it.

    Args:
        capability_class: The capability class to instantiate.
        user_id: ID of the user requesting execution.
        task: Task specification with parameters.
        skill_entry: The skill index entry for metadata.

    Returns:
        AgentResult with execution outcome.
    """
    start_ms = time.perf_counter()
    try:
        logger.debug(
            "Instantiating capability %s for user %s with task: %s",
            skill_entry.skill_path,
            user_id,
            task,
        )
        db = SupabaseClient.get_client()
        user_ctx = UserContext(user_id=user_id)

        cap = capability_class(
            supabase_client=db,
            memory_service=None,
            knowledge_graph=None,
            user_context=user_ctx,
        )

        logger.debug("Executing capability %s", skill_entry.skill_path)
        result: CapabilityResult = await cap.execute(task, context={})

        elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
        result.execution_time_ms = elapsed_ms

        logger.info(
            "Capability %s executed in %dms (success=%s)",
            skill_entry.skill_path,
            elapsed_ms,
            result.success,
        )

        return _result_to_agent_result(result, skill_entry.skill_path)

    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
        tb_str = traceback.format_exc()
        logger.error(
            "Capability %s execution failed after %dms\n"
            "Exception: %s: %s\n"
            "Task: %s\n"
            "Full traceback:\n%s",
            skill_entry.skill_path,
            elapsed_ms,
            type(e).__name__,
            str(e),
            task,
            tb_str,
        )
        return AgentResult(
            success=False,
            data={"skill_path": skill_entry.skill_path},
            error=f"{type(e).__name__}: {e}",
            execution_time_ms=elapsed_ms,
        )


# ---------------------------------------------------------------------------
# Lazy-loading handler factories
# Each factory imports the capability class only when first invoked,
# avoiding circular imports and heavy module loading at startup.
# ---------------------------------------------------------------------------


async def _handle_contact_enricher(
    user_id: str, task: dict[str, Any], skill_entry: SkillIndexEntry
) -> AgentResult:
    from src.agents.capabilities.contact_enricher import ContactEnricherCapability
    return await _execute_capability(ContactEnricherCapability, user_id, task, skill_entry)


async def _handle_web_intelligence(
    user_id: str, task: dict[str, Any], skill_entry: SkillIndexEntry
) -> AgentResult:
    from src.agents.capabilities.web_intel import WebIntelligenceCapability
    return await _execute_capability(WebIntelligenceCapability, user_id, task, skill_entry)


async def _handle_signal_radar(
    user_id: str, task: dict[str, Any], skill_entry: SkillIndexEntry
) -> AgentResult:
    from src.agents.capabilities.signal_radar import SignalRadarCapability
    return await _execute_capability(SignalRadarCapability, user_id, task, skill_entry)


async def _handle_linkedin_intelligence(
    user_id: str, task: dict[str, Any], skill_entry: SkillIndexEntry
) -> AgentResult:
    from src.agents.capabilities.linkedin import LinkedInIntelligenceCapability
    return await _execute_capability(LinkedInIntelligenceCapability, user_id, task, skill_entry)


async def _handle_email_intelligence(
    user_id: str, task: dict[str, Any], skill_entry: SkillIndexEntry
) -> AgentResult:
    from src.agents.capabilities.email_intel import EmailIntelligenceCapability
    return await _execute_capability(EmailIntelligenceCapability, user_id, task, skill_entry)


async def _handle_calendar_intelligence(
    user_id: str, task: dict[str, Any], skill_entry: SkillIndexEntry
) -> AgentResult:
    from src.agents.capabilities.calendar_intel import CalendarIntelligenceCapability
    return await _execute_capability(CalendarIntelligenceCapability, user_id, task, skill_entry)


async def _handle_crm_deep_sync(
    user_id: str, task: dict[str, Any], skill_entry: SkillIndexEntry
) -> AgentResult:
    from src.agents.capabilities.crm_sync import CRMDeepSyncCapability
    return await _execute_capability(CRMDeepSyncCapability, user_id, task, skill_entry)


async def _handle_meeting_intelligence(
    user_id: str, task: dict[str, Any], skill_entry: SkillIndexEntry
) -> AgentResult:
    from src.agents.capabilities.meeting_intel import MeetingIntelligenceCapability
    return await _execute_capability(MeetingIntelligenceCapability, user_id, task, skill_entry)


async def _handle_team_messenger(
    user_id: str, task: dict[str, Any], skill_entry: SkillIndexEntry
) -> AgentResult:
    from src.agents.capabilities.messenger import TeamMessengerCapability
    return await _execute_capability(TeamMessengerCapability, user_id, task, skill_entry)


async def _handle_mcp_evaluator(
    user_id: str, task: dict[str, Any], skill_entry: SkillIndexEntry
) -> AgentResult:
    """MCPEvaluatorCapability has a non-standard constructor (llm_client only)."""
    start_ms = time.perf_counter()
    try:
        from src.agents.capabilities.mcp_evaluator import MCPEvaluatorCapability
        from src.core.llm import LLMClient

        evaluator = MCPEvaluatorCapability(llm_client=LLMClient())
        # MCPEvaluator uses evaluate(), not execute() — adapt the interface
        server_info = task.get("server_info") or task
        result = await evaluator.evaluate(server_info)
        elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
        return AgentResult(
            success=True,
            data={
                "skill_execution": True,
                "execution_mode": "capability_direct",
                "skill_path": skill_entry.skill_path,
                "result": result.__dict__ if hasattr(result, "__dict__") else {"assessment": str(result)},
            },
            execution_time_ms=elapsed_ms,
        )
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
        logger.exception("MCP evaluator execution failed: %s", e)
        return AgentResult(success=False, data={"skill_path": skill_entry.skill_path}, error=str(e), execution_time_ms=elapsed_ms)


async def _handle_mcp_discovery(
    user_id: str, task: dict[str, Any], skill_entry: SkillIndexEntry
) -> AgentResult:
    """MCPDiscoveryCapability has a non-standard constructor (scanner only)."""
    start_ms = time.perf_counter()
    try:
        from src.agents.capabilities.mcp_discovery import MCPDiscoveryCapability

        discovery = MCPDiscoveryCapability()
        capability_query = task.get("description", task.get("query", ""))
        results = await discovery.search_for_capability(capability_query, limit=5)
        elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
        return AgentResult(
            success=True,
            data={
                "skill_execution": True,
                "execution_mode": "capability_direct",
                "skill_path": skill_entry.skill_path,
                "result": {"servers": [r.__dict__ if hasattr(r, "__dict__") else str(r) for r in results]},
            },
            execution_time_ms=elapsed_ms,
        )
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
        logger.exception("MCP discovery execution failed: %s", e)
        return AgentResult(success=False, data={"skill_path": skill_entry.skill_path}, error=str(e), execution_time_ms=elapsed_ms)


async def _handle_compliance(
    user_id: str, task: dict[str, Any], skill_entry: SkillIndexEntry
) -> AgentResult:
    """ComplianceScanner is not a BaseCapability — uses scan_text() directly."""
    start_ms = time.perf_counter()
    try:
        from src.agents.capabilities.compliance import ComplianceScanner

        scanner = ComplianceScanner()
        text = task.get("text", task.get("content", task.get("description", "")))
        scan_result = scanner.scan_text(text)
        elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
        return AgentResult(
            success=True,
            data={
                "skill_execution": True,
                "execution_mode": "capability_direct",
                "skill_path": skill_entry.skill_path,
                "result": {
                    "has_findings": scan_result.has_findings,
                    "highest_risk": scan_result.highest_risk,
                    "match_count": len(scan_result.matches),
                },
            },
            execution_time_ms=elapsed_ms,
        )
    except Exception as e:
        elapsed_ms = int((time.perf_counter() - start_ms) * 1000)
        logger.exception("Compliance scan execution failed: %s", e)
        return AgentResult(success=False, data={"skill_path": skill_entry.skill_path}, error=str(e), execution_time_ms=elapsed_ms)


# ---------------------------------------------------------------------------
# Registry mapping skill_path -> handler
# ---------------------------------------------------------------------------

_CAPABILITY_HANDLERS: dict[str, CapabilityHandler] = {
    "aria:capability/contact-enricher": _handle_contact_enricher,
    "aria:capability/web-intelligence": _handle_web_intelligence,
    "aria:capability/signal-radar": _handle_signal_radar,
    "aria:capability/linkedin-intelligence": _handle_linkedin_intelligence,
    "aria:capability/email-intelligence": _handle_email_intelligence,
    "aria:capability/calendar-intelligence": _handle_calendar_intelligence,
    "aria:capability/crm-deep-sync": _handle_crm_deep_sync,
    "aria:capability/meeting-intelligence": _handle_meeting_intelligence,
    "aria:capability/team-messenger": _handle_team_messenger,
    "aria:capability/mcp-evaluator": _handle_mcp_evaluator,
    "aria:capability/mcp-discovery": _handle_mcp_discovery,
    "aria:capability/compliance": _handle_compliance,
}


def get_capability_handler(skill_path: str) -> CapabilityHandler | None:
    """Look up a capability handler by skill path.

    Args:
        skill_path: The skill path to look up (e.g., "aria:capability/contact-enricher").

    Returns:
        The handler function if found, None otherwise.
    """
    return _CAPABILITY_HANDLERS.get(skill_path)


def is_capability_skill(skill_path: str) -> bool:
    """Check if a skill path corresponds to a capability (direct dispatch).

    Args:
        skill_path: The skill path to check.

    Returns:
        True if this skill path has a registered capability handler.
    """
    return skill_path in _CAPABILITY_HANDLERS
