"""ScribeAgent module for ARIA.

Drafts emails and documents with style matching using Digital Twin.
Uses LLM generation as the primary drafting method with template-based
fallback for resilience.
"""

import json
import logging
import re
from typing import TYPE_CHECKING, Any

from src.agents.base import AgentResult
from src.agents.skill_aware_agent import SkillAwareAgent

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

        comm_type = task["communication_type"]
        recipient = task.get("recipient")
        context = task.get("context", "")
        goal = task.get("goal", "")
        tone = task.get("tone", "formal")
        template_name = task.get("template_name")
        style = task.get("style")

        logger.info(
            f"Starting draft for {comm_type}",
            extra={
                "communication_type": comm_type,
                "tone": tone,
                "has_template": template_name is not None,
                "has_style": style is not None,
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
                        )
                else:
                    content = await self._draft_email(
                        recipient=recipient,
                        context=context,
                        goal=goal,
                        tone=tone,
                        style=style,
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

            result_data = {
                "draft_type": draft_type,
                "content": content,
                "metadata": content.get("metadata", {}),
                "style_applied": style_applied,
                "template_used": template_used,
                "ready_for_review": True,
            }

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

        # Add research context if available
        if recipient_research:
            if recipient_research.get("bio"):
                recipient_info_parts.append(f"Background: {recipient_research['bio'][:300]}")
            if recipient_research.get("recent_news"):
                news_items = recipient_research["recent_news"][:2]
                news_summary = "; ".join([n.get("title", "") for n in news_items])
                recipient_info_parts.append(f"Recent Company News: {news_summary}")
            if recipient_research.get("linkedin_url"):
                recipient_info_parts.append(f"LinkedIn: {recipient_research['linkedin_url']}")

        # Add ARIA memory context if available
        if memory_context:
            recipient_info_parts.append(
                f"\nARIA's memory about this person:\n{memory_context}\n"
                "Include relevant context naturally — mention shared history the user might forget."
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

        try:
            response = await self.llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=system_prompt,
                max_tokens=1024,
                temperature=0.7,
                user_id=self.user_id,
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
                f"Confidence is relatively low ({confidence:.0%}) — you may want to review carefully."
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
