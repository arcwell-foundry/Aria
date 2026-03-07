"""
Action Router: Transforms intelligence into execution.

Every Jarvis insight flows through this router. The router matches insights
against configurable rules and triggers downstream actions:
- Create proactive proposals (for user approval)
- Draft emails with competitive positioning
- Write to memory (institutional learning)
- Create notifications and pulse signals
- Update battle cards
- Update daily briefings

All rules are DB-driven and dynamic — no hardcoded companies or industries.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

_ZERO_UUID = "00000000-0000-0000-0000-000000000000"


def _valid_insight_id(insight: dict[str, Any]) -> str | None:
    """Return insight_id as string if it's a real persisted UUID, else None."""
    raw = str(insight.get("id", ""))
    if not raw or raw == _ZERO_UUID:
        return None
    try:
        UUID(raw)
        return raw
    except (ValueError, AttributeError):
        return None


class ActionRouter:
    """Routes Jarvis insights to appropriate downstream actions."""

    def __init__(self, supabase_client: Any) -> None:
        self._db = supabase_client
        self._rules: list[dict[str, Any]] | None = None  # lazy-loaded

    async def route_insight(
        self,
        user_id: str,
        insight: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Main entry point. Route an insight to downstream actions.

        Args:
            user_id: User UUID.
            insight: Insight dict (must include 'id' from DB insert).
            context: Enriched context from the orchestrator.

        Returns:
            List of action result dicts describing what was executed.
        """
        if not insight:
            return []

        context = context or {}
        actions_taken: list[dict[str, Any]] = []

        # Load routing rules
        rules = self._get_routing_rules()

        # Match insight against rules (first matching rule wins by priority)
        matched_rule = self._match_rule(insight, context, rules)

        if not matched_rule:
            # Default: always write to memory at minimum
            memory_action = await self._write_memory(user_id, insight, context)
            if memory_action:
                actions_taken.append(memory_action)
            # Always check goal impact regardless of rule matching
            try:
                goal_result = await self._check_goal_impact(user_id, insight, context)
                if goal_result:
                    actions_taken.append(goal_result)
            except Exception:
                pass
            return actions_taken

        logger.info(
            "[ActionRouter] Matched rule: %s for insight %s",
            matched_rule["rule_name"],
            insight.get("id", "unknown"),
        )

        # Execute each action defined in the rule
        rule_actions = matched_rule.get("actions", [])
        if isinstance(rule_actions, str):
            rule_actions = json.loads(rule_actions)

        for action_def in rule_actions:
            action_type = action_def.get("type", "")

            try:
                result = await self._dispatch_action(
                    action_type, user_id, insight, context, action_def
                )

                if result:
                    actions_taken.append(result)
                    await self._log_execution(
                        user_id, insight, matched_rule, action_type, result
                    )

            except Exception as e:
                logger.error("[ActionRouter] Failed to execute %s: %s", action_type, e)

        # Always check goal impact regardless of rule matching
        try:
            goal_result = await self._check_goal_impact(user_id, insight, context)
            if goal_result:
                actions_taken.append(goal_result)
        except Exception:
            pass
        return actions_taken

    # ================================================================
    # RULE LOADING & MATCHING
    # ================================================================

    def _get_routing_rules(self) -> list[dict[str, Any]]:
        """Load active routing rules, sorted by priority DESC."""
        if self._rules is not None:
            return self._rules

        try:
            result = (
                self._db.table("action_routing_rules")
                .select("*")
                .eq("is_active", True)
                .order("priority", desc=True)
                .execute()
            )
            self._rules = result.data or []
            return self._rules
        except Exception as e:
            logger.warning("[ActionRouter] Failed to load rules: %s", e)
            return []

    def _match_rule(
        self,
        insight: dict[str, Any],
        context: dict[str, Any],
        rules: list[dict[str, Any]],
    ) -> Optional[dict[str, Any]]:
        """Find the first matching rule for this insight."""
        insight_classification = insight.get("classification", "")
        confidence = insight.get("confidence", 0)
        entity_type = context.get("entity_type", "")
        signal_type = context.get("signal_type", "")

        # Derive urgency from specialized detections
        urgency = "medium"
        if context.get("fda_event"):
            urgency = context["fda_event"].get("urgency", "high")
        elif context.get("supply_chain_vulnerability"):
            urgency = context["supply_chain_vulnerability"].get("urgency", "high")
        elif context.get("pricing_signal"):
            urgency = (
                "high"
                if context["pricing_signal"].get("primary_type")
                in ("revenue_miss", "pricing_pressure")
                else "medium"
            )

        for rule in rules:
            # AND logic — all specified (non-null) conditions must match
            if (
                rule.get("insight_classification")
                and rule["insight_classification"] != insight_classification
            ):
                continue
            if rule.get("urgency_level") and rule["urgency_level"] != urgency:
                continue
            if rule.get("entity_type") and rule["entity_type"] != entity_type:
                continue
            if rule.get("signal_types"):
                rule_types = rule["signal_types"]
                if isinstance(rule_types, str):
                    rule_types = [rule_types]
                if signal_type and signal_type not in rule_types:
                    continue
            if rule.get("min_confidence", 0) > confidence:
                continue

            return rule

        return None

    # ================================================================
    # DISPATCH
    # ================================================================

    async def _dispatch_action(
        self,
        action_type: str,
        user_id: str,
        insight: dict[str, Any],
        context: dict[str, Any],
        action_def: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Dispatch to the correct action handler."""
        handlers = {
            "write_memory": self._write_memory,
            "create_proposal": self._create_proposal,
            "create_notification": self._create_notification,
            "create_pulse": self._create_pulse,
            "update_battle_card": self._update_battle_card,
            "draft_email": self._draft_email,
            "update_briefing": self._update_briefing,
            "update_conference_insight": self._update_conference_insight,
            "check_lead_discovery": self._check_lead_discovery,
        }

        handler = handlers.get(action_type)
        if not handler:
            logger.warning("[ActionRouter] Unknown action type: %s", action_type)
            return None

        # All handlers accept (user_id, insight, context) but some also need action_def
        if action_type in (
            "write_memory",
            "update_conference_insight",
            "check_lead_discovery",
        ):
            return await handler(user_id, insight, context)
        return await handler(user_id, insight, context, action_def)

    # ================================================================
    # ACTION IMPLEMENTATIONS
    # ================================================================

    async def _write_memory(
        self,
        user_id: str,
        insight: dict[str, Any],
        context: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Write insight to memory_semantic for institutional learning."""
        try:
            content = insight.get("content", "")
            classification = insight.get("classification", "unknown")
            company = context.get("company_name", "")
            entity_type = context.get("entity_type", "")
            user_company = context.get("user_company", {})
            user_company_name = (
                user_company.get("name", "") if isinstance(user_company, dict) else ""
            )

            # Build a fact from the insight
            if entity_type == "competitor" and company:
                fact = f"[Competitive Intel] {company} ({classification}): {content[:300]}"
            elif entity_type == "own_company":
                fact = f"[Company Intel] {user_company_name}: {content[:300]}"
            elif entity_type == "industry":
                fact = f"[Market Intel] {content[:300]}"
            else:
                fact = f"[Intelligence] {company}: {content[:300]}"

            valid_id = _valid_insight_id(insight)
            metadata: dict[str, Any] = {
                "category": (
                    "competitive_intelligence"
                    if entity_type == "competitor"
                    else "market_intelligence"
                ),
                "entities": [company] if company else [],
                "insight_classification": classification,
                "entity_type": entity_type,
            }
            if valid_id:
                metadata["source_insight_id"] = valid_id

            result = (
                self._db.table("memory_semantic")
                .insert(
                    {
                        "user_id": user_id,
                        "fact": fact,
                        "confidence": insight.get("confidence", 0.5),
                        "source": "jarvis_insight",
                        "metadata": metadata,
                    }
                )
                .execute()
            )

            memory_id = result.data[0]["id"] if result.data else None
            logger.info("[ActionRouter] Wrote memory: %s...", fact[:80])

            return {"type": "write_memory", "memory_id": memory_id, "fact": fact[:100]}
        except Exception as e:
            logger.error("[ActionRouter] Failed to write memory: %s", e)
            return None

    async def _create_proposal(
        self,
        user_id: str,
        insight: dict[str, Any],
        context: dict[str, Any],
        action_def: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Create a proactive proposal for user approval."""
        try:
            content = insight.get("content", "")
            classification = insight.get("classification", "unknown")
            company = context.get("company_name", "")
            entity_type = context.get("entity_type", "")
            battle_card = context.get("battle_card", {})
            actions = insight.get("recommended_actions", [])

            # Build proposal title
            template = action_def.get("template", "general")
            if template == "displacement_outreach" and company:
                title = f"Displacement opportunity: {company} vulnerability detected"
            elif template == "regulatory_displacement" and company:
                title = f"Regulatory intelligence: {company} compliance issue"
            else:
                title = f"Competitive intelligence: {company or 'market'} — {classification}"

            # Build proposal description
            description = content[:500]
            if actions and isinstance(actions, list):
                description += "\n\nRecommended actions:\n" + "\n".join(
                    f"- {a}" for a in actions[:3] if isinstance(a, str)
                )

            # Build competitive context from battle card
            comp_context: dict[str, Any] = {}
            if battle_card and isinstance(battle_card, dict):
                comp_context["battle_card_name"] = battle_card.get("competitor_name")
                comp_context["differentiation"] = battle_card.get(
                    "differentiation", []
                )[:3]
                comp_context["pricing"] = battle_card.get("pricing", {})
                comp_context["weaknesses"] = battle_card.get("weaknesses", [])[:3]

            proposal_data: dict[str, Any] = {
                "user_id": user_id,
                "proposal_type": template,
                "title": title,
                "description": description,
                "reasoning": (
                    f"Based on {entity_type} signal analysis with "
                    f"{insight.get('confidence', 0):.0%} confidence"
                ),
                "relevance_score": insight.get("confidence", 0.5),
                "status": "pending",
                "insight_content": content[:500],
                "competitive_context": comp_context,
            }
            valid_id = _valid_insight_id(insight)
            if valid_id:
                proposal_data["insight_id"] = valid_id

            result = (
                self._db.table("proactive_proposals")
                .insert(proposal_data)
                .execute()
            )

            proposal_id = result.data[0]["id"] if result.data else None

            # Also add to action queue for ARIA's task list
            action_payload: dict[str, Any] = {
                "company_name": company,
                "entity_type": entity_type,
                "competitive_context": comp_context,
            }
            if valid_id:
                action_payload["insight_id"] = valid_id

            self._db.table("aria_action_queue").insert(
                {
                    "user_id": user_id,
                    "agent": "intelligence",
                    "action_type": template,
                    "title": title,
                    "description": description[:300],
                    "risk_level": "low",
                    "status": "pending",
                    "payload": action_payload,
                    "reasoning": f"Jarvis detected {classification} for {entity_type} {company}",
                }
            ).execute()

            logger.info("[ActionRouter] Created proposal: %s", title[:60])
            return {
                "type": "create_proposal",
                "proposal_id": proposal_id,
                "title": title,
            }
        except Exception as e:
            logger.error("[ActionRouter] Failed to create proposal: %s", e)
            return None

    async def _create_notification(
        self,
        user_id: str,
        insight: dict[str, Any],
        context: dict[str, Any],
        action_def: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Create a notification for the user."""
        try:
            urgency = action_def.get("urgency", "medium")
            company = context.get("company_name", "")
            classification = insight.get("classification", "")

            title = f"{'🔴' if urgency == 'urgent' else '🟡'} {classification.title()}: {company}"
            message = insight.get("content", "")[:200]

            result = (
                self._db.table("notifications")
                .insert(
                    {
                        "user_id": user_id,
                        "type": "signal_detected",
                        "title": title,
                        "message": message,
                        "link": "/intelligence",
                        "metadata": {
                            "insight_id": str(insight.get("id", "")),
                            "urgency": urgency,
                            "company": company,
                            "classification": classification,
                        },
                    }
                )
                .execute()
            )

            notif_id = result.data[0]["id"] if result.data else None
            logger.info("[ActionRouter] Created notification: %s", title[:60])
            return {
                "type": "create_notification",
                "notification_id": notif_id,
                "urgency": urgency,
            }
        except Exception as e:
            logger.error("[ActionRouter] Failed to create notification: %s", e)
            return None

    async def _create_pulse(
        self,
        user_id: str,
        insight: dict[str, Any],
        context: dict[str, Any],
        action_def: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Create a pulse signal for Intelligence Pulse delivery."""
        try:
            priority = action_def.get("priority", "medium")
            company = context.get("company_name", "")

            priority_score = {"urgent": 0.95, "high": 0.8, "medium": 0.6, "low": 0.3}.get(
                priority, 0.5
            )

            result = (
                self._db.table("pulse_signals")
                .insert(
                    {
                        "user_id": user_id,
                        "pulse_type": "jarvis_insight",
                        "title": f"{insight.get('classification', 'intelligence').title()}: {company}",
                        "content": insight.get("content", "")[:500],
                        "source": "jarvis_action_router",
                        "signal_category": "competitive_intelligence",
                        "priority_score": priority_score,
                        "time_sensitivity": 0.8 if priority in ("urgent", "high") else 0.4,
                        "value_impact": insight.get("confidence", 0.5),
                        "entities": [company] if company else [],
                    }
                )
                .execute()
            )

            pulse_id = result.data[0]["id"] if result.data else None
            logger.info("[ActionRouter] Created pulse signal: priority=%s", priority)
            return {"type": "create_pulse", "pulse_id": pulse_id, "priority": priority}
        except Exception as e:
            logger.error("[ActionRouter] Failed to create pulse: %s", e)
            return None

    async def _update_battle_card(
        self,
        user_id: str,
        insight: dict[str, Any],
        context: dict[str, Any],
        action_def: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Update battle card with new intelligence."""
        try:
            company = context.get("company_name", "")
            if not company:
                return None

            card = (
                self._db.table("battle_cards")
                .select("id, analysis, recent_news")
                .ilike("competitor_name", f"%{company}%")
                .limit(1)
                .execute()
            )

            if not card.data:
                return None

            card_data = card.data[0]
            card_id = card_data["id"]

            # Add insight to recent_news
            recent_news = card_data.get("recent_news") or []
            if isinstance(recent_news, list):
                new_entry = {
                    "headline": insight.get("title", "")[:200],
                    "summary": insight.get("content", "")[:300],
                    "date": datetime.now(timezone.utc).isoformat(),
                    "source": "jarvis_insight",
                    "classification": insight.get("classification", ""),
                }
                recent_news.insert(0, new_entry)
                recent_news = recent_news[:10]

            self._db.table("battle_cards").update(
                {
                    "recent_news": recent_news,
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("id", card_id).execute()

            logger.info("[ActionRouter] Updated battle card for %s", company)
            return {"type": "update_battle_card", "company": company}
        except Exception as e:
            logger.error("[ActionRouter] Failed to update battle card: %s", e)
            return None

    async def _draft_email(
        self,
        user_id: str,
        insight: dict[str, Any],
        context: dict[str, Any],
        action_def: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Queue competitive positioning for the briefing queue.

        Note: deferred_email_drafts is for email thread deduplication (requires
        thread_id, latest_email_id, deferred_until, reason). Instead, we queue
        this intelligence for the next daily briefing where it can be actioned.
        """
        try:
            company = context.get("company_name", "")
            battle_card = context.get("battle_card", {})
            classification = insight.get("classification", "")

            if not battle_card or not isinstance(battle_card, dict):
                return None

            # Build email positioning from battle card
            differentiation = battle_card.get("differentiation", [])
            diff_text = (
                ", ".join(str(d) for d in differentiation[:3])
                if differentiation
                else "our specialized solutions"
            )

            pricing = battle_card.get("pricing", {})
            pricing_intel = pricing.get("notes", "") if isinstance(pricing, dict) else ""

            positioning = (
                f"COMPETITIVE POSITIONING (from {company} battle card):\n"
                f"- Your differentiation: {diff_text}\n"
                f"- Their pricing intel: {pricing_intel[:200] if pricing_intel else 'Not available'}\n"
                f"- Signal context: {insight.get('content', '')[:200]}"
            )

            # Queue for briefing instead of deferred_email_drafts
            result = (
                self._db.table("briefing_queue")
                .insert(
                    {
                        "user_id": user_id,
                        "title": f"Competitive positioning ready: {company}",
                        "message": positioning[:500],
                        "category": "competitive_intelligence",
                        "metadata": {
                            "insight_id": str(insight.get("id", "")),
                            "classification": classification,
                            "company": company,
                            "battle_card_positioning": True,
                        },
                    }
                )
                .execute()
            )

            item_id = result.data[0]["id"] if result.data else None
            logger.info("[ActionRouter] Queued competitive positioning for briefing: %s", company)
            return {"type": "update_briefing", "item_id": item_id, "company": company}
        except Exception as e:
            logger.error("[ActionRouter] Failed to queue competitive positioning: %s", e)
            return None

    async def _update_briefing(
        self,
        user_id: str,
        insight: dict[str, Any],
        context: dict[str, Any],
        action_def: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Queue insight for inclusion in next daily briefing.

        Uses briefing_queue schema: title, message, category, metadata.
        """
        try:
            section = action_def.get("section", "competitive_intelligence")
            company = context.get("company_name", "")
            classification = insight.get("classification", "")

            self._db.table("briefing_queue").insert(
                {
                    "user_id": user_id,
                    "title": f"{classification.title()}: {company}" if company else classification.title(),
                    "message": insight.get("content", "")[:300],
                    "category": section,
                    "metadata": {
                        "insight_id": str(insight.get("id", "")),
                        "confidence": insight.get("confidence"),
                        "company": company,
                        "classification": classification,
                    },
                }
            ).execute()

            logger.info(
                "[ActionRouter] Queued for briefing: %s",
                context.get("company_name", "unknown"),
            )
            return {"type": "update_briefing", "section": section}
        except Exception as e:
            logger.error("[ActionRouter] Failed to update briefing: %s", e)
            return None

    async def _update_conference_insight(
        self,
        user_id: str,
        insight: dict[str, Any],
        context: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Update conference intelligence when conference-related signal detected."""
        try:
            conference = context.get("conference")
            if not conference or not isinstance(conference, dict):
                return None

            self._db.table("conference_insights").insert(
                {
                    "user_id": user_id,
                    "conference_id": conference.get("conference_id"),
                    "insight_type": "competitive_presence",
                    "content": insight.get("content", "")[:500],
                    "companies_mentioned": (
                        [context.get("company_name")]
                        if context.get("company_name")
                        else []
                    ),
                    "urgency": "medium",
                    "actionable": True,
                    "recommended_actions": insight.get("recommended_actions", []),
                }
            ).execute()

            conf_name = conference.get("conference_name", "unknown")
            logger.info(
                "[ActionRouter] Updated conference insight for %s", conf_name
            )
            return {
                "type": "update_conference_insight",
                "conference": conf_name,
            }
        except Exception as e:
            logger.error("[ActionRouter] Failed to update conference insight: %s", e)
            return None

    async def _check_lead_discovery(
        self,
        user_id: str,
        insight: dict[str, Any],
        context: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Check if a clinical trial signal should trigger lead discovery."""
        try:
            clinical = context.get("clinical_trial")
            if not clinical or not isinstance(clinical, dict):
                return None

            company = context.get("company_name", "")
            entity_type = context.get("entity_type", "")

            # Only discover leads for non-competitors (prospects or unknowns)
            if entity_type in ("competitor", "own_company"):
                return None

            # Check if already a lead
            existing = (
                self._db.table("discovered_leads")
                .select("id")
                .eq("user_id", user_id)
                .ilike("company_name", f"%{company}%")
                .limit(1)
                .execute()
            )

            if existing.data:
                return None  # Already discovered

            equipment = clinical.get("equipment_needs", {})
            phase = clinical.get("clinical_phase", "")
            modality = clinical.get("drug_modality", "")
            downstream = equipment.get("downstream", [])[:3] if isinstance(equipment, dict) else []

            reasoning = (
                f"{company} entering {phase} for {modality}. "
                f"Equipment needs: {', '.join(downstream)}. "
                f"Procurement window: ~{clinical.get('procurement_lead_months', 12)} months."
            )

            self._db.table("discovered_leads").insert(
                {
                    "user_id": user_id,
                    "company_name": company,
                    "source": "clinical_trial_predictor",
                    "review_status": "pending",
                    "fit_score": 70,
                    "company_data": {
                        "clinical_phase": phase,
                        "drug_modality": modality,
                        "equipment_needs": equipment,
                    },
                    "signals": [
                        {
                            "insight_id": str(insight.get("id", "")),
                            "reasoning": reasoning,
                        }
                    ],
                    "score_breakdown": {
                        "clinical_relevance": 0.7,
                        "equipment_fit": 0.6,
                        "timing": 0.8,
                    },
                }
            ).execute()

            logger.info(
                "[ActionRouter] Discovered lead: %s (%s %s)", company, phase, modality
            )
            return {
                "type": "check_lead_discovery",
                "company": company,
                "phase": phase,
                "modality": modality,
            }
        except Exception as e:
            logger.error("[ActionRouter] Failed to check lead discovery: %s", e)
            return None

    async def _check_goal_impact(
        self,
        user_id: str,
        insight: dict[str, Any],
        context: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Check if insight impacts active goals and create goal_updates."""
        try:
            goals = (
                self._db.table("goals")
                .select("id, title, goal_type, status")
                .eq("user_id", user_id)
                .in_("status", ["active", "in_progress", "plan_ready"])
                .execute()
            )

            if not goals.data:
                return None

            content = (insight.get("content", "") or "").lower()
            goals_updated: list[str] = []

            for goal in goals.data:
                title = (goal.get("title", "") or "").lower()
                goal_keywords = {w for w in title.split() if len(w) > 3}
                content_keywords = {w for w in content.split() if len(w) > 3}
                overlap = goal_keywords & content_keywords

                if len(overlap) >= 2:
                    try:
                        self._db.table("goal_updates").insert({
                            "goal_id": goal["id"],
                            "update_type": "intelligence",
                            "content": (
                                f"New {insight.get('classification', 'intelligence')}: "
                                f"{insight.get('content', '')[:200]}"
                            ),
                            "created_by": "aria_intelligence",  # NOT NULL field
                        }).execute()
                        goals_updated.append(goal["title"])
                    except Exception:
                        pass

            if goals_updated:
                return {
                    "type": "check_goal_impact",
                    "goals_updated": len(goals_updated),
                }
            return None
        except Exception:
            return None

    # ================================================================
    # AUDIT LOGGING
    # ================================================================

    async def _log_execution(
        self,
        user_id: str,
        insight: dict[str, Any],
        rule: dict[str, Any],
        action_type: str,
        result: dict[str, Any],
    ) -> None:
        """Log action execution for audit trail."""
        try:
            log_data: dict[str, Any] = {
                "user_id": user_id,
                "rule_id": rule.get("id"),
                "action_type": action_type,
                "action_details": result,
                "execution_mode": rule.get("execution_mode", "auto"),
                "status": "executed",
                "result": result,
                "executed_at": datetime.now(timezone.utc).isoformat(),
            }
            valid_id = _valid_insight_id(insight)
            if valid_id:
                log_data["insight_id"] = valid_id

            self._db.table("action_execution_log").insert(log_data).execute()
        except Exception as e:
            logger.warning("[ActionRouter] Failed to log execution: %s", e)
