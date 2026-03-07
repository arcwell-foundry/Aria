"""
Context Enrichment Layer for Jarvis Intelligence.

Assembles ARIA's full institutional knowledge about the user's world
before any engine processes an event. This is the difference between
hallucinated insights and grounded intelligence.
"""

from __future__ import annotations

import logging
from typing import Any

from src.intelligence.regulatory_intelligence import detect_fda_event, format_regulatory_context
from src.intelligence.clinical_trial_intelligence import detect_clinical_trial_signal, format_clinical_trial_context
from src.intelligence.supply_chain_intelligence import detect_supply_chain_signal, format_supply_chain_context
from src.intelligence.pricing_intelligence import detect_pricing_signal, format_pricing_context
from src.intelligence.therapeutic_area_intelligence import (
    detect_therapeutic_area,
    detect_manufacturing_modality,
    format_therapeutic_context,
)
from src.intelligence.conference_intelligence import ConferenceIntelligenceEngine

logger = logging.getLogger(__name__)


class ContextEnricher:
    """Assembles ARIA's full knowledge about the user's world before engine processing."""

    def __init__(self, supabase_client: Any) -> None:
        self._db = supabase_client

    async def enrich_event_context(
        self,
        user_id: str,
        event: str,
        company_name: str,
        signal_type: str = "",
        existing_context: dict | None = None,
    ) -> dict:
        """
        Returns a rich context dict that every engine receives.

        This is called ONCE per event, before any engine runs.
        All engines share the same enriched context.
        """
        context = existing_context.copy() if existing_context else {}
        context["event"] = event
        context["company_name"] = company_name
        context["signal_type"] = signal_type

        try:
            # 1. User's company identity
            user_company = await self._get_user_company(user_id)
            context["user_company"] = user_company

            # 2. Entity classification: competitor, prospect, partner, or industry?
            entity_type = await self._classify_entity(company_name, user_id, user_company)
            context["entity_type"] = entity_type

            # 3. If competitor: pull full battle card
            if entity_type == "competitor":
                battle_card = await self._get_battle_card(company_name)
                if battle_card:
                    context["battle_card"] = battle_card

            # 4. Relevant semantic memories (about this company + event topic)
            memories = await self._search_semantic_memories(
                user_id, event, company_name, limit=8
            )
            if memories:
                context["relevant_memories"] = memories

            # 5. Recent signals for this company (pattern context)
            recent_signals = await self._get_recent_signals(
                user_id, company_name, limit=5
            )
            if recent_signals:
                context["company_recent_signals"] = recent_signals

            # 6. Active goals that might be affected
            active_goals = await self._get_active_goals(user_id)
            if active_goals:
                context["active_goals"] = active_goals

            # 7. Competitive landscape summary
            landscape = await self._get_competitive_landscape(user_id)
            if landscape:
                context["competitive_landscape"] = landscape

            # 8. Specialized signal detection
            fda_event = detect_fda_event(event, signal_type)
            if fda_event:
                context["fda_event"] = fda_event
                context["regulatory_context"] = format_regulatory_context(
                    fda_event, context.get("battle_card"), company_name
                )
                logger.info(
                    "[ContextEnricher] FDA event detected: %s (urgency: %s)",
                    fda_event['fda_event_type'], fda_event['urgency'],
                )

            clinical_trial = detect_clinical_trial_signal(event, signal_type)
            if clinical_trial:
                context["clinical_trial"] = clinical_trial
                context["clinical_trial_context"] = format_clinical_trial_context(
                    clinical_trial, company_name
                )
                logger.info(
                    "[ContextEnricher] Clinical trial detected: %s %s",
                    clinical_trial['clinical_phase'], clinical_trial['drug_modality'],
                )

            supply_chain = detect_supply_chain_signal(event, signal_type)
            if supply_chain:
                context["supply_chain_vulnerability"] = supply_chain
                context["supply_chain_context"] = format_supply_chain_context(
                    supply_chain, context.get("battle_card"), company_name
                )
                logger.info(
                    "[ContextEnricher] Supply chain vulnerability: %s (urgency: %s)",
                    supply_chain['vulnerability_type'], supply_chain['urgency'],
                )

            pricing_signal = detect_pricing_signal(event, signal_type)
            if pricing_signal:
                context["pricing_signal"] = pricing_signal
                context["pricing_context"] = format_pricing_context(
                    pricing_signal, context.get("battle_card"), company_name
                )
                logger.info(
                    "[ContextEnricher] Pricing signal: %s",
                    pricing_signal['primary_type'],
                )

            # Therapeutic area and manufacturing modality detection
            therapeutic_areas = detect_therapeutic_area(event)
            manufacturing_modalities = detect_manufacturing_modality(event)
            if therapeutic_areas or manufacturing_modalities:
                context["therapeutic_areas"] = therapeutic_areas
                context["manufacturing_modalities"] = manufacturing_modalities
                therapeutic_ctx = format_therapeutic_context(
                    therapeutic_areas, manufacturing_modalities
                )
                if therapeutic_ctx:
                    context["therapeutic_context"] = therapeutic_ctx
                logger.info(
                    "[ContextEnricher] Therapeutic: %s, Modalities: %s",
                    therapeutic_areas,
                    manufacturing_modalities,
                )

            # Conference mention detection
            try:
                conf_engine = ConferenceIntelligenceEngine(self._db)
                conf_mention = conf_engine.detect_conference_mention(event)
                if conf_mention:
                    context["conference"] = conf_mention
                    context["conference_context"] = (
                        conf_engine.format_conference_context(conf_mention)
                    )
                    logger.info(
                        "[ContextEnricher] Conference detected: %s",
                        conf_mention["conference_name"],
                    )
            except Exception as e:
                logger.warning(
                    "[ContextEnricher] Conference detection failed: %s", e
                )

            logger.info(
                "[ContextEnricher] Enriched context for '%s': "
                "entity_type=%s, "
                "battle_card=%s, "
                "memories=%d, "
                "signals=%d, "
                "goals=%d",
                company_name,
                entity_type,
                "yes" if context.get("battle_card") else "no",
                len(memories) if memories else 0,
                len(recent_signals) if recent_signals else 0,
                len(active_goals) if active_goals else 0,
            )

        except Exception as e:
            logger.error("[ContextEnricher] Error enriching context: %s", e)
            # Return partial context rather than failing completely

        return context

    async def _get_user_company(self, user_id: str) -> dict:
        """Get the user's company identity."""
        default = {"name": "Unknown", "domain": "", "industry": "life sciences"}
        try:
            result = (
                self._db.table("user_profiles")
                .select("company_id, role")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )

            if not result.data:
                return default

            company_id = result.data[0].get("company_id")
            if not company_id:
                return default

            company_result = (
                self._db.table("companies")
                .select("name, domain, industry, description")
                .eq("id", company_id)
                .limit(1)
                .execute()
            )

            if company_result.data:
                company = company_result.data[0]
                return {
                    "name": company.get("name", "Unknown"),
                    "domain": company.get("domain", ""),
                    "industry": company.get("industry") or "life sciences bioprocessing",
                    "description": company.get("description") or "",
                    "user_role": result.data[0].get("role", ""),
                }

            return default
        except Exception as e:
            logger.warning("[ContextEnricher] Failed to get user company: %s", e)
            return default

    async def _classify_entity(
        self, company_name: str, user_id: str, user_company: dict
    ) -> str:
        """
        Classify whether company_name is a competitor, prospect, partner,
        or industry entity.

        Returns: "competitor" | "prospect" | "partner" | "own_company"
                 | "industry" | "unknown"
        """
        if not company_name:
            return "unknown"

        # Check if it's the user's own company
        own_name = user_company.get("name", "").lower()
        target = company_name.lower()
        if own_name and (own_name in target or target in own_name):
            return "own_company"

        # Check battle_cards (competitors have battle cards)
        try:
            bc_result = (
                self._db.table("battle_cards")
                .select("competitor_name")
                .ilike("competitor_name", f"%{company_name}%")
                .limit(1)
                .execute()
            )
            if bc_result.data:
                return "competitor"
        except Exception:
            pass

        # Check monitored_entities for type hints
        try:
            me_result = (
                self._db.table("monitored_entities")
                .select("entity_type, entity_name")
                .eq("user_id", user_id)
                .ilike("entity_name", f"%{company_name}%")
                .limit(1)
                .execute()
            )
            if me_result.data:
                entity = me_result.data[0]
                etype = entity.get("entity_type", "").lower()
                if etype in ("competitor", "prospect", "partner"):
                    return etype
                # If monitored but type is generic, likely a competitor
                return "competitor"
        except Exception:
            pass

        # Check if it's a generic industry term
        industry_terms = [
            "life sciences industry",
            "bioprocessing",
            "pharmaceutical",
            "biotechnology",
            "biopharma",
            "industry",
        ]
        if any(term in target for term in industry_terms):
            return "industry"

        return "unknown"

    async def _get_battle_card(self, company_name: str) -> dict | None:
        """Get the full battle card for a competitor."""
        try:
            result = (
                self._db.table("battle_cards")
                .select("*")
                .ilike("competitor_name", f"%{company_name}%")
                .limit(1)
                .execute()
            )

            if result.data:
                card = result.data[0]
                return {
                    "competitor_name": card.get("competitor_name"),
                    "overview": card.get("overview"),
                    "strengths": card.get("strengths", []),
                    "weaknesses": card.get("weaknesses", []),
                    "differentiation": card.get("differentiation", []),
                    "pricing": card.get("pricing", {}),
                    "objection_handlers": card.get("objection_handlers", []),
                    "recent_news": card.get("recent_news", []),
                    "analysis": card.get("analysis", {}),
                }
            return None
        except Exception as e:
            logger.warning(
                "[ContextEnricher] Failed to get battle card for %s: %s",
                company_name,
                e,
            )
            return None

    async def _search_semantic_memories(
        self, user_id: str, _event: str, company_name: str, limit: int = 8
    ) -> list:
        """Get relevant semantic memories about this company and event."""
        try:
            result = (
                self._db.table("memory_semantic")
                .select("fact, confidence, source")
                .eq("user_id", user_id)
                .ilike("fact", f"%{company_name}%")
                .order("confidence", desc=True)
                .limit(limit)
                .execute()
            )

            if result.data:
                return [
                    {
                        "fact": m["fact"],
                        "confidence": m["confidence"],
                        "source": m["source"],
                    }
                    for m in result.data
                ]
            return []
        except Exception as e:
            logger.warning("[ContextEnricher] Failed to search memories: %s", e)
            return []

    async def _get_recent_signals(
        self, user_id: str, company_name: str, limit: int = 5
    ) -> list:
        """Get recent market signals for this company."""
        try:
            result = (
                self._db.table("market_signals")
                .select("headline, signal_type, detected_at, relevance_score")
                .eq("user_id", user_id)
                .eq("company_name", company_name)
                .order("detected_at", desc=True)
                .limit(limit)
                .execute()
            )

            if result.data:
                return [
                    {
                        "headline": s["headline"],
                        "signal_type": s["signal_type"],
                        "detected_at": s["detected_at"],
                        "relevance_score": s.get("relevance_score"),
                    }
                    for s in result.data
                ]
            return []
        except Exception as e:
            logger.warning("[ContextEnricher] Failed to get recent signals: %s", e)
            return []

    async def _get_active_goals(self, user_id: str) -> list:
        """Get user's active goals."""
        try:
            result = (
                self._db.table("goals")
                .select("title, goal_type, status, priority")
                .eq("user_id", user_id)
                .in_("status", ["active", "in_progress", "plan_ready"])
                .order("priority", desc=True)
                .limit(5)
                .execute()
            )

            if result.data:
                return [
                    {
                        "title": g["title"],
                        "goal_type": g["goal_type"],
                        "status": g["status"],
                        "priority": g.get("priority", 0.5),
                    }
                    for g in result.data
                ]
            return []
        except Exception as e:
            logger.warning("[ContextEnricher] Failed to get goals: %s", e)
            return []

    async def _get_competitive_landscape(self, _user_id: str) -> dict | None:
        """Get summary of the user's competitive landscape."""
        try:
            result = (
                self._db.table("battle_cards")
                .select("competitor_name, analysis, pricing")
                .order("competitor_name")
                .execute()
            )

            if not result.data:
                return None

            competitors = []
            for card in result.data:
                analysis = card.get("analysis", {})
                pricing = card.get("pricing", {})
                if not isinstance(analysis, dict):
                    analysis = {}
                if not isinstance(pricing, dict):
                    pricing = {}
                competitors.append(
                    {
                        "name": card["competitor_name"],
                        "threat_level": analysis.get("threat_level", "unknown"),
                        "momentum": analysis.get("momentum", "unknown"),
                        "pricing_range": pricing.get("range", ""),
                        "signal_count_30d": analysis.get("signal_count_30d", 0),
                    }
                )

            return {
                "competitors": competitors,
                "total_competitors": len(competitors),
            }
        except Exception as e:
            logger.warning(
                "[ContextEnricher] Failed to get competitive landscape: %s", e
            )
            return None

    def format_context_for_llm(self, context: dict) -> str:
        """
        Format the enriched context into a string for LLM prompts.

        Translates structured data into natural language that the LLM
        can reason about when generating insights.
        """
        parts: list[str] = []

        # User's company identity
        user_co = context.get("user_company", {})
        if user_co.get("name") and user_co["name"] != "Unknown":
            parts.append(
                f"YOU WORK FOR: {user_co['name']} "
                f"({user_co.get('industry', 'life sciences')})"
            )

        # Entity classification
        entity_type = context.get("entity_type", "unknown")
        company_name = context.get("company_name", "Unknown")
        own_name = user_co.get("name", "your company")

        entity_descriptions = {
            "competitor": (
                f"ENTITY RELATIONSHIP: {company_name} is a COMPETITOR of {own_name}. "
                "Analyze this signal for competitive implications — how it affects your "
                "competitive position, displacement opportunities, and account strategy "
                "against this competitor."
            ),
            "own_company": (
                f"ENTITY RELATIONSHIP: This signal is about YOUR OWN COMPANY "
                f"({company_name}). Analyze internal implications and strategic impact."
            ),
            "prospect": (
                f"ENTITY RELATIONSHIP: {company_name} is a PROSPECT/CUSTOMER. "
                "Analyze this signal for deal implications — buying signals, risks, "
                "and engagement opportunities."
            ),
            "industry": (
                f"ENTITY RELATIONSHIP: This is an INDUSTRY-WIDE signal. Analyze "
                f"broad market implications for {own_name}'s competitive position."
            ),
        }
        parts.append(
            entity_descriptions.get(
                entity_type,
                f"ENTITY RELATIONSHIP: {company_name}'s relationship to {own_name} "
                "is unclear. Analyze general business implications.",
            )
        )

        # Battle card data (if competitor)
        bc = context.get("battle_card")
        if bc:
            parts.append(
                f"\nCOMPETITOR BATTLE CARD FOR {bc['competitor_name'].upper()}:"
            )
            if bc.get("overview"):
                parts.append(f"Overview: {bc['overview']}")
            if bc.get("strengths") and isinstance(bc["strengths"], list):
                parts.append(
                    f"Their Strengths: {', '.join(str(s) for s in bc['strengths'][:4])}"
                )
            if bc.get("weaknesses") and isinstance(bc["weaknesses"], list):
                parts.append(
                    f"Their Weaknesses: {', '.join(str(w) for w in bc['weaknesses'][:3])}"
                )
            if bc.get("differentiation") and isinstance(bc["differentiation"], list):
                parts.append(
                    "How We Win Against Them: "
                    f"{', '.join(str(d) for d in bc['differentiation'][:3])}"
                )
            pricing = bc.get("pricing", {})
            if isinstance(pricing, dict) and pricing.get("range"):
                parts.append(
                    f"Their Pricing: {pricing.get('model', '')} | "
                    f"Range: {pricing.get('range', '')} | "
                    f"Strategy: {pricing.get('strategy', '')}"
                )
                if pricing.get("notes"):
                    parts.append(f"Pricing Intel: {pricing['notes']}")
            analysis = bc.get("analysis", {})
            if isinstance(analysis, dict):
                parts.append(
                    f"Current Threat Level: {analysis.get('threat_level', 'unknown')} | "
                    f"Momentum: {analysis.get('momentum', 'unknown')} | "
                    f"Signals in 30d: {analysis.get('signal_count_30d', 0)}"
                )

        # Relevant memories
        memories = context.get("relevant_memories", [])
        if memories:
            parts.append(
                f"\nRELEVANT FACTS FROM ARIA'S MEMORY ({len(memories)} facts):"
            )
            for m in memories[:5]:
                parts.append(
                    f"- {m['fact']} (confidence: {m.get('confidence', 'N/A')}, "
                    f"source: {m.get('source', 'unknown')})"
                )

        # Recent signals for this company
        signals = context.get("company_recent_signals", [])
        if signals:
            parts.append(
                f"\nRECENT SIGNALS FOR {company_name.upper()} ({len(signals)} recent):"
            )
            for s in signals[:5]:
                parts.append(
                    f"- [{s.get('signal_type', '?')}] {s['headline']} "
                    f"({s.get('detected_at', '')[:10]})"
                )

        # Competitive landscape
        landscape = context.get("competitive_landscape")
        if landscape and landscape.get("competitors"):
            parts.append(
                f"\nCOMPETITIVE LANDSCAPE "
                f"({landscape['total_competitors']} tracked competitors):"
            )
            for c in landscape["competitors"]:
                parts.append(
                    f"- {c['name']}: threat={c.get('threat_level', '?')}, "
                    f"momentum={c.get('momentum', '?')}, "
                    f"{c.get('signal_count_30d', 0)} signals/30d"
                )

        # Specialized intelligence contexts
        if context.get("regulatory_context"):
            parts.append(context["regulatory_context"])

        if context.get("clinical_trial_context"):
            parts.append(context["clinical_trial_context"])

        if context.get("supply_chain_context"):
            parts.append(context["supply_chain_context"])

        if context.get("pricing_context"):
            parts.append(context["pricing_context"])

        if context.get("therapeutic_context"):
            parts.append(context["therapeutic_context"])

        if context.get("conference_context"):
            parts.append(context["conference_context"])

        # Active goals
        goals = context.get("active_goals", [])
        if goals:
            parts.append(f"\nUSER'S ACTIVE GOALS ({len(goals)}):")
            for g in goals:
                parts.append(
                    f"- {g['title']} (type: {g.get('goal_type', '?')}, "
                    f"status: {g.get('status', '?')})"
                )

        # Critical instruction
        parts.append("\nCRITICAL RULES FOR INSIGHT GENERATION:")
        parts.append(
            "- NEVER invent deals, stakeholder names, or dollar amounts "
            "that don't exist in the context above."
        )
        parts.append(
            "- NEVER suggest 'contact the VP' unless a specific person "
            "is named in the data."
        )
        parts.append(
            "- If the company is a COMPETITOR, frame insights as competitive "
            "intelligence (displacement opportunities, competitive positioning, "
            "market share implications)."
        )
        parts.append(
            "- If the company is a PROSPECT, frame insights as deal intelligence "
            "(buying signals, engagement opportunities, risk factors)."
        )
        parts.append(
            "- All recommended actions must be grounded in the data provided. "
            "Reference specific battle card points, pricing data, or known facts."
        )
        parts.append(
            f"- Your user works at {own_name} in "
            f"{user_co.get('industry', 'life sciences')}."
        )

        return "\n".join(parts)
