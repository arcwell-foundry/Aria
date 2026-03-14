"""ScribeAgent module for ARIA.

Drafts emails and documents with style matching using Digital Twin.
Uses LLM generation as the primary drafting method with template-based
fallback for resilience.
"""

import json
import logging
import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from src.agents.base import AgentResult
from src.agents.skill_aware_agent import SkillAwareAgent
from src.core.config import settings
from src.core.task_types import TaskType
from src.prompts.email_writing_framework import ELITE_EMAIL_FRAMEWORK
from src.security.prompt_security import wrap_external_data

if TYPE_CHECKING:
    from src.core.llm import LLMClient
    from src.core.persona import PersonaBuilder
    from src.memory.cold_retrieval import ColdMemoryRetriever
    from src.skills.index import SkillIndex
    from src.skills.orchestrator import SkillOrchestrator

logger = logging.getLogger(__name__)


def _extract_json_from_text(text: str) -> Any:
    """Extract JSON from text that Claude may wrap in markdown code fences.

    Tries multiple strategies in order:
    1. Direct json.loads() on the full text
    2. Regex extraction from ```json ... ``` or ``` ... ``` code fences
    3. Bracket/brace boundary detection (finds first { or [ and its match)

    Args:
        text: Raw text potentially containing JSON.

    Returns:
        Parsed JSON object (dict or list).

    Raises:
        ValueError: If no valid JSON can be extracted from the text.
    """
    # Strategy 1: Try direct parse
    stripped = text.strip()
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        pass

    # Strategy 2: Extract from markdown code fences
    fence_pattern = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL)
    fence_match = fence_pattern.search(text)
    if fence_match:
        try:
            return json.loads(fence_match.group(1).strip())
        except (json.JSONDecodeError, ValueError):
            pass

    # Strategy 3: Bracket/brace boundary detection
    for open_char, close_char in [("{", "}"), ("[", "]")]:
        start_idx = text.find(open_char)
        if start_idx == -1:
            continue

        # Walk forward to find the matching closing character
        depth = 0
        in_string = False
        escape_next = False
        for i in range(start_idx, len(text)):
            ch = text[i]
            if escape_next:
                escape_next = False
                continue
            if ch == "\\":
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == open_char:
                depth += 1
            elif ch == close_char:
                depth -= 1
                if depth == 0:
                    candidate = text[start_idx : i + 1]
                    try:
                        return json.loads(candidate)
                    except (json.JSONDecodeError, ValueError):
                        break

    raise ValueError(f"No valid JSON found in text: {text[:200]}...")


