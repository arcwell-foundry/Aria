"""
Conference Intelligence Engine for Life Sciences.

Discovers conferences, enriches with participant data, generates recommendations,
and connects conference activity to competitive/commercial strategy.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ConferenceIntelligenceEngine:
    """Full conference intelligence lifecycle."""

    def __init__(self, supabase_client: Any, exa_client: Any = None) -> None:
        self._db = supabase_client
        self._exa = exa_client

    # ================================================================
    # CONFERENCE DISCOVERY
    # ================================================================

    async def discover_niche_conferences(self, user_id: str) -> list[dict]:
        """
        Use Exa to discover niche conferences relevant to the user's focus.
        Adds new conferences to the calendar.
        """
        user_context = await self._get_user_focus(user_id)
        if not user_context:
            logger.warning("[ConferenceIntel] No user context for conference discovery")
            return []

        discovered: list[dict] = []

        if not self._exa:
            logger.warning("[ConferenceIntel] Exa client not available for discovery")
            return []

        search_queries: list[str] = []
        for modality in user_context.get("manufacturing_focus", [])[:3]:
            search_queries.append(
                f"{modality.replace('_', ' ')} conference 2026 bioprocessing"
            )
        for area in user_context.get("therapeutic_areas", [])[:2]:
            search_queries.append(
                f"{area.replace('_', ' ')} manufacturing conference 2026"
            )
        for competitor in user_context.get("competitors", [])[:3]:
            search_queries.append(
                f"{competitor} exhibiting conference 2026 bioprocessing"
            )

        for query in search_queries:
            try:
                results = self._exa.search(
                    query, num_results=5, use_autoprompt=True
                )
                if results and hasattr(results, "results"):
                    for r in results.results:
                        title = r.title if hasattr(r, "title") else ""
                        url = r.url if hasattr(r, "url") else ""

                        if title and not await self._conference_exists(title):
                            discovered.append(
                                {
                                    "name": title,
                                    "url": url,
                                    "query": query,
                                    "source": "exa_discovery",
                                }
                            )
            except Exception as e:
                logger.warning(
                    "[ConferenceIntel] Discovery search failed for '%s': %s",
                    query,
                    e,
                )

        logger.info(
            "[ConferenceIntel] Discovered %d potential new conferences",
            len(discovered),
        )
        return discovered

    # ================================================================
    # CONFERENCE ENRICHMENT
    # ================================================================

    async def enrich_upcoming_conferences(self, days_ahead: int = 90) -> int:
        """
        For each upcoming conference, search Exa for exhibitor lists,
        speaker agendas, and poster abstracts. Populate conference_participants.
        """
        now = datetime.now(timezone.utc).date()
        cutoff = now + timedelta(days=days_ahead)

        result = (
            self._db.table("conferences")
            .select("id, name, short_name, start_date, website_url")
            .gte("start_date", now.isoformat())
            .lte("start_date", cutoff.isoformat())
            .execute()
        )

        if not result.data:
            logger.info("[ConferenceIntel] No upcoming conferences to enrich")
            return 0

        total_participants = 0

        for conf in result.data:
            conf_name = conf.get("short_name") or conf.get("name")

            if not self._exa:
                continue

            exhibitor_queries = [
                f"{conf_name} 2026 exhibitor list",
                f"{conf_name} 2026 exhibitors companies",
                f"{conf_name} 2026 sponsors",
            ]
            speaker_queries = [
                f"{conf_name} 2026 speaker agenda",
                f"{conf_name} 2026 presentations schedule",
                f"{conf_name} 2026 poster abstracts",
            ]

            for query in exhibitor_queries + speaker_queries:
                try:
                    results = self._exa.search(
                        query, num_results=3, use_autoprompt=True
                    )
                    if results and hasattr(results, "results"):
                        for r in results.results:
                            text = (r.title or "") + " " + (
                                r.text or "" if hasattr(r, "text") else ""
                            )
                            companies = self._extract_company_names(text)

                            for company_name in companies:
                                ptype = (
                                    "exhibitor"
                                    if "exhibitor" in query
                                    else "speaker"
                                )
                                await self._add_participant(
                                    conference_id=conf["id"],
                                    company_name=company_name,
                                    participation_type=ptype,
                                    source_url=(
                                        r.url if hasattr(r, "url") else None
                                    ),
                                )
                                total_participants += 1
                except Exception as e:
                    logger.warning(
                        "[ConferenceIntel] Enrichment search failed: %s", e
                    )

            self._db.table("conferences").update(
                {
                    "last_enriched_at": datetime.now(timezone.utc).isoformat(),
                    "enrichment_source": "exa",
                }
            ).eq("id", conf["id"]).execute()

        logger.info(
            "[ConferenceIntel] Enriched %d conferences with %d participants",
            len(result.data),
            total_participants,
        )
        return total_participants

    # ================================================================
    # COMPETITOR/PROSPECT CLASSIFICATION
    # ================================================================

    async def classify_participants(self, user_id: str) -> None:
        """
        Auto-classify conference participants as competitor/prospect/own_company
        based on user's battle_cards, monitored_entities, and company.
        """
        user_company = await self._get_user_company_name(user_id)
        competitors = await self._get_competitor_names(user_id)

        if user_company:
            self._db.table("conference_participants").update(
                {"is_own_company": True}
            ).ilike("company_name", f"%{user_company}%").execute()

        for comp_name in competitors:
            self._db.table("conference_participants").update(
                {"is_competitor": True}
            ).ilike("company_name", f"%{comp_name}%").execute()

    # ================================================================
    # CONFERENCE RECOMMENDATIONS
    # ================================================================

    async def generate_recommendations(self, user_id: str) -> list[dict]:
        """
        Score each upcoming conference for this user based on:
        1. Competitor presence (how many competitors are exhibiting)
        2. Topic relevance (overlap with user's manufacturing focus)
        3. Audience fit (does the conference target the user's role)
        """
        user_context = await self._get_user_focus(user_id)
        if not user_context:
            return []

        now = datetime.now(timezone.utc).date()

        conferences = (
            self._db.table("conferences")
            .select("*")
            .gte("start_date", now.isoformat())
            .order("start_date")
            .execute()
        )

        if not conferences.data:
            return []

        recommendations: list[dict] = []
        user_modalities = set(user_context.get("manufacturing_focus", []))
        user_areas = set(user_context.get("therapeutic_areas", []))
        user_competitors = set(user_context.get("competitors", []))

        for conf in conferences.data:
            conf_modalities = set(conf.get("manufacturing_focus") or [])
            conf_areas = set(conf.get("therapeutic_areas") or [])

            modality_overlap = len(user_modalities & conf_modalities) / max(
                len(user_modalities), 1
            )
            area_overlap = len(user_areas & conf_areas) / max(
                len(user_areas), 1
            )
            topic_relevance = round(
                modality_overlap * 0.6 + area_overlap * 0.4, 2
            )

            # Score competitor presence from participants table
            participants = (
                self._db.table("conference_participants")
                .select("company_name, is_competitor")
                .eq("conference_id", conf["id"])
                .execute()
            )

            competitor_count = 0
            if participants.data:
                for p in participants.data:
                    if p.get("is_competitor") or p.get(
                        "company_name"
                    ) in user_competitors:
                        competitor_count += 1

            # Also check if competitor names appear in conference description
            conf_text = (
                conf.get("name", "") + " " + (conf.get("description") or "")
            ).lower()
            for comp in user_competitors:
                if comp.lower() in conf_text:
                    competitor_count += 1

            competitor_score = min(competitor_count / 3, 1.0)

            relevance = round(
                topic_relevance * 0.5 + competitor_score * 0.5, 2
            )

            if relevance >= 0.6:
                rec_type = "must_attend"
            elif relevance >= 0.3:
                rec_type = "consider"
            else:
                rec_type = "monitor_remotely"

            reasons: list[dict] = []
            if competitor_count > 0:
                reasons.append(
                    {
                        "reason": f"{competitor_count} competitors exhibiting/presenting",
                        "weight": competitor_score,
                    }
                )
            if modality_overlap > 0:
                overlap_names = user_modalities & conf_modalities
                reasons.append(
                    {
                        "reason": (
                            "Covers your focus areas: "
                            + ", ".join(
                                n.replace("_", " ") for n in overlap_names
                            )
                        ),
                        "weight": modality_overlap,
                    }
                )
            if area_overlap > 0:
                overlap_names = user_areas & conf_areas
                reasons.append(
                    {
                        "reason": (
                            "Relevant therapeutic areas: "
                            + ", ".join(
                                n.replace("_", " ") for n in overlap_names
                            )
                        ),
                        "weight": area_overlap,
                    }
                )

            rec = {
                "conference_id": conf["id"],
                "conference_name": conf["name"],
                "short_name": conf.get("short_name"),
                "start_date": conf.get("start_date"),
                "end_date": conf.get("end_date"),
                "city": conf.get("city"),
                "country": conf.get("country"),
                "recommendation_type": rec_type,
                "relevance_score": relevance,
                "competitor_presence": competitor_count,
                "topic_relevance": topic_relevance,
                "reasons": reasons,
                "estimated_attendance": conf.get("estimated_attendance"),
            }
            recommendations.append(rec)

            # Upsert to DB
            try:
                self._db.table("conference_recommendations").upsert(
                    {
                        "user_id": user_id,
                        "conference_id": conf["id"],
                        "recommendation_type": rec_type,
                        "relevance_score": relevance,
                        "competitor_presence": competitor_count,
                        "topic_relevance": topic_relevance,
                        "reasons": reasons,
                    },
                    on_conflict="user_id,conference_id",
                ).execute()
            except Exception as e:
                logger.warning(
                    "[ConferenceIntel] Failed to upsert recommendation: %s", e
                )

        recommendations.sort(
            key=lambda x: x["relevance_score"], reverse=True
        )

        # Memory compounding: write top recommendations to institutional memory
        for rec in recommendations[:3]:
            try:
                reason_texts = [
                    r["reason"]
                    for r in rec.get("reasons", [])[:2]
                    if isinstance(r, dict) and r.get("reason")
                ]
                self._db.table("memory_semantic").insert(
                    {
                        "user_id": user_id,
                        "fact": (
                            f"[Conference] {rec['conference_name']} "
                            f"({rec.get('start_date', 'TBD')}): "
                            f"Relevance score {rec['relevance_score']:.0%}. "
                            f"{'; '.join(reason_texts)}"
                        ),
                        "confidence": rec["relevance_score"],
                        "source": "conference_intelligence",
                        "metadata": {
                            "conference_id": str(rec["conference_id"]),
                            "recommendation_type": rec["recommendation_type"],
                        },
                    }
                ).execute()
            except Exception as e:
                logger.debug(
                    "[ConferenceIntel] Failed to write memory for %s: %s",
                    rec.get("conference_name"),
                    e,
                )

        return recommendations

    # ================================================================
    # CONFERENCE SIGNAL DETECTION
    # ================================================================

    def detect_conference_mention(self, event_text: str) -> Optional[dict]:
        """
        Detect if a signal mentions a known conference.
        Returns conference info if found.
        """
        text_lower = event_text.lower()

        try:
            conferences = (
                self._db.table("conferences")
                .select("id, name, short_name, start_date, city")
                .execute()
            )

            if not conferences.data:
                return None

            for conf in conferences.data:
                short = (conf.get("short_name") or "").lower()
                name = (conf.get("name") or "").lower()

                # Check short name first (more specific)
                if short and len(short) >= 3 and short in text_lower:
                    return {
                        "conference_id": conf["id"],
                        "conference_name": conf["name"],
                        "short_name": conf.get("short_name"),
                        "start_date": conf.get("start_date"),
                        "city": conf.get("city"),
                    }

                # Check full name
                if name and len(name) >= 10 and name in text_lower:
                    return {
                        "conference_id": conf["id"],
                        "conference_name": conf["name"],
                        "short_name": conf.get("short_name"),
                        "start_date": conf.get("start_date"),
                        "city": conf.get("city"),
                    }

            return None
        except Exception:
            return None

    def format_conference_context(self, conf_info: dict) -> str:
        """Format conference context for LLM prompts."""
        parts = [
            f"\nCONFERENCE DETECTED: {conf_info['conference_name']}",
            f"Date: {conf_info.get('start_date', 'TBD')} | Location: {conf_info.get('city', 'TBD')}",
            (
                "ANALYZE: How does this signal relate to the conference? "
                "What competitive intelligence can be gathered? "
                "What preparation or follow-up actions should the sales team take?"
            ),
        ]
        return "\n".join(parts)

    # ================================================================
    # HELPER METHODS
    # ================================================================

    async def _get_user_focus(self, user_id: str) -> Optional[dict]:
        """Get user's focus areas from their company and battle cards."""
        try:
            profile = (
                self._db.table("user_profiles")
                .select("company_id")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )

            if not profile.data:
                return None

            battle_cards = (
                self._db.table("battle_cards")
                .select("competitor_name")
                .execute()
            )

            competitors = [
                bc["competitor_name"] for bc in (battle_cards.data or [])
            ]

            all_areas: set[str] = set()
            all_modalities: set[str] = set()

            if battle_cards.data:
                confs = (
                    self._db.table("conferences")
                    .select("therapeutic_areas, manufacturing_focus")
                    .execute()
                )

                if confs.data:
                    for c in confs.data:
                        areas = c.get("therapeutic_areas") or []
                        mods = c.get("manufacturing_focus") or []
                        all_areas.update(areas)
                        all_modalities.update(mods)

            entities = (
                self._db.table("monitored_entities")
                .select("entity_name, entity_type")
                .eq("user_id", user_id)
                .execute()
            )

            return {
                "competitors": competitors,
                "therapeutic_areas": list(all_areas),
                "manufacturing_focus": list(all_modalities),
                "entities": entities.data if entities.data else [],
            }
        except Exception as e:
            logger.warning(
                "[ConferenceIntel] Failed to get user focus: %s", e
            )
            return None

    async def _get_user_company_name(self, user_id: str) -> Optional[str]:
        try:
            result = (
                self._db.table("user_profiles")
                .select("company_id")
                .eq("id", user_id)
                .limit(1)
                .execute()
            )
            if not result.data:
                return None
            company = (
                self._db.table("companies")
                .select("name")
                .eq("id", result.data[0]["company_id"])
                .limit(1)
                .execute()
            )
            return company.data[0]["name"] if company.data else None
        except Exception:
            return None

    async def _get_competitor_names(self, user_id: str) -> list[str]:
        try:
            result = (
                self._db.table("battle_cards")
                .select("competitor_name")
                .execute()
            )
            return [r["competitor_name"] for r in (result.data or [])]
        except Exception:
            return []

    async def _conference_exists(self, name: str) -> bool:
        try:
            result = (
                self._db.table("conferences")
                .select("id")
                .ilike("name", f"%{name[:50]}%")
                .limit(1)
                .execute()
            )
            return bool(result.data)
        except Exception:
            return False

    async def _add_participant(
        self,
        conference_id: str,
        company_name: str,
        participation_type: str,
        source_url: Optional[str] = None,
        person_name: Optional[str] = None,
        presentation_title: Optional[str] = None,
    ) -> None:
        """Add a participant, avoiding duplicates."""
        try:
            existing = (
                self._db.table("conference_participants")
                .select("id")
                .eq("conference_id", conference_id)
                .ilike("company_name", f"%{company_name}%")
                .eq("participation_type", participation_type)
                .limit(1)
                .execute()
            )

            if existing.data:
                return

            self._db.table("conference_participants").insert(
                {
                    "conference_id": conference_id,
                    "company_name": company_name,
                    "participation_type": participation_type,
                    "source_url": source_url,
                    "person_name": person_name,
                    "presentation_title": presentation_title,
                }
            ).execute()
        except Exception as e:
            logger.warning(
                "[ConferenceIntel] Failed to add participant: %s", e
            )

    def _extract_company_names(self, text: str) -> list[str]:
        """Extract known company names from text."""
        known_companies = [
            "Cytiva",
            "Sartorius",
            "Pall",
            "MilliporeSigma",
            "Thermo Fisher",
            "Repligen",
            "Fujifilm",
            "Samsung Biologics",
            "Catalent",
            "Lonza",
            "WuXi",
            "Charles River",
            "Merck",
            "Danaher",
            "GE Healthcare",
            "Pall Corporation",
            "Novatech",
            "Eppendorf",
        ]
        found: list[str] = []
        text_lower = text.lower()
        for company in known_companies:
            if company.lower() in text_lower:
                found.append(company)
        return found