class ScribeAgent(SkillAwareAgent):
    """Drafts emails and documents with style matching.

    The Scribe agent creates communications tailored to the user's
    writing style using Digital Twin, with support for multiple
    tones and templates. Uses LLM generation as the primary drafting
    method with template-based fallback.

    Now includes recipient research via Exa for personalized emails.
    """

    name = "Scribe"
    description = "Drafts emails and documents with style matching"
    agent_id = "scribe"

    # Valid communication types and tones
    VALID_COMMUNICATION_TYPES = {"email", "document", "message"}
    VALID_TONES = {"formal", "friendly", "urgent"}

    def __init__(
        self,
        llm_client: "LLMClient",
        user_id: str,
        skill_orchestrator: "SkillOrchestrator | None" = None,
        skill_index: "SkillIndex | None" = None,
        persona_builder: "PersonaBuilder | None" = None,
        cold_retriever: "ColdMemoryRetriever | None" = None,
    ) -> None:
        """Initialize the Scribe agent.

        Args:
            llm_client: LLM client for reasoning and generation.
            user_id: ID of the user this agent is working for.
            skill_orchestrator: Optional orchestrator for multi-skill execution.
            skill_index: Optional index for skill discovery.
            persona_builder: Optional PersonaBuilder for Digital Twin style matching.
            cold_retriever: Optional retriever for on-demand memory search.
        """
        self._templates: dict[str, str] = self._get_builtin_templates()
        self._exa_provider: Any = None
        self._resource_status: list[dict[str, Any]] = []  # Tool connectivity status
        super().__init__(
            llm_client=llm_client,
            user_id=user_id,
            skill_orchestrator=skill_orchestrator,
            skill_index=skill_index,
            persona_builder=persona_builder,
            cold_retriever=cold_retriever,
        )

    def _get_exa_provider(self) -> Any:
        """Lazily initialize and return the ExaEnrichmentProvider."""
        if self._exa_provider is None:
            try:
                from src.agents.capabilities.enrichment_providers.exa_provider import (
                    ExaEnrichmentProvider,
                )

                self._exa_provider = ExaEnrichmentProvider()
                logger.info("ScribeAgent: ExaEnrichmentProvider initialized")
            except Exception as e:
                logger.warning("ScribeAgent: Failed to initialize ExaEnrichmentProvider: %s", e)
        return self._exa_provider

    async def _load_outreach_intelligence(
        self,
        recipient: dict[str, Any] | None,
        lead_memory_id: str | None = None,
    ) -> dict[str, Any]:
        """Load outreach intelligence context for drafting.

        Per execution_spec.md Section 5.1-5.2, loads:
        - Persona-specific messaging approach from stakeholder title/role
        - Trigger event that originated this lead
        - Company enrichment facts from memory_semantic

        Args:
            recipient: Recipient info with name, company, title.
            lead_memory_id: Optional lead_memory_id to look up context.

        Returns:
            Dict with persona_approach, trigger_context, company_facts.
        """
        context: dict[str, Any] = {
            "persona_approach": "",
            "trigger_context": "",
            "company_facts": [],
            "stakeholder_role": "",
        }

        if not recipient:
            return context

        recipient_title = recipient.get("title", "")
        recipient_company = recipient.get("company", "")

        # 1. Determine persona-specific messaging approach from title/role
        context["persona_approach"] = self._determine_persona_approach(
            title=recipient_title,
            role=recipient.get("role", ""),
        )

        try:
            from src.db.supabase import SupabaseClient

            db = SupabaseClient.get_client()
        except Exception as e:
            logger.warning("[SCRIBE] Cannot access DB for outreach intelligence: %s", e)
            return context

        # 2. Load stakeholder role from lead_memory_stakeholders
        if recipient_company and not lead_memory_id:
            try:
                lead_result = (
                    db.table("lead_memories")
                    .select("id")
                    .eq("user_id", self.user_id)
                    .ilike("company_name", f"%{recipient_company}%")
                    .order("created_at", desc=True)
                    .limit(1)
                    .execute()
                )
                if lead_result.data:
                    lead_memory_id = lead_result.data[0]["id"]
            except Exception as e:
                logger.debug("[SCRIBE] Failed to look up lead_memory_id: %s", e)

        if lead_memory_id:
            # Load stakeholder details
            try:
                recipient_name = recipient.get("name", "")
                if recipient_name:
                    stakeholder_result = (
                        db.table("lead_memory_stakeholders")
                        .select("title, role, influence_level")
                        .eq("lead_memory_id", lead_memory_id)
                        .ilike("contact_name", f"%{recipient_name}%")
                        .limit(1)
                        .execute()
                    )
                    if stakeholder_result.data:
                        sh = stakeholder_result.data[0]
                        context["stakeholder_role"] = sh.get("role", "")
                        # Refine persona approach with DB-stored role
                        if sh.get("role"):
                            context["persona_approach"] = self._determine_persona_approach(
                                title=sh.get("title", recipient_title),
                                role=sh["role"],
                            )
                        logger.info(
                            "[SCRIBE] Loaded stakeholder: role=%s, influence=%s",
                            sh.get("role", "?"),
                            sh.get("influence_level", "?"),
                        )
            except Exception as e:
                logger.debug("[SCRIBE] Failed to load stakeholder: %s", e)

            # 3. Load trigger event from lead_memory_events
            try:
                event_result = (
                    db.table("lead_memory_events")
                    .select("event_type, subject, content, occurred_at, metadata")
                    .eq("lead_memory_id", lead_memory_id)
                    .in_("event_type", ["signal", "discovery"])
                    .order("occurred_at", desc=True)
                    .limit(1)
                    .execute()
                )
                if event_result.data:
                    evt = event_result.data[0]
                    trigger_type = (evt.get("metadata") or {}).get(
                        "trigger_signal_type",
                        evt.get("event_type", ""),
                    )
                    context["trigger_context"] = (
                        f"Trigger: {trigger_type}. "
                        f"{evt.get('subject', '')}. "
                        f"{evt.get('content', '')[:200]}"
                    )
                    logger.info(
                        "[SCRIBE] Loaded trigger event: %s", trigger_type
                    )
            except Exception as e:
                logger.debug("[SCRIBE] Failed to load trigger event: %s", e)

        # 4. Load company enrichment facts from memory_semantic
        if recipient_company:
            try:
                facts_result = (
                    db.table("memory_semantic")
                    .select("fact, confidence")
                    .eq("user_id", self.user_id)
                    .ilike("fact", f"%{recipient_company}%")
                    .order("confidence", desc=True)
                    .limit(5)
                    .execute()
                )
                if facts_result.data:
                    context["company_facts"] = [
                        row["fact"] for row in facts_result.data
                    ]
                    logger.info(
                        "[SCRIBE] Loaded %d company facts for %s",
                        len(facts_result.data),
                        recipient_company,
                    )
            except Exception as e:
                logger.debug("[SCRIBE] Failed to load company facts: %s", e)

        return context

    def _determine_persona_approach(
        self,
        title: str,
        role: str = "",
    ) -> str:
        """Determine persona-specific messaging approach.

        Per knowledge_base.md Section 5.2, maps title/role to messaging
        framework: senior executive, technical leader, procurement, or
        quality/regulatory.

        Args:
            title: Contact's job title.
            role: Stakeholder role (decision_maker, influencer, etc.).

        Returns:
            Messaging approach instruction string for LLM prompt.
        """
        title_lower = title.lower()

        # Senior executive persona
        if any(
            kw in title_lower
            for kw in [
                "ceo", "cfo", "cto", "coo", "chief", "president",
                "svp", "evp", "vp commercial", "vp sales", "cco",
            ]
        ) or role == "decision_maker":
            return (
                "PERSONA: Senior Executive. "
                "Use strategic, ROI-focused language. Lead with competitive insight or market trend. "
                "Reference recent earnings call language or conference presentation if available. "
                "Quantify potential impact. Keep it concise -- 3-4 short paragraphs max. "
                "Tone: peer-level, confident."
            )

        # Technical leader persona
        if any(
            kw in title_lower
            for kw in [
                "r&d", "research", "scientist", "phd", "cso",
                "scientific", "engineering", "development",
            ]
        ):
            return (
                "PERSONA: Technical Leader. "
                "Use evidence-based, scientifically precise language. Reference specific programs "
                "in their pipeline. Cite relevant data. Offer scientific value (application note, "
                "case study, technical comparison). Tone: collegial, peer-level, respectful of expertise."
            )

        # Procurement / operations persona
        if any(
            kw in title_lower
            for kw in [
                "procurement", "sourcing", "supply chain", "operations",
                "manufacturing", "vp ops",
            ]
        ):
            return (
                "PERSONA: Procurement/Operations. "
                "Lead with operational efficiency or cost insight. Reference industry benchmark data. "
                "Emphasize compliance credentials and TCO. Use language: efficiency, SLA, vendor "
                "qualification, audit readiness. Tone: professional, structured, detail-oriented."
            )

        # Quality / regulatory persona
        if any(
            kw in title_lower
            for kw in [
                "quality", "regulatory", "compliance", "validation",
                "gmp", "gxp",
            ]
        ):
            return (
                "PERSONA: Quality/Regulatory. "
                "Lead with compliance-relevant content. Reference recent regulatory developments "
                "(new FDA guidance, enforcement actions). Use language: validation, qualification, "
                "audit trail, 21 CFR Part 11, data integrity. Tone: conservative, precise, risk-aware."
            )

        # Default: general professional
        return (
            "PERSONA: Business Professional. "
            "Lead with insight relevant to their role. Keep messaging concise and value-first. "
            "Reference specific company events or recent news. Include a clear next step."
        )

    def _run_compliance_scan(
        self,
        subject: str,
        body: str,
        recipient: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Run compliance scan on a drafted email.

        Checks for:
        - Medical/efficacy claims requiring MLR review
        - HCP recipient (flag for Sunshine Act tracking)
        - Competitive claims from non-public sources

        Args:
            subject: Email subject line.
            body: Email body text.
            recipient: Recipient info with title, company.

        Returns:
            Compliance scan results dict for email_drafts.metadata.
        """
        findings: list[dict[str, str]] = []
        flags: list[str] = []
        combined_text = f"{subject} {body}".lower()

        # 1. Medical claims scan (efficacy/treatment language)
        medical_patterns = [
            (r"\b(cure|treat|heal|remedy|prevent)\b", "medical_claim"),
            (r"\b(clinically\s+proven|scientifically\s+proven)\b", "unqualified_efficacy"),
            (r"\b(superior\s+to|better\s+than|outperforms)\b.*\b(treatment|therapy|drug)\b", "comparative_claim"),
            (r"\b(fda\s+approved\s+for|indicated\s+for)\b", "regulatory_claim"),
            (r"\b(patient\s+outcomes?|survival\s+rate|response\s+rate)\b", "clinical_outcome_claim"),
            (r"\b(no\s+side\s+effects?|zero\s+adverse)\b", "safety_claim"),
        ]
        for pattern, claim_type in medical_patterns:
            if re.search(pattern, combined_text):
                findings.append({
                    "type": "medical_claim",
                    "subtype": claim_type,
                    "severity": "high",
                    "recommendation": "Requires MLR (Medical, Legal, Regulatory) review before sending",
                })
                if "mlr_review_required" not in flags:
                    flags.append("mlr_review_required")

        # 2. HCP recipient check (Sunshine Act / Open Payments)
        hcp_indicators = [
            "md", "m.d.", "do", "d.o.", "phd", "ph.d.",
            "physician", "surgeon", "clinician", "nurse practitioner",
            "pharmacist", "medical director", "chief medical",
        ]
        recipient_title = ""
        if recipient:
            recipient_title = recipient.get("title", "").lower()

        is_hcp = any(ind in recipient_title for ind in hcp_indicators)
        if is_hcp:
            findings.append({
                "type": "hcp_recipient",
                "subtype": "sunshine_act",
                "severity": "medium",
                "recommendation": (
                    "Recipient appears to be a Healthcare Professional. "
                    "Ensure compliance with Sunshine Act / Open Payments "
                    "reporting if offering anything of value."
                ),
            })
            flags.append("hcp_sunshine_act")

        # 3. Competitive claims from non-public sources
        competitive_patterns = [
            (r"\b(confidential|internal)\s+(data|source|intelligence)\b", "non_public_source"),
            (r"\b(we\s+learned|we\s+discovered|our\s+sources)\b.*\b(competitor|rival)\b", "competitive_intelligence"),
            (r"\b(their\s+internal|inside\s+information)\b", "insider_information"),
        ]
        for pattern, claim_type in competitive_patterns:
            if re.search(pattern, combined_text):
                findings.append({
                    "type": "competitive_claim",
                    "subtype": claim_type,
                    "severity": "high",
                    "recommendation": "Remove references to non-public competitive intelligence",
                })
                if "competitive_review" not in flags:
                    flags.append("competitive_review")

        scan_result = {
            "scanned_at": datetime.now(UTC).isoformat(),
            "passed": len(findings) == 0,
            "findings": findings,
            "flags": flags,
            "finding_count": len(findings),
        }

        if findings:
            logger.info(
                "[SCRIBE] Compliance scan found %d issue(s): %s",
                len(findings),
                ", ".join(flags),
            )
        else:
            logger.info("[SCRIBE] Compliance scan passed")

        return scan_result

    async def _track_outreach_in_memory(
        self,
        content: dict[str, Any],
        recipient: dict[str, Any] | None,
        compliance_scan: dict[str, Any],
        lead_memory_id: str | None = None,
    ) -> None:
        """Track outreach draft in lead_memory_events, email_drafts, aria_activity.

        Per execution_spec.md Section 5.3. NEVER auto-sends.

        Args:
            content: Drafted email content with subject, body.
            recipient: Recipient info.
            compliance_scan: Compliance scan results.
            lead_memory_id: Optional lead_memory_id for event tracking.
        """
        try:
            from src.db.supabase import SupabaseClient

            db = SupabaseClient.get_client()
        except Exception as e:
            logger.warning("[SCRIBE] Cannot access DB for outreach tracking: %s", e)
            return

        now_iso = datetime.now(UTC).isoformat()
        draft_id = str(uuid4())
        recipient_email = ""
        recipient_name = ""
        recipient_company = ""

        if recipient:
            recipient_email = recipient.get("email", "")
            recipient_name = recipient.get("name", "")
            recipient_company = recipient.get("company", "")

        # 1. email_drafts INSERT (status: 'draft' — NEVER auto-send)
        try:
            db.table("email_drafts").insert({
                "id": draft_id,
                "user_id": self.user_id,
                "recipient_email": recipient_email,
                "recipient": recipient_name,
                "recipient_company": recipient_company,
                "subject": content.get("subject", ""),
                "body": content.get("body", ""),
                "status": "draft",
                "metadata": {
                    "lead_memory_id": lead_memory_id,
                    "persona_type": content.get("metadata", {}).get("persona_approach_used", ""),
                    "compliance_scan": compliance_scan,
                    "context_used": content.get("metadata", {}).get("context_used", []),
                    "confidence_score": content.get("metadata", {}).get("confidence_score", 0.7),
                    "tone": content.get("tone", "formal"),
                    "research_informed": content.get("research_informed", False),
                },
                "created_at": now_iso,
                "updated_at": now_iso,
            }).execute()
            logger.info("[SCRIBE] Created email_drafts record: %s", draft_id)
        except Exception as e:
            logger.warning("[SCRIBE] Failed to insert email_drafts: %s", e)

        # 2. lead_memory_events INSERT (event_type: 'email_drafted')
        if lead_memory_id:
            try:
                db.table("lead_memory_events").insert({
                    "id": str(uuid4()),
                    "user_id": self.user_id,
                    "lead_id": lead_memory_id,
                    "event_type": "email_drafted",
                    "title": f"Draft: {content.get('subject', '')}",
                    "description": (
                        f"Outreach email drafted for {recipient_name} "
                        f"at {recipient_company}. "
                        f"Status: draft (awaiting user approval). "
                        f"Compliance: {'passed' if compliance_scan.get('passed') else 'flagged'}."
                    ),
                    "confidence": 0.9,
                    "source": "scribe_agent",
                    "metadata": {
                        "email_draft_id": draft_id,
                        "direction": "outbound",
                        "compliance_passed": compliance_scan.get("passed", True),
                        "compliance_flags": compliance_scan.get("flags", []),
                    },
                    "created_at": now_iso,
                }).execute()
            except Exception as e:
                logger.warning("[SCRIBE] Failed to insert lead_memory_events: %s", e)

        # 3. aria_activity INSERT
        try:
            db.table("aria_activity").insert({
                "id": str(uuid4()),
                "user_id": self.user_id,
                "activity_type": "email_drafted",
                "title": f"Draft ready: {content.get('subject', '')[:50]}",
                "description": (
                    f"Drafted email for {recipient_name} at {recipient_company}. "
                    f"Status: draft (review on /communications). "
                    f"Compliance: {len(compliance_scan.get('findings', []))} finding(s)."
                ),
                "metadata": {
                    "email_draft_id": draft_id,
                    "recipient": recipient_name,
                    "recipient_company": recipient_company,
                    "compliance_flags": compliance_scan.get("flags", []),
                },
                "created_at": now_iso,
            }).execute()
        except Exception as e:
            logger.warning("[SCRIBE] Failed to insert aria_activity: %s", e)

    def _check_tool_connected(
        self,
        resource_status: list[dict[str, Any]],
        tool_name: str,
    ) -> bool:
        """Check if a specific tool is connected based on resource_status.

        Args:
            resource_status: List of resource status dicts from the task.
            tool_name: Name of the tool to check (e.g., "exa").

        Returns:
            True if the tool is connected, False otherwise.
        """
        if not resource_status:
            return False

        tool_lower = tool_name.lower()
        for resource in resource_status:
            tool = resource.get("tool", "").lower()
            if tool == tool_lower and resource.get("connected", False):
                return True

        return False

    def _get_builtin_templates(self) -> dict[str, str]:
        """Get built-in communication templates.

        Returns:
            Dictionary of template name to template string.
        """
        return {
            "follow_up_email": (
                "Hi {name},\n\n"
                "I wanted to follow up on {meeting_topic}. "
                "I hope you found our discussion valuable.\n\n"
                "Please let me know if you have any questions or would like to schedule a follow-up.\n\n"
                "Best regards"
            ),
            "meeting_request": (
                "Hi {name},\n\n"
                "I would like to schedule a meeting to {purpose}. "
                "Would you have time this week or next?\n\n"
                "Please let me know your availability.\n\n"
                "Best regards"
            ),
            "introduction": (
                "Hi {name},\n\n"
                "I'm {sender_name} from {company}. "
                "I'm reaching out because {reason}.\n\n"
                "I'd love to connect and discuss how we might work together.\n\n"
                "Best regards"
            ),
            "thank_you": (
                "Hi {name},\n\n"
                "Thank you for {reason}. "
                "I really appreciate your time and {detail}.\n\n"
                "Best regards"
            ),
        }

    def _register_tools(self) -> dict[str, Any]:
        """Register Scribe agent's drafting tools.

        Returns:
            Dictionary mapping tool names to callable functions.
        """
        return {
            "draft_email": self._draft_email,
            "draft_document": self._draft_document,
            "personalize": self._personalize,
            "apply_template": self._apply_template,
            "research_recipient": self._research_recipient,
            "explain_choices": self._explain_choices,
        }

    def validate_input(self, task: dict[str, Any]) -> bool:
        """Validate draft task input.

        Args:
            task: Task specification to validate.

        Returns:
            True if valid, False otherwise.
        """
        # Required fields
        if "communication_type" not in task:
            return False

        if "goal" not in task:
            return False

        # Validate communication_type
        comm_type = task["communication_type"]
        if comm_type not in self.VALID_COMMUNICATION_TYPES:
            return False

        # Validate tone if present
        if "tone" in task:
            tone = task["tone"]
            if tone not in self.VALID_TONES:
                return False

        # Validate recipient if present
        if "recipient" in task and task["recipient"] is not None:
            recipient = task["recipient"]
            if not isinstance(recipient, dict):
                return False

        return True

    async def draft_lead_outreach(
        self,
        recipient_name: str,
        recipient_title: str,
        recipient_email: str,
        company_name: str,
        signal_hook: str,
        fit_analysis: str,
        lead_id: str,
        recipient_linkedin: str = "",
        company_domain: str = "",
    ) -> dict[str, Any]:
        """Draft a signal-first outreach email for a lead-gen contact.

        Uses the full Scribe pipeline: persona mapping, Exa research,
        cold memory, ELITE_EMAIL_FRAMEWORK, compliance scan, and memory
        tracking. The signal_hook becomes the literal first-sentence opener.

        Args:
            recipient_name: Contact's full name.
            recipient_title: Contact's job title.
            recipient_email: Contact's email address.
            company_name: Target company name.
            signal_hook: The trigger event — used as email opener.
            fit_analysis: ICP fit analysis text.
            lead_id: discovered_lead ID to link drafts to.
            recipient_linkedin: Optional LinkedIn URL for Exa research.
            company_domain: Optional company domain.

        Returns:
            Dict with subject, body, compliance_scan, metadata.

        Raises:
            Exception: Propagated if the entire pipeline fails.
        """
        recipient = {
            "name": recipient_name,
            "title": recipient_title,
            "email": recipient_email,
            "company": company_name,
            "linkedin_url": recipient_linkedin,
        }

        # 1. Load outreach intelligence (persona, trigger events, company facts)
        outreach_intel = await self._load_outreach_intelligence(
            recipient=recipient,
            lead_memory_id=lead_id,
        )
        persona_approach = outreach_intel.get("persona_approach", "")
        company_facts = outreach_intel.get("company_facts", [])

        # 2. Build context with signal-first framing
        context_parts = []
        if signal_hook:
            context_parts.append(
                f"CRITICAL — Use this signal as the email opener (first sentence): {signal_hook}"
            )
        if fit_analysis:
            context_parts.append(f"ICP fit analysis: {fit_analysis}")
        if company_facts:
            context_parts.append(
                f"Known facts about {company_name}: {'; '.join(company_facts[:3])}"
            )
        if company_domain:
            context_parts.append(f"Company domain: {company_domain}")

        context = "\n".join(context_parts)

        # 3. Determine tone from title
        title_lower = recipient_title.lower()
        if any(kw in title_lower for kw in ("ceo", "president", "chief", "svp", "vp")):
            tone = "formal"
        elif any(kw in title_lower for kw in ("procurement", "purchasing", "supply")):
            tone = "formal"
        else:
            tone = "formal"

        # 4. Build goal with signal-first instruction and brevity constraint
        goal = (
            f"Write a cold outreach email to {recipient_name} ({recipient_title}) "
            f"at {company_name}. "
            f"The FIRST SENTENCE must reference this signal event: '{signal_hook}'. "
            f"Do NOT start with 'I hope this email finds you well', 'My name is', "
            f"or 'I wanted to reach out'. "
            f"Keep the entire email between 150-200 words. "
            f"End with a single, specific call to action."
        )

        # 5. Draft via the full Scribe pipeline
        draft_result = await self._draft_email(
            recipient=recipient,
            context=context,
            goal=goal,
            tone=tone,
            persona_approach=persona_approach,
        )

        subject = draft_result.get("subject", f"Regarding {company_name}")
        body = draft_result.get("body", "")

        # 6. Run compliance scan
        compliance_scan = self._run_compliance_scan(
            subject=subject,
            body=body,
            recipient=recipient,
        )

        # 7. Track in memory (email_drafts, lead_memory_events, aria_activity)
        await self._track_outreach_in_memory(
            content=draft_result,
            recipient=recipient,
            compliance_scan=compliance_scan,
            lead_memory_id=lead_id,
        )

        return {
            "subject": subject,
            "body": body,
            "compliance_scan": compliance_scan,
            "metadata": draft_result.get("metadata", {}),
            "source": "lead_gen_scribe",
        }

    async def execute(self, task: dict[str, Any]) -> AgentResult:
        """Execute the draft task.

        Orchestrates the full drafting workflow:
        1. Determine communication type
        2. Apply template if specified
        3. Draft the content
        4. Personalize with Digital Twin style
        5. Return draft ready for review

        Args:
            task: Task specification with:
                - communication_type: "email", "document", "message"
                - recipient: Optional recipient info
                - context: Background context
                - goal: What to achieve
                - tone: "formal", "friendly", "urgent"
                - template_name: Optional template to use
                - style: Optional Digital Twin style

        Returns:
            AgentResult with drafted content.
        """
        # OODA ACT: Log skill consideration before native execution
        await self._log_skill_consideration()

        # Extract team intelligence for LLM enrichment (optional, fail-open)
        self._team_intelligence: str = task.get("team_intelligence", "")

        # Extract resource_status for graceful degradation
        resource_status = task.get("resource_status", [])
        self._resource_status = resource_status

        # Check if Exa (for optional recipient research) is available
        exa_available = settings.EXA_API_KEY or self._check_tool_connected(resource_status, "exa")

        comm_type = task["communication_type"]
        recipient = task.get("recipient")
        context = task.get("context", "")
        goal = task.get("goal", "")
        tone = task.get("tone", "formal")
        template_name = task.get("template_name")
        style = task.get("style")
        lead_memory_id = task.get("lead_memory_id")

        # Load outreach intelligence from skill knowledge (fail-open)
        outreach_intel: dict[str, Any] = {}
        if comm_type in ("email", "message"):
            try:
                outreach_intel = await self._load_outreach_intelligence(
                    recipient=recipient,
                    lead_memory_id=lead_memory_id,
                )
                # Enrich context with outreach intelligence
                if outreach_intel.get("trigger_context"):
                    context = f"{context}\n\n{outreach_intel['trigger_context']}"
                if outreach_intel.get("company_facts"):
                    facts_str = "\n".join(f"- {f}" for f in outreach_intel["company_facts"])
                    context = f"{context}\n\nCompany intelligence:\n{facts_str}"
            except Exception as e:
                logger.warning("[SCRIBE] Outreach intelligence loading failed: %s", e)

        logger.info(
            f"Starting draft for {comm_type}",
            extra={
                "communication_type": comm_type,
                "tone": tone,
                "has_template": template_name is not None,
                "has_style": style is not None,
                "exa_available": exa_available,
            },
        )

        template_used = None
        style_applied = None

        try:
            # Handle email or message types
            if comm_type in ("email", "message"):
                # Use template if specified
                if template_name:
                    variables = {
                        "name": recipient.get("name", "there") if recipient else "there",
                        "meeting_topic": context,
                        "purpose": goal,
                        "reason": context,
                    }
                    content_body = await self._apply_template(template_name, variables)

                    if content_body:
                        template_used = template_name
                        content = {
                            "subject": goal[:60] if goal else "Follow-up",
                            "body": content_body,
                            "recipient_name": recipient.get("name") if recipient else None,
                            "tone": tone,
                            "word_count": len(content_body.split()),
                            "has_call_to_action": True,
                        }
                    else:
                        # Fallback to regular draft
                        content = await self._draft_email(
                            recipient=recipient,
                            context=context,
                            goal=goal,
                            tone=tone,
                            style=style,
                            persona_approach=outreach_intel.get("persona_approach", ""),
                        )
                else:
                    content = await self._draft_email(
                        recipient=recipient,
                        context=context,
                        goal=goal,
                        tone=tone,
                        style=style,
                        persona_approach=outreach_intel.get("persona_approach", ""),
                    )

                draft_type = "email"

            # Handle document type
            elif comm_type == "document":
                document_type = task.get("document_type", "brief")
                content = await self._draft_document(
                    document_type=document_type,
                    context=context,
                    goal=goal,
                    tone=tone,
                    style=style,
                )
                draft_type = "document"

            else:
                # Fallback to email
                content = await self._draft_email(
                    recipient=recipient,
                    context=context,
                    goal=goal,
                    tone=tone,
                    style=style,
                )
                draft_type = "email"

            # Apply personalization if style provided
            if style and "body" in content:
                content["body"] = await self._personalize(content["body"], style)
                style_applied = "custom"

            # Run compliance scan on email drafts (fail-open)
            compliance_scan: dict[str, Any] = {}
            if draft_type == "email" and content.get("body"):
                try:
                    compliance_scan = self._run_compliance_scan(
                        subject=content.get("subject", ""),
                        body=content["body"],
                        recipient=recipient,
                    )
                    # Store scan in content metadata
                    content_meta = content.get("metadata", {})
                    content_meta["compliance_scan"] = compliance_scan
                    content_meta["persona_approach_used"] = outreach_intel.get(
                        "persona_approach", ""
                    )[:100]
                    content["metadata"] = content_meta
                except Exception as e:
                    logger.warning("[SCRIBE] Compliance scan failed: %s", e)

            # Track outreach in memory (email_drafts, lead_memory_events, aria_activity)
            # NEVER auto-send — draft only, user approves on /communications
            if draft_type == "email" and content.get("body"):
                try:
                    await self._track_outreach_in_memory(
                        content=content,
                        recipient=recipient,
                        compliance_scan=compliance_scan,
                        lead_memory_id=lead_memory_id,
                    )
                except Exception as e:
                    logger.warning("[SCRIBE] Outreach tracking failed: %s", e)

            # Build advisories for any degraded capabilities
            advisories: list[str] = []
            if not exa_available and recipient:
                advisories.append(
                    "Recipient research skipped - Exa web search not connected. "
                    "Connect Exa in Settings > Integrations for personalized recipient insights."
                )
            if compliance_scan and not compliance_scan.get("passed", True):
                advisories.append(
                    f"Compliance scan flagged {compliance_scan.get('finding_count', 0)} issue(s): "
                    f"{', '.join(compliance_scan.get('flags', []))}. "
                    "Review findings before sending."
                )

            result_data = {
                "draft_type": draft_type,
                "content": content,
                "metadata": content.get("metadata", {}),
                "style_applied": style_applied,
                "template_used": template_used,
                "ready_for_review": True,
            }
            if advisories:
                result_data["advisories"] = advisories

            logger.info(
                f"Draft complete: {draft_type}",
                extra={
                    "draft_type": draft_type,
                    "word_count": content.get("word_count", 0),
                },
            )

            return AgentResult(success=True, data=result_data)

        except Exception as e:
            logger.error(f"Draft failed: {e}", extra={"error": str(e)})
            return AgentResult(
                success=False,
                data={},
                error=str(e),
            )

    async def _draft_email(
        self,
        recipient: dict[str, Any] | None = None,
        context: str = "",
        goal: str = "",
        tone: str = "formal",
        style: dict[str, Any] | None = None,
        persona_approach: str = "",
    ) -> dict[str, Any]:
        """Draft an email using LLM generation with template fallback.

        Builds a detailed prompt for Claude to generate a professional email
        tailored to the life sciences commercial context. Falls back to
        template-based generation if the LLM call fails.

        Now includes optional recipient research via Exa for personalized context.

        Args:
            recipient: Recipient information with name, title, company.
            context: Background context for the email.
            goal: What this email should achieve.
            tone: Tone of the email (formal, friendly, urgent).
            style: Optional Digital Twin style hints for the LLM.
            persona_approach: Persona-specific messaging instructions from skill knowledge.

        Returns:
            Drafted email with subject, body, and metadata.
        """
        recipient_name = "there"
        recipient_company = ""
        recipient_title = ""
        recipient_research: dict[str, Any] | None = None

        if recipient:
            recipient_name = recipient.get("name", "there")
            recipient_company = recipient.get("company", "")
            recipient_title = recipient.get("title", "")

            # Research recipient for personalized context
            if recipient_name != "there":
                try:
                    recipient_research = await self._research_recipient(recipient)
                except Exception as e:
                    logger.warning(f"Recipient research failed: {e}")

        # Retrieve cold memory context about the recipient
        memory_context = ""
        memory_sources: list[str] = []
        if recipient_name != "there":
            try:
                memory_context, memory_sources = await self._retrieve_recipient_context(
                    recipient_name=recipient_name,
                    recipient_company=recipient_company,
                )
            except Exception as e:
                logger.warning(f"Recipient context retrieval failed: {e}")

        logger.info(
            f"Drafting email to {recipient_name}",
            extra={
                "recipient": recipient_name,
                "tone": tone,
                "goal": goal[:50] if goal else "",
                "has_research": recipient_research is not None,
                "has_memory_context": bool(memory_context),
            },
        )

        # Build LLM prompt
        recipient_info_parts = [f"Name: {recipient_name}"]
        if recipient_title:
            recipient_info_parts.append(f"Title: {recipient_title}")
        if recipient_company:
            recipient_info_parts.append(f"Company: {recipient_company}")

        # Add research context if available (wrapped as external data for security)
        if recipient_research:
            research_parts: list[str] = []
            if recipient_research.get("bio"):
                research_parts.append(f"Background: {recipient_research['bio'][:300]}")
            if recipient_research.get("recent_news"):
                news_items = recipient_research["recent_news"][:2]
                news_summary = "; ".join([n.get("title", "") for n in news_items])
                research_parts.append(f"Recent Company News: {news_summary}")
            if recipient_research.get("linkedin_url"):
                research_parts.append(f"LinkedIn: {recipient_research['linkedin_url']}")
            if research_parts:
                recipient_info_parts.append(
                    wrap_external_data("\n".join(research_parts), "exa_people_search")
                )

        # Add ARIA memory context if available
        if memory_context:
            recipient_info_parts.append(
                f"\nARIA's memory about this person:\n{memory_context}\n"
                "Include relevant context naturally - mention shared history the user might forget."
            )

        recipient_info = "\n".join(recipient_info_parts)

        style_hints = ""
        if style:
            style_parts = []
            if "preferred_greeting" in style:
                style_parts.append(f"- Use greeting style: {style['preferred_greeting']}")
            if "formality" in style:
                style_parts.append(f"- Formality level: {style['formality']}")
            if "signature" in style:
                style_parts.append(f"- Include signature: {style['signature']}")
            if style_parts:
                style_hints = "\n\nWriting style preferences:\n" + "\n".join(style_parts)

        # Build persona approach section from outreach intelligence
        persona_section = ""
        if persona_approach:
            persona_section = f"\n\nMessaging approach:\n{persona_approach}\n"

        # Build team intelligence section if available (fail-open)
        team_intel_section = ""
        try:
            team_intel = getattr(self, "_team_intelligence", "")
            if team_intel:
                team_intel_section = f"\n\n{team_intel}\n"
        except Exception:
            pass

        prompt = (
            f"Draft a professional email for a life sciences commercial team member.\n\n"
            f"Recipient:\n{recipient_info}\n\n"
            f"Context: {context}\n\n"
            f"Goal: {goal}\n\n"
            f"Tone: {tone}\n"
            f"{style_hints}"
            f"{persona_section}"
            f"{team_intel_section}\n\n"
            f"Requirements:\n"
            f"- Keep the email concise and professional\n"
            f"- Include a clear call to action\n"
            f"- Match the requested tone ({tone})\n"
            f"- Do NOT use emojis\n"
            f"- Use specific details from the context, not generic placeholders\n"
            f"- Reference the recipient's background or recent news if provided\n\n"
            f"Respond with JSON only:\n"
            f'{{"subject": "email subject line", "body": "full email body text", '
            f'"tone_notes": "brief note on tone choices made", '
            f'"confidence": 0.0, '
            f'"alternatives": [{{"approach": "brief description", "rationale": "why this might work"}}]}}'
        )

        hardcoded_prompt = (
            "You are a professional email writer for life sciences commercial teams. "
            "You write clear, persuasive, and appropriately-toned emails that drive "
            "action. Your emails are concise, avoid jargon overload, and always include "
            "a clear next step or call to action. Respond with valid JSON only."
        )

        # Use PersonaBuilder when available, fall back to hardcoded prompt
        system_prompt = await self._get_persona_system_prompt(
            task_description=f"Draft {tone} email about: {goal[:80]}",
            output_format="json",
            include_relationship=bool(recipient_name != "there"),
            recipient_name=recipient_name if recipient_name != "there" else None,
            account_name=recipient_company or None,
        ) or hardcoded_prompt
        system_prompt = ELITE_EMAIL_FRAMEWORK + "\n\n" + system_prompt

        try:
            response = await self.llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=system_prompt,
                max_tokens=1024,
                temperature=0.7,
                user_id=self.user_id,
                task=TaskType.SCRIBE_DRAFT_EMAIL,
                agent_id="scribe",
            )

            parsed = _extract_json_from_text(response)

            subject = parsed.get("subject", goal[:60] if goal else "Follow-up")
            body = parsed.get("body", "")

            if not body:
                raise ValueError("LLM returned empty email body")

            word_count = len(body.split())

            # Detect call to action heuristically
            cta_indicators = [
                "let me know",
                "schedule",
                "call",
                "meeting",
                "reply",
                "respond",
                "reach out",
                "follow up",
                "available",
                "discuss",
                "connect",
                "touch base",
                "your thoughts",
            ]
            body_lower = body.lower()
            has_cta = any(indicator in body_lower for indicator in cta_indicators)

            logger.info(
                "Email drafted via LLM",
                extra={"word_count": word_count, "tone": tone},
            )

            return {
                "subject": subject,
                "body": body,
                "recipient_name": recipient_name if recipient else None,
                "recipient_company": recipient_company if recipient_company else None,
                "tone": tone,
                "word_count": word_count,
                "has_call_to_action": has_cta,
                "research_informed": recipient_research is not None,
                "metadata": {
                    "confidence_score": parsed.get("confidence", 0.7),
                    "context_used": [
                        s
                        for s in [
                            "persona_builder" if system_prompt != hardcoded_prompt else None,
                            "exa_research" if recipient_research else None,
                            "cold_memory" if memory_context else None,
                        ]
                        if s
                    ],
                    "alternatives": parsed.get("alternatives", []),
                    "persona_layers_used": system_prompt != hardcoded_prompt,
                },
            }

        except Exception as e:
            logger.warning(
                f"LLM email generation failed, falling back to template: {e}",
                extra={"error": str(e)},
            )
            return self._draft_email_fallback(
                recipient=recipient,
                recipient_name=recipient_name,
                recipient_company=recipient_company,
                context=context,
                goal=goal,
                tone=tone,
            )

    async def _research_recipient(
        self,
        recipient: dict[str, Any],
    ) -> dict[str, Any]:
        """Research a recipient for personalized email context.

        Uses Exa search_person for bio/LinkedIn info and search_news
        for company context.

        Args:
            recipient: Recipient info with name and optionally company.

        Returns:
            Dict with bio, linkedin_url, and recent_news.
        """
        name = recipient.get("name", "")
        company = recipient.get("company", "")

        if not name:
            return {}

        logger.info(f"Researching recipient: {name} at {company}")

        exa = self._get_exa_provider()
        if not exa:
            logger.warning("ExaEnrichmentProvider not available for recipient research")
            return {}

        result: dict[str, Any] = {}

        try:
            # Get person enrichment
            enrichment = await exa.search_person(name=name, company=company)

            if enrichment.bio:
                result["bio"] = enrichment.bio[:500]
            if enrichment.linkedin_url:
                result["linkedin_url"] = enrichment.linkedin_url
            if enrichment.title:
                result["verified_title"] = enrichment.title

        except Exception as e:
            logger.warning(f"Person search failed for {name}: {e}")

        # Get company news if company is known
        if company:
            try:
                news_results = await exa.search_news(
                    query=f"{company} news announcement",
                    num_results=5,
                    days_back=30,
                )

                if news_results:
                    result["recent_news"] = [
                        {
                            "title": n.title,
                            "url": n.url,
                            "date": n.published_date,
                        }
                        for n in news_results[:3]
                    ]

            except Exception as e:
                logger.warning(f"Company news search failed for {company}: {e}")

        logger.info(
            f"Recipient research complete for {name}",
            extra={
                "has_bio": bool(result.get("bio")),
                "has_linkedin": bool(result.get("linkedin_url")),
                "news_count": len(result.get("recent_news", [])),
            },
        )

        return result

    async def _retrieve_recipient_context(
        self,
        recipient_name: str,
        recipient_company: str = "",
    ) -> tuple[str, list[str]]:
        """Retrieve ARIA's memory about a recipient for email personalization.

        Uses cold memory retrieval to find entity context and general
        memories about the recipient.

        Args:
            recipient_name: Name of the recipient.
            recipient_company: Optional company name for broader context.

        Returns:
            Tuple of (formatted context string, list of source types used).
            Returns ("", []) if no cold_retriever or on failure.
        """
        if self._cold_retriever is None:
            return ("", [])

        context_parts: list[str] = []
        sources: list[str] = []

        try:
            # Entity-centric retrieval for structured facts
            entity_ctx = await self._cold_retriever.retrieve_for_entity(
                user_id=self.user_id,
                entity_id=recipient_name,
                hops=2,
            )
            if entity_ctx.direct_facts:
                facts = [r.content for r in entity_ctx.direct_facts[:5]]
                context_parts.append("Known facts:\n- " + "\n- ".join(facts))
                sources.append("entity_facts")
            if entity_ctx.relationships:
                rels = [r.content for r in entity_ctx.relationships[:3]]
                context_parts.append("Relationships:\n- " + "\n- ".join(rels))
                sources.append("entity_relationships")
            if entity_ctx.recent_interactions:
                interactions = [r.content for r in entity_ctx.recent_interactions[:3]]
                context_parts.append("Recent interactions:\n- " + "\n- ".join(interactions))
                sources.append("recent_interactions")
        except Exception as e:
            logger.debug(f"Entity context retrieval failed for {recipient_name}: {e}")

        try:
            # General query-based retrieval
            query = recipient_name
            if recipient_company:
                query = f"{recipient_name} {recipient_company}"
            results = await self.cold_retrieve(query=query, limit=5)
            if results:
                memories = [r["content"] for r in results if r.get("content")]
                if memories:
                    context_parts.append("Related memories:\n- " + "\n- ".join(memories[:5]))
                    sources.append("cold_memory")
        except Exception as e:
            logger.debug(f"Cold memory retrieval failed for {recipient_name}: {e}")

        formatted = "\n\n".join(context_parts) if context_parts else ""
        return (formatted, sources)

    async def _explain_choices(
        self,
        draft_metadata: dict[str, Any],
        question: str = "",
    ) -> dict[str, Any]:
        """Explain the context and style choices made in a draft.

        Reads metadata from a draft output and builds a human-readable
        explanation of what context sources were used. Optionally answers
        a specific question about the draft using a lightweight LLM call.

        Args:
            draft_metadata: Metadata dict from a draft output.
            question: Optional specific question to answer about the draft.

        Returns:
            Dict with explanation, style_references, and context_references.
        """
        context_used = draft_metadata.get("context_used", [])
        confidence = draft_metadata.get("confidence_score", 0.7)
        alternatives = draft_metadata.get("alternatives", [])

        # Build human-readable explanation
        explanation_parts: list[str] = []

        if "persona_builder" in context_used:
            explanation_parts.append(
                "Used your Digital Twin writing style for tone and voice matching."
            )
        if "cold_memory" in context_used:
            explanation_parts.append(
                "Retrieved past interactions and facts about the recipient from ARIA's memory."
            )
        if "exa_research" in context_used:
            explanation_parts.append(
                "Researched the recipient's background and recent company news via web search."
            )

        if not explanation_parts:
            explanation_parts.append("Used default professional writing style (no personalization context available).")

        if confidence < 0.5:
            explanation_parts.append(
                f"Confidence is relatively low ({confidence:.0%}) - you may want to review carefully."
            )

        explanation = " ".join(explanation_parts)

        result: dict[str, Any] = {
            "explanation": explanation,
            "style_references": ["persona_builder"] if "persona_builder" in context_used else [],
            "context_references": [s for s in context_used if s != "persona_builder"],
        }

        if alternatives:
            result["alternatives"] = alternatives

        # If a specific question is asked, use a lightweight LLM call
        if question:
            try:
                prompt = (
                    f"The user drafted a communication. Here is the metadata about how it was created:\n"
                    f"- Context sources: {', '.join(context_used) or 'none'}\n"
                    f"- Confidence: {confidence:.0%}\n"
                    f"- Alternatives considered: {len(alternatives)}\n\n"
                    f"User question: {question}\n\n"
                    f"Answer briefly and directly."
                )
                answer = await self.llm.generate_response(
                    messages=[{"role": "user", "content": prompt}],
                    max_tokens=256,
                    temperature=0.3,
                    user_id=self.user_id,
                    task=TaskType.SCRIBE_CLASSIFY_EMAIL,
                    agent_id="scribe",
                )
                result["answer"] = answer
            except Exception as e:
                logger.warning(f"LLM call for explain_choices question failed: {e}")
                result["answer"] = f"Could not answer: {e}"

        return result

    def _draft_email_fallback(
        self,
        recipient: dict[str, Any] | None = None,
        recipient_name: str = "there",
        recipient_company: str = "",
        context: str = "",
        goal: str = "",
        tone: str = "formal",
    ) -> dict[str, Any]:
        """Template-based email fallback when LLM generation fails.

        Args:
            recipient: Original recipient dict.
            recipient_name: Extracted recipient name.
            recipient_company: Extracted recipient company.
            context: Background context for the email.
            goal: What this email should achieve.
            tone: Tone of the email (formal, friendly, urgent).

        Returns:
            Drafted email with subject, body, and metadata.
        """
        # Generate greeting based on tone
        if tone == "formal":
            greeting = f"Dear {recipient_name},"
        elif tone == "friendly":
            greeting = f"Hi {recipient_name},"
        else:  # urgent
            greeting = f"Dear {recipient_name},"

        # Generate subject based on tone and goal
        if tone == "urgent":
            subject = f"Urgent: {goal[:50]}" if goal else "Urgent: Action Required"
        else:
            subject = goal[:60] if goal else "Follow-up"

        # Generate body
        context_line = f"\n\n{context}" if context else ""

        if tone == "urgent":
            urgency_note = (
                "\n\nThis requires your immediate attention. Please respond as soon as possible."
            )
        else:
            urgency_note = ""

        # Generate call to action
        cta = "\n\nPlease let me know your availability to discuss further."

        # Closing based on tone
        if tone == "formal":
            closing = "\n\nBest regards"
        elif tone == "friendly":
            closing = "\n\nThanks!"
        else:  # urgent
            closing = "\n\nThank you for your prompt attention to this matter."

        body = f"{greeting}{context_line}{urgency_note}{cta}{closing}"

        word_count = len(body.split())

        return {
            "subject": subject,
            "body": body,
            "recipient_name": recipient_name if recipient else None,
            "recipient_company": recipient_company if recipient_company else None,
            "tone": tone,
            "word_count": word_count,
            "has_call_to_action": True,
        }

    async def _draft_document(
        self,
        document_type: str = "brief",
        context: str = "",
        goal: str = "",
        tone: str = "formal",
        style: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Draft a document using LLM generation with template fallback.

        Builds a detailed prompt for Claude to generate a complete document
        with structured sections. Falls back to template-based generation
        if the LLM call fails.

        Args:
            document_type: Type of document (brief, report, proposal).
            context: Background context for the document.
            goal: What this document should achieve.
            tone: Tone of the document.
            style: Optional Digital Twin style hints for the LLM.

        Returns:
            Drafted document with title, body, sections, and metadata.
        """
        logger.info(
            f"Drafting {document_type} document",
            extra={
                "document_type": document_type,
                "tone": tone,
                "goal": goal[:50] if goal else "",
            },
        )

        # Build section guidance based on document type
        if document_type == "brief":
            section_guidance = (
                "Create a concise brief with 2-3 sections. Suggested sections: "
                "Summary, Key Points, and optionally Recommendations. "
                "Keep it under 300 words total."
            )
        elif document_type == "report":
            section_guidance = (
                "Create a detailed report with 3-5 sections. Suggested sections: "
                "Executive Summary, Background, Analysis, Findings, and Recommendations. "
                "Be thorough but focused."
            )
        elif document_type == "proposal":
            section_guidance = (
                "Create a persuasive proposal with 3-5 sections. Suggested sections: "
                "Introduction, Proposed Solution, Benefits, Implementation Plan, and Next Steps. "
                "Focus on value and feasibility."
            )
        else:
            section_guidance = (
                f"Create a {document_type} document with appropriate sections. "
                "Use clear headings and structured content."
            )

        # Retrieve cold memory context for the document topic
        doc_memory_context = ""
        doc_memory_sources: list[str] = []
        try:
            results = await self.cold_retrieve(query=f"{context} {goal}", limit=5)
            if results:
                memories = [r["content"] for r in results if r.get("content")]
                if memories:
                    doc_memory_context = "\n- ".join(memories[:5])
                    doc_memory_sources.append("cold_memory")
        except Exception as e:
            logger.debug(f"Cold memory retrieval for document failed: {e}")

        style_hints = ""
        if style:
            style_parts = []
            if "formality" in style:
                style_parts.append(f"- Formality level: {style['formality']}")
            if style_parts:
                style_hints = "\n\nWriting style preferences:\n" + "\n".join(style_parts)

        memory_section = ""
        if doc_memory_context:
            memory_section = (
                f"\n\nRelevant context from ARIA's memory:\n- {doc_memory_context}\n"
                "Incorporate relevant facts naturally into the document."
            )

        prompt = (
            f"Create a {document_type} document for a life sciences commercial team.\n\n"
            f"Context: {context}\n\n"
            f"Goal/Purpose: {goal}\n\n"
            f"Tone: {tone}\n\n"
            f"Document structure guidance:\n{section_guidance}\n"
            f"{style_hints}"
            f"{memory_section}\n\n"
            f"Requirements:\n"
            f"- Use specific details from the context provided\n"
            f"- Do NOT use placeholder text or generic filler\n"
            f"- Do NOT use emojis\n"
            f"- Write in a professional life sciences commercial voice\n\n"
            f"Respond with JSON only:\n"
            f'{{"title": "document title", "body": "full document body as markdown text", '
            f'"sections": [{{"heading": "Section Title", "content": "section content"}}], '
            f'"confidence": 0.0, '
            f'"alternatives": [{{"approach": "brief description", "rationale": "why this might work"}}]}}'
        )

        hardcoded_prompt = (
            "You are a professional document writer for life sciences commercial teams. "
            "You create clear, well-structured documents that inform and drive decisions. "
            "Your writing is precise, evidence-based, and uses appropriate industry terminology "
            "without being overly jargon-heavy. Respond with valid JSON only."
        )

        # Use PersonaBuilder when available, fall back to hardcoded prompt
        system_prompt = await self._get_persona_system_prompt(
            task_description=f"Draft {document_type} document about: {goal[:80]}",
            output_format="json",
        ) or hardcoded_prompt

        try:
            response = await self.llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=system_prompt,
                max_tokens=2048,
                temperature=0.7,
                user_id=self.user_id,
                task=TaskType.SCRIBE_DRAFT_EMAIL,
                agent_id="scribe",
            )

            parsed = _extract_json_from_text(response)

            title = parsed.get("title", goal if goal else f"{document_type.capitalize()} Document")
            sections = parsed.get("sections", [])
            body = parsed.get("body", "")

            if not sections and not body:
                raise ValueError("LLM returned empty document")

            # If we have sections but no body, build body from sections
            if sections and not body:
                body_parts = []
                for section in sections:
                    heading = section.get("heading", "Section")
                    section_content = section.get("content", "")
                    body_parts.append(f"## {heading}\n\n{section_content}")
                body = "\n\n".join(body_parts)

            # If we have body but no sections, it's still valid
            if not sections and body:
                sections = [{"heading": "Content", "content": body}]

            word_count = len(body.split())

            logger.info(
                "Document drafted via LLM",
                extra={
                    "document_type": document_type,
                    "word_count": word_count,
                    "section_count": len(sections),
                },
            )

            return {
                "title": title,
                "body": body,
                "sections": sections,
                "document_type": document_type,
                "word_count": word_count,
                "tone": tone,
                "metadata": {
                    "confidence_score": parsed.get("confidence", 0.7),
                    "context_used": [
                        s
                        for s in [
                            "persona_builder" if system_prompt != hardcoded_prompt else None,
                            "cold_memory" if doc_memory_context else None,
                        ]
                        if s
                    ],
                    "alternatives": parsed.get("alternatives", []),
                    "persona_layers_used": system_prompt != hardcoded_prompt,
                },
            }

        except Exception as e:
            logger.warning(
                f"LLM document generation failed, falling back to template: {e}",
                extra={"error": str(e)},
            )
            return self._draft_document_fallback(
                document_type=document_type,
                context=context,
                goal=goal,
                tone=tone,
            )

    def _draft_document_fallback(
        self,
        document_type: str = "brief",
        context: str = "",
        goal: str = "",
        tone: str = "formal",
    ) -> dict[str, Any]:
        """Template-based document fallback when LLM generation fails.

        Args:
            document_type: Type of document (brief, report, proposal).
            context: Background context for the document.
            goal: What this document should achieve.
            tone: Tone of the document.

        Returns:
            Drafted document with title, body, sections, and metadata.
        """
        # Generate title from goal
        title = goal if goal else f"{document_type.capitalize()} Document"

        # Generate sections based on document type
        if document_type == "brief":
            sections = [
                {"heading": "Summary", "content": context if context else "Summary content here."},
                {"heading": "Key Points", "content": "- Point 1\n- Point 2\n- Point 3"},
            ]
        elif document_type == "report":
            sections = [
                {
                    "heading": "Executive Summary",
                    "content": context if context else "Executive summary.",
                },
                {"heading": "Background", "content": "Background information and context."},
                {"heading": "Analysis", "content": "Detailed analysis of the situation."},
                {"heading": "Recommendations", "content": "Recommended actions moving forward."},
            ]
        elif document_type == "proposal":
            sections = [
                {
                    "heading": "Introduction",
                    "content": context if context else "Introduction to the proposal.",
                },
                {"heading": "Proposed Solution", "content": "Details of the proposed solution."},
                {"heading": "Benefits", "content": "Expected benefits and outcomes."},
                {"heading": "Next Steps", "content": "Proposed next steps and timeline."},
            ]
        else:
            sections = [
                {"heading": "Content", "content": context if context else "Document content."},
            ]

        # Build body from sections
        body_parts = []
        for section in sections:
            body_parts.append(f"## {section['heading']}\n\n{section['content']}")
        body = "\n\n".join(body_parts)

        word_count = len(body.split())

        return {
            "title": title,
            "body": body,
            "sections": sections,
            "document_type": document_type,
            "word_count": word_count,
            "tone": tone,
        }

    async def _personalize(
        self,
        content: str,
        style: dict[str, Any] | None = None,
    ) -> str:
        """Personalize content to match a writing style.

        Applies Digital Twin style parameters to the content.
        In production, this would use the LLM for more sophisticated style matching.

        Currently supported style parameters:
            - signature: str - Appended to content if not already present
            - preferred_greeting: str - Replaces common greetings (Dear, Hello, Hi, Hey)

        Future LLM-based parameters (not yet implemented):
            - formality: "formal", "casual" - Adjusts overall tone
            - contractions: bool - Expands/contracts phrases

        Args:
            content: The content to personalize.
            style: Style parameters from Digital Twin.

        Returns:
            Personalized content matching the style.
        """
        if not style:
            return content

        logger.info(
            "Personalizing content with style",
            extra={"style_keys": list(style.keys())},
        )

        result = content

        # Apply greeting preference
        if "preferred_greeting" in style:
            preferred = style["preferred_greeting"]
            # Replace common greetings with preferred one
            greetings = ["Dear", "Hello", "Hi", "Hey"]
            for greeting in greetings:
                if result.startswith(f"{greeting} "):
                    result = result.replace(f"{greeting} ", f"{preferred} ", 1)
                    break

        # Apply signature
        if "signature" in style:
            sig = style["signature"]
            if sig not in result:
                result = f"{result}\n\n{sig}"

        return result

    async def _apply_template(
        self,
        template_name: str,
        variables: dict[str, Any],
    ) -> str:
        """Apply a template with variables.

        Substitutes variables into a named template.

        Args:
            template_name: Name of the template to use.
            variables: Variables to substitute in template.

        Returns:
            Rendered template content, or empty string if template not found.
        """
        if template_name not in self._templates:
            logger.warning(f"Template not found: {template_name}")
            return ""

        logger.info(
            f"Applying template: {template_name}",
            extra={"template": template_name, "variables": list(variables.keys())},
        )

        template = self._templates[template_name]

        # Substitute variables
        try:
            # Use str.format with partial substitution support
            result = template
            for key, value in variables.items():
                placeholder = "{" + key + "}"
                result = result.replace(placeholder, str(value))
            return result
        except KeyError as e:
            logger.warning(f"Missing variable in template: {e}")
            return template
