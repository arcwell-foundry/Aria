"""Signal Radar capability for ScoutAgent.

Aggregates market signals from 15+ life sciences data sources, scores
relevance against user context, detects non-obvious implications via LLM,
and writes high-value alerts to market_signals / notifications tables.

Data sources:
- RSS feeds: BioPharma Dive, STAT News, Endpoints News, Fierce Pharma,
  BioSpace, Pharmaceutical Technology, GEN News, Drug Discovery & Development
- Government APIs: FDA (approvals, warning letters), ClinicalTrials.gov,
  SEC EDGAR, USPTO patents
- Wire services: PR Newswire, GlobeNewswire
- Social: LinkedIn company pages

Per-user monitoring is configured via the ``monitored_entities`` table.
The capability is designed to run on an hourly cron during business hours
via the SyncScheduler.
"""

import asyncio
import hashlib
import json
import logging
import subprocess
import time
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import urlencode

from pydantic import BaseModel, Field

from src.agents.capabilities.base import BaseCapability, CapabilityResult
from src.core.llm import LLMClient
from src.db.supabase import SupabaseClient

if TYPE_CHECKING:
    from src.intelligence.causal.models import ButterflyEffect

logger = logging.getLogger(__name__)

# ── User-Agent for public API requests ──────────────────────────────────
DEFAULT_USER_AGENT = "ARIA-Intelligence/1.0 (support@aria-intel.com)"

# ── RSS feed URLs (life sciences) ──────────────────────────────────────
RSS_FEEDS: dict[str, str] = {
    "biopharma_dive": "https://www.biopharmadive.com/feeds/news/",
    "stat_news": "https://www.statnews.com/feed/",
    "endpoints_news": "https://endpts.com/feed/",
    "fierce_pharma": "https://www.fiercepharma.com/rss/xml",
    "biospace": "https://www.biospace.com/rss/",
    "pharma_tech": "https://www.pharmaceutical-technology.com/feed/",
    "gen_news": "https://www.genengnews.com/feed/",
    "drug_discovery_dev": "https://www.drugdiscoverytrends.com/feed/",
}

# ── Government API endpoints ──────────────────────────────────────────
FDA_DRUG_APPROVALS_URL = "https://api.fda.gov/drug/drugsfda.json"
FDA_WARNING_LETTERS_URL = "https://api.fda.gov/drug/enforcement.json"
FDA_DEVICE_APPROVALS_URL = "https://api.fda.gov/device/510k.json"
CLINICAL_TRIALS_URL = "https://clinicaltrials.gov/api/v2/studies"
SEC_EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions"
# NOTE: The old developer.uspto.gov IBD API was retired in 2025.
# Patent search now uses Google Patents as primary source.
GOOGLE_PATENTS_XHR_URL = "https://patents.google.com/xhr/query"

# ── Wire service URLs ──────────────────────────────────────────────────
PR_NEWSWIRE_SEARCH_URL = "https://www.prnewswire.com/search/news/"
GLOBENEWSWIRE_SEARCH_URL = "https://www.globenewswire.com/search"

# ── Signal type constants ──────────────────────────────────────────────
SIGNAL_TYPES = {
    "fda_approval",
    "fda_warning_letter",
    "clinical_trial",
    "sec_filing",
    "patent",
    "funding",
    "leadership",
    "partnership",
    "product",
    "hiring",
    "earnings",
    "regulatory",
    "competitive_move",
    "market_trend",
}


# ── Domain models ──────────────────────────────────────────────────────


class Signal(BaseModel):
    """A detected market signal from any source."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_name: str
    signal_type: str
    headline: str
    summary: str = ""
    source_url: str = ""
    source_name: str = ""
    relevance_score: float = 0.0
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = Field(default_factory=dict)
    linked_lead_id: str | None = None


class Implication(BaseModel):
    """A non-obvious implication derived from a signal via LLM analysis."""

    signal_id: str
    description: str
    affected_entities: list[str] = Field(default_factory=list)
    confidence: float = 0.5
    action_suggestion: str = ""
    reasoning: str = ""


# ── Capability implementation ──────────────────────────────────────────


class SignalRadarCapability(BaseCapability):
    """Aggregates, scores, and alerts on market signals from 15+ sources.

    Designed for the ScoutAgent to replace mock signal detection with real
    data from RSS feeds, government APIs, wire services, and social media.
    Signals are stored in ``market_signals`` and high-relevance alerts go
    to ``notifications``.

    Task types:
    - ``scan_all_sources``: Full scan across all configured sources
    - ``scan_rss``: Scan RSS feeds only
    - ``scan_fda``: Scan FDA APIs only
    - ``scan_clinical_trials``: Scan ClinicalTrials.gov only
    - ``scan_sec``: Scan SEC EDGAR only
    - ``scan_patents``: Scan USPTO only
    - ``scan_social``: Scan LinkedIn company pages
    - ``detect_implications``: Run LLM implication detection on recent signals
    - ``create_alerts``: Process signals and write notifications
    """

    capability_name: str = "signal-radar"
    agent_types: list[str] = ["ScoutAgent"]
    oauth_scopes: list[str] = []
    data_classes: list[str] = ["PUBLIC", "INTERNAL"]

    # ── BaseCapability abstract interface ─────────────────────────────

    async def can_handle(self, task: dict[str, Any]) -> float:
        """Return confidence for signal-radar tasks."""
        task_type = task.get("type", "")
        if task_type in {
            "scan_all_sources",
            "scan_rss",
            "scan_fda",
            "scan_clinical_trials",
            "scan_sec",
            "scan_patents",
            "scan_social",
            "detect_implications",
            "create_alerts",
        }:
            return 0.95
        if any(kw in task_type.lower() for kw in ("signal", "radar", "monitor", "scan", "alert")):
            return 0.6
        return 0.0

    async def execute(
        self,
        task: dict[str, Any],
        context: dict[str, Any],  # noqa: ARG002
    ) -> CapabilityResult:
        """Route to the correct method based on task type."""
        start = time.monotonic()
        user_id = self._user_context.user_id
        task_type = task.get("type", "")

        try:
            if task_type == "scan_all_sources":
                signals = await self.scan_all_sources(user_id)
                data = {"signals": [s.model_dump(mode="json") for s in signals]}
                facts = self._extract_facts_from_signals(signals, user_id)

            elif task_type == "scan_rss":
                entities = await self._get_monitored_entities(user_id)
                signals = await self._scan_rss_feeds(entities)
                data = {"signals": [s.model_dump(mode="json") for s in signals]}
                facts = self._extract_facts_from_signals(signals, user_id)

            elif task_type == "scan_fda":
                entities = await self._get_monitored_entities(user_id)
                keywords = [e["entity_name"] for e in entities]
                signals = await self._scan_fda(keywords)
                data = {"signals": [s.model_dump(mode="json") for s in signals]}
                facts = self._extract_facts_from_signals(signals, user_id)

            elif task_type == "scan_clinical_trials":
                entities = await self._get_monitored_entities(user_id)
                keywords = [e["entity_name"] for e in entities]
                signals = await self._scan_clinical_trials(keywords)
                data = {"signals": [s.model_dump(mode="json") for s in signals]}
                facts = self._extract_facts_from_signals(signals, user_id)

            elif task_type == "scan_sec":
                entities = await self._get_monitored_entities(user_id)
                company_names = [
                    e["entity_name"] for e in entities if e.get("entity_type") == "company"
                ]
                signals = await self._scan_sec_edgar(company_names)
                data = {"signals": [s.model_dump(mode="json") for s in signals]}
                facts = self._extract_facts_from_signals(signals, user_id)

            elif task_type == "scan_patents":
                entities = await self._get_monitored_entities(user_id)
                keywords = [e["entity_name"] for e in entities]
                signals = await self._scan_patents(keywords)
                data = {"signals": [s.model_dump(mode="json") for s in signals]}
                facts = self._extract_facts_from_signals(signals, user_id)

            elif task_type == "scan_social":
                entities = await self._get_monitored_entities(user_id)
                company_names = [
                    e["entity_name"] for e in entities if e.get("entity_type") == "company"
                ]
                signals = await self._scan_social(company_names)
                data = {"signals": [s.model_dump(mode="json") for s in signals]}
                facts = self._extract_facts_from_signals(signals, user_id)

            elif task_type == "detect_implications":
                signal_data = task.get("signals", [])
                signals = [Signal(**s) for s in signal_data]
                user_context = await self._build_user_context(user_id)
                implications: list[Implication] = []
                for signal in signals:
                    impls = await self.detect_implications(signal, user_context)
                    implications.extend(impls)
                data = {
                    "implications": [i.model_dump(mode="json") for i in implications],
                }
                facts = self._extract_facts_from_implications(implications, user_id)

            elif task_type == "create_alerts":
                signal_data = task.get("signals", [])
                signals = [Signal(**s) for s in signal_data]
                await self.create_alerts(signals, user_id)
                data = {"alerts_created": len(signals)}
                facts = []

            else:
                return CapabilityResult(
                    success=False,
                    error=f"Unknown task type: {task_type}",
                    execution_time_ms=int((time.monotonic() - start) * 1000),
                )

            elapsed_ms = int((time.monotonic() - start) * 1000)
            await self.log_activity(
                activity_type="signal_radar",
                title=f"Signal radar: {task_type}",
                description=f"Completed {task_type} for user {user_id}",
                confidence=0.80,
                metadata={
                    "task_type": task_type,
                    "signals_found": len(data.get("signals", [])),
                },
            )
            return CapabilityResult(
                success=True,
                data=data,
                extracted_facts=facts,
                execution_time_ms=elapsed_ms,
            )

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.exception("Signal radar capability failed")
            return CapabilityResult(
                success=False,
                error=str(exc),
                execution_time_ms=elapsed_ms,
            )

    def get_data_classes_accessed(self) -> list[str]:
        """Declare data classification levels."""
        return ["public", "internal"]

    # ── Public methods ───────────────────────────────────────────────

    async def scan_all_sources(self, user_id: str) -> list[Signal]:
        """Aggregate signals from all configured sources for a user.

        Reads the user's ``monitored_entities`` to determine which
        companies, people, and topics to watch, then fans out to every
        source in parallel.

        Args:
            user_id: Authenticated user UUID.

        Returns:
            Deduplicated list of Signal objects from all sources.
        """
        import asyncio

        entities = await self._get_monitored_entities(user_id)
        if not entities:
            logger.info("No monitored entities for user %s", user_id)
            return []

        keywords = [e["entity_name"] for e in entities]
        company_names = [e["entity_name"] for e in entities if e.get("entity_type") == "company"]
        topic_names = [e["entity_name"] for e in entities if e.get("entity_type") == "topic"]

        # Fan out to all sources in parallel
        results = await asyncio.gather(
            self._scan_rss_feeds(entities),
            self._scan_fda(keywords + topic_names),
            self._scan_clinical_trials(keywords + topic_names),
            self._scan_sec_edgar(company_names),
            self._scan_patents(keywords + topic_names),
            self._scan_wire_services(company_names),
            self._scan_social(company_names),
            return_exceptions=True,
        )

        # Merge signals, skipping failures
        all_signals: list[Signal] = []
        source_labels = [
            "rss",
            "fda",
            "clinical_trials",
            "sec",
            "patents",
            "wire_services",
            "social",
        ]
        for i, result in enumerate(results):
            if isinstance(result, BaseException):
                logger.warning(
                    "Signal source %s failed: %s",
                    source_labels[i],
                    result,
                )
                continue
            all_signals.extend(result)

        # Score relevance against user context
        user_context = await self._build_user_context(user_id)
        for signal in all_signals:
            signal.relevance_score = await self.score_relevance(signal, user_context)

        # Deduplicate
        deduped = self._deduplicate_signals(all_signals)

        # Sort by relevance descending
        deduped.sort(key=lambda s: s.relevance_score, reverse=True)

        # Store in market_signals and create alerts for high-relevance
        client = SupabaseClient.get_client()
        for signal in deduped:
            self._store_market_signal(client, user_id, signal)

        high_relevance = [s for s in deduped if s.relevance_score >= 0.7]
        if high_relevance:
            await self.create_alerts(high_relevance, user_id)

        # Update last_checked_at on monitored entities
        await self._update_last_checked(user_id)

        logger.info(
            "Signal radar scan complete",
            extra={
                "user_id": user_id,
                "total_signals": len(all_signals),
                "deduplicated": len(deduped),
                "high_relevance": len(high_relevance),
            },
        )
        return deduped

    async def score_relevance(self, signal: Signal, user_context: dict[str, Any]) -> float:
        """Score a signal's relevance (0-1) against user context.

        Scoring factors:
        - Direct company match (tracked competitors, leads): +0.35
        - Therapeutic area match: +0.25
        - Product/pipeline overlap: +0.20
        - Signal freshness (last 24h = full, decays over 7 days): +0.10
        - Signal type priority (FDA, funding = high): +0.10

        Args:
            signal: Signal to score.
            user_context: Dict containing tracked_competitors, leads,
                therapeutic_areas, products, company_name.

        Returns:
            Float in [0.0, 1.0].
        """
        score = 0.0

        # Factor 1: Company match
        tracked_companies = {c.lower() for c in user_context.get("tracked_competitors", [])}
        lead_companies = {c.lower() for c in user_context.get("lead_companies", [])}
        user_company = user_context.get("company_name", "").lower()
        signal_company = signal.company_name.lower()

        if signal_company in tracked_companies:
            score += 0.35
        elif signal_company in lead_companies:
            score += 0.30
        elif signal_company == user_company:
            score += 0.25

        # Factor 2: Therapeutic area match
        user_areas = {a.lower() for a in user_context.get("therapeutic_areas", [])}
        signal_text = f"{signal.headline} {signal.summary}".lower()
        area_matches = sum(1 for a in user_areas if a in signal_text)
        if area_matches > 0:
            score += min(0.25, 0.10 * area_matches)

        # Factor 3: Product/pipeline overlap
        user_products = {p.lower() for p in user_context.get("products", [])}
        product_matches = sum(1 for p in user_products if p in signal_text)
        if product_matches > 0:
            score += min(0.20, 0.10 * product_matches)

        # Factor 4: Freshness decay
        age_hours = (datetime.now(UTC) - signal.detected_at).total_seconds() / 3600
        if age_hours <= 24:
            score += 0.10
        elif age_hours <= 72:
            score += 0.07
        elif age_hours <= 168:
            score += 0.03

        # Factor 5: Signal type priority
        high_priority_types = {
            "fda_approval",
            "fda_warning_letter",
            "funding",
            "leadership",
            "clinical_trial",
        }
        if signal.signal_type in high_priority_types:
            score += 0.10
        elif signal.signal_type in {"partnership", "product", "earnings"}:
            score += 0.05

        return min(1.0, score)

    async def detect_implications(
        self, signal: Signal, knowledge_context: dict[str, Any]
    ) -> list[Implication]:
        """Use LLM to identify non-obvious implications of a signal.

        Example: "WuXi announced Boston capacity expansion" -> implications
        for user's CDMO clients in the Boston area.

        Args:
            signal: The signal to analyse.
            knowledge_context: User's knowledge graph context including
                leads, competitors, therapeutic areas, and relationships.

        Returns:
            List of Implication objects with confidence scores.
        """
        llm = LLMClient()
        prompt = self._build_implications_prompt(signal, knowledge_context)

        try:
            response = await llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=(
                    "You are ARIA's strategic intelligence engine. Analyse "
                    "the market signal and identify non-obvious implications "
                    "for the user's business. Focus on second-order effects, "
                    "competitive dynamics, and actionable opportunities. "
                    "Respond with valid JSON only."
                ),
                max_tokens=2048,
                temperature=0.4,
            )

            implications = self._parse_implications_response(response, signal.id)
            return implications

        except Exception as exc:
            logger.warning(
                "Implication detection failed for signal %s: %s",
                signal.id,
                exc,
            )
            return []

    async def create_alerts(self, signals: list[Signal], user_id: str) -> None:
        """Write high-relevance signals as notifications.

        Inserts into both ``market_signals`` (if not already stored) and
        ``notifications`` tables so the user sees them in the UI.
        Each signal is also passed through implication analysis to trigger
        skill execution plans for actionable insights.

        Args:
            signals: Signals to alert on.
            user_id: User UUID.
        """
        from src.skills.implication_trigger import process_signal_with_implications

        client = SupabaseClient.get_client()

        for signal in signals:
            # Run new causal implication engine analysis first
            await self._run_causal_implication_analysis(signal, user_id)

            # Run implication analysis before notification — this may create
            # a richer, implication-aware notification instead of a plain one.
            try:
                triggers = await process_signal_with_implications(signal, user_id)
                if triggers:
                    # Implication trigger already sent a richer notification,
                    # skip the plain one.
                    logger.info(
                        "Signal %s handled by implication trigger (%d actions)",
                        signal.id,
                        len(triggers),
                    )
                    continue
            except Exception as exc:
                logger.warning(
                    "Implication analysis failed for signal %s, "
                    "falling back to plain notification: %s",
                    signal.id,
                    exc,
                )

            # Fallback: plain notification when no implications detected
            try:
                client.table("notifications").insert(
                    {
                        "id": str(uuid.uuid4()),
                        "user_id": user_id,
                        "type": "signal_detected",
                        "title": signal.headline[:200],
                        "message": signal.summary[:500],
                        "link": signal.source_url,
                        "metadata": {
                            "signal_id": signal.id,
                            "signal_type": signal.signal_type,
                            "company_name": signal.company_name,
                            "relevance_score": signal.relevance_score,
                            "source_name": signal.source_name,
                        },
                        "created_at": datetime.now(UTC).isoformat(),
                    }
                ).execute()
            except Exception as exc:
                logger.warning(
                    "Failed to create notification for signal %s: %s",
                    signal.id,
                    exc,
                )

            # Trigger LinkedIn post draft for high-relevance signals
            if signal.relevance_score >= 0.7:
                try:
                    from src.agents.capabilities.linkedin import (
                        LinkedInIntelligenceCapability,
                    )

                    linkedin_cap = LinkedInIntelligenceCapability(
                        supabase_client=client,
                        memory_service=None,
                        knowledge_graph=None,
                        user_context=self._user_context,
                    )
                    await linkedin_cap.draft_post(
                        user_id=user_id,
                        trigger_context={
                            "trigger_type": "signal",
                            "trigger_source": signal.headline[:120],
                            "content": (
                                f"{signal.headline}\n\n{signal.summary}\n\n"
                                f"Company: {signal.company_name} | "
                                f"Type: {signal.signal_type} | "
                                f"Source: {signal.source_name}"
                            ),
                        },
                    )
                except Exception as exc:
                    logger.warning(
                        "LinkedIn draft trigger failed for signal %s: %s",
                        signal.id,
                        exc,
                    )

    async def _run_causal_implication_analysis(self, signal: Signal, user_id: str) -> None:
        """Run intelligence analysis for a signal via the Jarvis Orchestrator.

        Uses the unified orchestrator (US-710) to process the signal through
        all intelligence engines: causal chains, implications, butterfly effects,
        goal impact, time horizon, and more.

        Args:
            signal: The signal to analyze.
            user_id: User UUID.
        """
        try:
            from src.intelligence.orchestrator import create_orchestrator

            orchestrator = create_orchestrator()
            event_description = f"{signal.headline}\n\n{signal.summary}"
            insights = await orchestrator.process_event(
                user_id=user_id,
                event=event_description,
                source_context="signal_radar",
                source_id=str(signal.id),
            )

            if insights:
                logger.info(
                    "Orchestrator analysis produced %d insights for signal %s",
                    len(insights),
                    signal.id,
                )

        except Exception as exc:
            logger.warning(
                "Orchestrator analysis failed for signal %s: %s",
                signal.id,
                exc,
            )

    async def _create_butterfly_notification(
        self,
        user_id: str,
        butterfly: "ButterflyEffect",
        signal: Signal,
    ) -> None:
        """Create notification for high/critical butterfly effects.

        Args:
            user_id: User UUID.
            butterfly: Detected butterfly effect.
            signal: The source signal.
        """
        from datetime import UTC, datetime
        from uuid import uuid4

        client = SupabaseClient.get_client()
        try:
            client.table("notifications").insert(
                {
                    "id": str(uuid4()),
                    "user_id": user_id,
                    "type": "butterfly_effect",
                    "title": f"⚠️ {butterfly.warning_level.value.upper()}: Cascade Effect Detected",
                    "message": (
                        f"Signal '{signal.headline[:80]}...' shows {butterfly.amplification_factor:.1f}x "
                        f"amplification across {butterfly.cascade_depth} cascade levels. "
                        f"Full impact expected in {butterfly.time_to_full_impact}."
                    ),
                    "link": signal.source_url,
                    "metadata": {
                        "signal_id": signal.id,
                        "amplification_factor": butterfly.amplification_factor,
                        "cascade_depth": butterfly.cascade_depth,
                        "warning_level": butterfly.warning_level.value,
                        "affected_goal_count": butterfly.affected_goal_count,
                    },
                    "created_at": datetime.now(UTC).isoformat(),
                }
            ).execute()
        except Exception as exc:
            logger.warning("Failed to create butterfly notification: %s", exc)

    # ── Source scanners (private) ────────────────────────────────────

    async def _scan_rss_feeds(self, entities: list[dict[str, Any]]) -> list[Signal]:
        """Scan life sciences RSS feeds for signals matching entities.

        Parses RSS/Atom feeds from 8 industry publications and matches
        articles against monitored entity names.

        Args:
            entities: List of monitored entity dicts from Supabase.

        Returns:
            List of Signal objects from RSS matches.
        """
        import httpx

        signals: list[Signal] = []
        entity_names_lower = [e["entity_name"].lower() for e in entities]

        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": DEFAULT_USER_AGENT},
        ) as client:
            for feed_name, feed_url in RSS_FEEDS.items():
                try:
                    resp = await client.get(feed_url)
                    if resp.status_code != 200:
                        continue
                    feed_signals = self._parse_rss_feed(resp.text, feed_name, entity_names_lower)
                    signals.extend(feed_signals)
                except httpx.HTTPError as exc:
                    logger.warning("RSS feed %s failed: %s", feed_name, exc)

        return signals

    async def _scan_fda(self, keywords: list[str]) -> list[Signal]:
        """Scan FDA openFDA APIs for drug approvals and warning letters.

        Queries:
        - Drug approvals (drugsfda.json)
        - Enforcement actions / warning letters (enforcement.json)
        - Device 510(k) clearances (510k.json)

        Args:
            keywords: Company/drug names to search for.

        Returns:
            List of Signal objects from FDA matches.
        """
        import asyncio

        import httpx

        signals: list[Signal] = []
        search_term = " OR ".join(f'"{kw}"' for kw in keywords[:10])

        async with httpx.AsyncClient(
            timeout=20.0,
            headers={"User-Agent": DEFAULT_USER_AGENT},
        ) as client:
            tasks = [
                self._fetch_fda_approvals(client, search_term),
                self._fetch_fda_enforcement(client, search_term),
                self._fetch_fda_devices(client, search_term),
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, BaseException):
                    logger.warning("FDA sub-scan failed: %s", result)
                    continue
                signals.extend(result)

        return signals

    async def _fetch_fda_approvals(self, client: Any, search_term: str) -> list[Signal]:
        """Fetch recent drug approvals from openFDA.

        Args:
            client: httpx.AsyncClient instance.
            search_term: openFDA search query string.

        Returns:
            List of Signal objects for drug approvals.
        """
        signals: list[Signal] = []
        try:
            resp = await client.get(
                FDA_DRUG_APPROVALS_URL,
                params={
                    "search": f"openfda.brand_name:{search_term}",
                    "limit": "20",
                    "sort": "submissions.submission_status_date:desc",
                },
            )
            if resp.status_code != 200:
                return signals

            data = resp.json()
            for result in data.get("results", []):
                brand_names = result.get("openfda", {}).get("brand_name", [])
                manufacturer = (
                    result.get("openfda", {}).get("manufacturer_name", ["Unknown"])[0]
                    if result.get("openfda", {}).get("manufacturer_name")
                    else "Unknown"
                )
                product_name = brand_names[0] if brand_names else "Unknown"

                submissions = result.get("submissions", [])
                latest = submissions[0] if submissions else {}
                sub_date = latest.get("submission_status_date", "")

                signals.append(
                    Signal(
                        company_name=manufacturer,
                        signal_type="fda_approval",
                        headline=f"FDA action: {product_name} ({manufacturer})",
                        summary=(
                            f"{latest.get('submission_type', '')} "
                            f"{latest.get('submission_status', '')} "
                            f"for {product_name}"
                        ),
                        source_url=(
                            f"https://www.accessdata.fda.gov/scripts/cder/"
                            f"daf/index.cfm?event=overview.process"
                            f"&ApplNo={result.get('application_number', '')}"
                        ),
                        source_name="FDA openFDA",
                        metadata={
                            "application_number": result.get("application_number", ""),
                            "submission_date": sub_date,
                            "brand_names": brand_names,
                        },
                    )
                )
        except Exception as exc:
            logger.warning("FDA approvals fetch failed: %s", exc)

        return signals

    async def _fetch_fda_enforcement(self, client: Any, search_term: str) -> list[Signal]:
        """Fetch FDA enforcement actions (recalls, warning letters).

        Args:
            client: httpx.AsyncClient instance.
            search_term: openFDA search query string.

        Returns:
            List of Signal objects for enforcement actions.
        """
        signals: list[Signal] = []
        try:
            resp = await client.get(
                FDA_WARNING_LETTERS_URL,
                params={
                    "search": f"recalling_firm:{search_term}",
                    "limit": "20",
                    "sort": "report_date:desc",
                },
            )
            if resp.status_code != 200:
                return signals

            data = resp.json()
            for result in data.get("results", []):
                firm = result.get("recalling_firm", "Unknown")
                signals.append(
                    Signal(
                        company_name=firm,
                        signal_type="fda_warning_letter",
                        headline=(
                            f"FDA enforcement: {firm} — {result.get('reason_for_recall', '')[:100]}"
                        ),
                        summary=result.get("reason_for_recall", ""),
                        source_url=(
                            "https://www.fda.gov/safety/recalls-market-withdrawals-safety-alerts"
                        ),
                        source_name="FDA openFDA",
                        metadata={
                            "recall_number": result.get("recall_number", ""),
                            "status": result.get("status", ""),
                            "classification": result.get("classification", ""),
                            "report_date": result.get("report_date", ""),
                        },
                    )
                )
        except Exception as exc:
            logger.warning("FDA enforcement fetch failed: %s", exc)

        return signals

    async def _fetch_fda_devices(self, client: Any, search_term: str) -> list[Signal]:
        """Fetch FDA 510(k) device clearances.

        Args:
            client: httpx.AsyncClient instance.
            search_term: openFDA search query string.

        Returns:
            List of Signal objects for device clearances.
        """
        signals: list[Signal] = []
        try:
            resp = await client.get(
                FDA_DEVICE_APPROVALS_URL,
                params={
                    "search": f"applicant:{search_term}",
                    "limit": "20",
                    "sort": "decision_date:desc",
                },
            )
            if resp.status_code != 200:
                return signals

            data = resp.json()
            for result in data.get("results", []):
                applicant = result.get("applicant", "Unknown")
                device_name = result.get("device_name", "Unknown device")
                signals.append(
                    Signal(
                        company_name=applicant,
                        signal_type="fda_approval",
                        headline=(f"510(k) clearance: {device_name} ({applicant})"),
                        summary=(
                            f"Device: {device_name}. "
                            f"Decision: {result.get('decision_description', '')}. "
                            f"Product code: {result.get('product_code', '')}."
                        ),
                        source_url=(
                            f"https://www.accessdata.fda.gov/scripts/cdrh/"
                            f"cfdocs/cfpmn/pmn.cfm?ID="
                            f"{result.get('k_number', '')}"
                        ),
                        source_name="FDA 510(k)",
                        metadata={
                            "k_number": result.get("k_number", ""),
                            "decision_date": result.get("decision_date", ""),
                            "product_code": result.get("product_code", ""),
                        },
                    )
                )
        except Exception as exc:
            logger.warning("FDA device clearance fetch failed: %s", exc)

        return signals

    async def _scan_clinical_trials(self, keywords: list[str]) -> list[Signal]:
        """Scan ClinicalTrials.gov v2 API for new/updated trials.

        Searches for trials matching monitored keywords that were
        posted or updated in the last 7 days. Falls back to curl if
        httpx is blocked by TLS fingerprinting.

        Args:
            keywords: Terms to search for (company names, drugs, areas).

        Returns:
            List of Signal objects from clinical trial matches.
        """
        import httpx

        signals: list[Signal] = []
        search_term = " OR ".join(keywords[:10])
        params: dict[str, Any] = {
            "query.term": search_term,
            "pageSize": 20,
            "sort": "LastUpdatePostDate:desc",
            "format": "json",
        }

        data: dict[str, Any] | None = None
        try:
            async with httpx.AsyncClient(
                timeout=20.0,
                headers={"User-Agent": DEFAULT_USER_AGENT},
            ) as client:
                resp = await client.get(CLINICAL_TRIALS_URL, params=params)
                if resp.status_code == 200:
                    data = resp.json()
                else:
                    logger.info(
                        "ClinicalTrials.gov httpx returned %d, trying curl",
                        resp.status_code,
                    )
        except httpx.HTTPError as exc:
            logger.info("ClinicalTrials.gov httpx failed (%s), trying curl", exc)

        # Curl fallback — CT.gov blocks some HTTP clients via TLS fingerprinting
        if data is None:
            try:
                url = f"{CLINICAL_TRIALS_URL}?{urlencode(params, doseq=True)}"
                proc = await asyncio.to_thread(
                    subprocess.run,
                    ["curl", "-s", "-f", "--max-time", "30", url],
                    capture_output=True,
                    text=True,
                    timeout=35,
                )
                if proc.returncode == 0:
                    data = json.loads(proc.stdout)
                else:
                    logger.warning(
                        "ClinicalTrials.gov curl fallback failed (exit %d)",
                        proc.returncode,
                    )
            except Exception as curl_exc:
                logger.warning("ClinicalTrials.gov curl fallback error: %s", curl_exc)

        if data is None:
            return signals

        studies = data.get("studies", [])
        for study in studies:
            protocol = study.get("protocolSection", {})
            ident = protocol.get("identificationModule", {})
            status_mod = protocol.get("statusModule", {})
            sponsor_mod = protocol.get("sponsorCollaboratorsModule", {})
            design_mod = protocol.get("designModule", {})

            nct_id = ident.get("nctId", "")
            title = ident.get("briefTitle", "Untitled trial")
            sponsor = sponsor_mod.get("leadSponsor", {}).get("name", "Unknown")
            phase_list = design_mod.get("phases", [])
            phase = phase_list[0] if phase_list else "N/A"
            overall_status = status_mod.get("overallStatus", "Unknown")

            signals.append(
                Signal(
                    company_name=sponsor,
                    signal_type="clinical_trial",
                    headline=f"Trial update: {title[:120]}",
                    summary=(
                        f"NCT: {nct_id}. Sponsor: {sponsor}. "
                        f"Phase: {phase}. Status: {overall_status}."
                    ),
                    source_url=f"https://clinicaltrials.gov/study/{nct_id}",
                    source_name="ClinicalTrials.gov",
                    metadata={
                        "nct_id": nct_id,
                        "phase": phase,
                        "overall_status": overall_status,
                        "sponsor": sponsor,
                    },
                )
            )

        return signals

    async def _scan_sec_edgar(self, company_names: list[str]) -> list[Signal]:
        """Scan SEC EDGAR for new filings from monitored companies.

        Checks the EDGAR submissions API for recent 10-K, 10-Q, 8-K,
        and S-1 filings.

        Args:
            company_names: Company names to search for.

        Returns:
            List of Signal objects from SEC filing matches.
        """
        import httpx

        signals: list[Signal] = []

        async with httpx.AsyncClient(
            timeout=20.0,
            headers={
                "User-Agent": DEFAULT_USER_AGENT,
                "Accept": "application/json",
            },
        ) as client:
            # Search via the company tickers lookup
            try:
                resp = await client.get(
                    "https://www.sec.gov/files/company_tickers.json",
                )
                if resp.status_code != 200:
                    return signals
                tickers_data = resp.json()
            except httpx.HTTPError as exc:
                logger.warning("SEC tickers lookup failed: %s", exc)
                return signals

            for company in company_names[:10]:
                company_lower = company.lower()
                cik = None
                for entry in tickers_data.values():
                    if company_lower in str(entry.get("title", "")).lower():
                        cik = str(entry.get("cik_str", "")).zfill(10)
                        break

                if not cik:
                    continue

                try:
                    resp = await client.get(
                        f"{SEC_EDGAR_SUBMISSIONS_URL}/CIK{cik}.json",
                    )
                    if resp.status_code != 200:
                        continue

                    data = resp.json()
                    company_name = data.get("name", company)
                    recent = data.get("filings", {}).get("recent", {})
                    forms = recent.get("form", [])
                    dates = recent.get("filingDate", [])
                    accessions = recent.get("accessionNumber", [])
                    descriptions = recent.get("primaryDocDescription", [])

                    target_forms = {"10-K", "10-Q", "8-K", "S-1", "6-K"}
                    for i, form in enumerate(forms[:20]):
                        if form not in target_forms:
                            continue
                        accession = accessions[i] if i < len(accessions) else ""
                        accession_path = accession.replace("-", "")

                        signals.append(
                            Signal(
                                company_name=company_name,
                                signal_type="sec_filing",
                                headline=(
                                    f"SEC {form}: {company_name} "
                                    f"({dates[i] if i < len(dates) else ''})"
                                ),
                                summary=(
                                    descriptions[i] if i < len(descriptions) else f"{form} filing"
                                ),
                                source_url=(
                                    f"https://www.sec.gov/Archives/"
                                    f"edgar/data/{cik}/{accession_path}/"
                                ),
                                source_name="SEC EDGAR",
                                metadata={
                                    "form_type": form,
                                    "cik": cik,
                                    "accession_number": accession,
                                    "filed_date": (dates[i] if i < len(dates) else ""),
                                },
                            )
                        )

                except httpx.HTTPError as exc:
                    logger.warning("SEC EDGAR scan for %s failed: %s", company, exc)

        return signals

    async def _scan_patents(self, keywords: list[str]) -> list[Signal]:
        """Scan for recent patent publications via Google Patents.

        The old USPTO IBD API was retired in 2025. This method now uses
        Google Patents XHR as the primary source.

        Args:
            keywords: Search terms for patent text search.

        Returns:
            List of Signal objects from patent matches.
        """
        import httpx

        signals: list[Signal] = []
        search_text = " OR ".join(keywords[:10])

        try:
            async with httpx.AsyncClient(
                timeout=20.0,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": "application/json",
                },
            ) as client:
                resp = await client.get(
                    GOOGLE_PATENTS_XHR_URL,
                    params={"url": f"q={search_text}&oq={search_text}&num=20"},
                )
                if resp.status_code != 200:
                    logger.info(
                        "Google Patents returned %d for patent scan",
                        resp.status_code,
                    )
                    return signals

                data = resp.json()
                clusters = data.get("results", {}).get("cluster", [])
                for cluster in clusters:
                    for result in cluster.get("result", []):
                        patent_info = result.get("patent", {})
                        pub_number = patent_info.get("publication_number", "")
                        title = patent_info.get("title", "Untitled patent")
                        snippet = result.get("snippet", "")
                        assignee = patent_info.get("assignee", "")
                        filing_date = patent_info.get("filing_date", "")
                        pub_date = patent_info.get("publication_date", "")

                        if title:
                            signals.append(
                                Signal(
                                    company_name=assignee or "Unknown",
                                    signal_type="patent",
                                    headline=title,
                                    summary=snippet[:500],
                                    source_url=f"https://patents.google.com/patent/{pub_number}",
                                    source_name="Google Patents",
                                    metadata={
                                        "publication_number": pub_number,
                                        "filed_date": filing_date,
                                        "publication_date": pub_date,
                                    },
                                )
                            )

        except httpx.HTTPError as exc:
            logger.warning("Google Patents scan failed: %s", exc)

        return signals

    async def _scan_wire_services(self, company_names: list[str]) -> list[Signal]:
        """Scan PR Newswire and GlobeNewswire for press releases.

        Args:
            company_names: Company names to search for.

        Returns:
            List of Signal objects from press release matches.
        """
        import httpx

        signals: list[Signal] = []

        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={"User-Agent": DEFAULT_USER_AGENT},
        ) as client:
            for company in company_names[:10]:
                # PR Newswire
                try:
                    resp = await client.get(
                        PR_NEWSWIRE_SEARCH_URL,
                        params={
                            "keyword": company,
                            "page": "1",
                            "pagesize": "5",
                        },
                    )
                    if resp.status_code == 200:
                        pr_signals = self._parse_wire_html(resp.text, company, "PR Newswire")
                        signals.extend(pr_signals)
                except httpx.HTTPError as exc:
                    logger.warning(
                        "PR Newswire search for %s failed: %s",
                        company,
                        exc,
                    )

                # GlobeNewswire
                try:
                    resp = await client.get(
                        GLOBENEWSWIRE_SEARCH_URL,
                        params={
                            "keyword": company,
                            "pageSize": "5",
                        },
                    )
                    if resp.status_code == 200:
                        gn_signals = self._parse_wire_html(resp.text, company, "GlobeNewswire")
                        signals.extend(gn_signals)
                except httpx.HTTPError as exc:
                    logger.warning(
                        "GlobeNewswire search for %s failed: %s",
                        company,
                        exc,
                    )

        return signals

    async def _scan_social(self, company_names: list[str]) -> list[Signal]:
        """Scan LinkedIn company pages for signals.

        Uses public LinkedIn company data. In production this would use
        the LinkedIn Marketing API (requires OAuth). Currently extracts
        from public company pages via web scraping.

        Args:
            company_names: Company names to check.

        Returns:
            List of Signal objects from social monitoring.
        """
        import httpx

        signals: list[Signal] = []

        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={
                "User-Agent": ("Mozilla/5.0 (compatible; ARIA-Intelligence/1.0)"),
            },
        ) as client:
            for company in company_names[:5]:
                slug = company.lower().replace(" ", "-").replace(",", "")
                try:
                    resp = await client.get(
                        f"https://www.linkedin.com/company/{slug}/posts/",
                    )
                    if resp.status_code != 200:
                        continue

                    # Extract basic signals from company page
                    social_signals = self._parse_linkedin_page(resp.text, company)
                    signals.extend(social_signals)
                except httpx.HTTPError as exc:
                    logger.warning("LinkedIn scan for %s failed: %s", company, exc)

        return signals

    # ── Helper methods ───────────────────────────────────────────────

    async def _get_monitored_entities(self, user_id: str) -> list[dict[str, Any]]:
        """Fetch active monitored entities for a user.

        Args:
            user_id: User UUID.

        Returns:
            List of entity dicts from monitored_entities table.
        """
        client = SupabaseClient.get_client()
        try:
            resp = (
                client.table("monitored_entities")
                .select("*")
                .eq("user_id", user_id)
                .eq("is_active", True)
                .execute()
            )
            return resp.data or []
        except Exception as exc:
            logger.warning("Failed to fetch monitored entities: %s", exc)
            return []

    async def _update_last_checked(self, user_id: str) -> None:
        """Update last_checked_at on all active monitored entities.

        Args:
            user_id: User UUID.
        """
        client = SupabaseClient.get_client()
        try:
            (
                client.table("monitored_entities")
                .update({"last_checked_at": datetime.now(UTC).isoformat()})
                .eq("user_id", user_id)
                .eq("is_active", True)
                .execute()
            )
        except Exception as exc:
            logger.warning("Failed to update last_checked_at: %s", exc)

    async def _build_user_context(self, user_id: str) -> dict[str, Any]:
        """Build user context for relevance scoring and implications.

        Loads from monitored_entities, lead_memory, and corporate memory
        to assemble the user's competitive landscape.

        Args:
            user_id: User UUID.

        Returns:
            Dict with tracked_competitors, lead_companies,
            therapeutic_areas, products, company_name.
        """
        client = SupabaseClient.get_client()
        context: dict[str, Any] = {
            "tracked_competitors": [],
            "lead_companies": [],
            "therapeutic_areas": [],
            "products": [],
            "company_name": "",
        }

        try:
            # Monitored entities → competitors + topics
            entities_resp = (
                client.table("monitored_entities")
                .select("entity_type, entity_name, monitoring_config")
                .eq("user_id", user_id)
                .eq("is_active", True)
                .execute()
            )
            for entity in entities_resp.data or []:
                if entity.get("entity_type") == "company":
                    context["tracked_competitors"].append(entity["entity_name"])
                elif entity.get("entity_type") == "topic":
                    context["therapeutic_areas"].append(entity["entity_name"])

            # Lead memory → companies from active leads
            leads_resp = (
                client.table("leads")
                .select("company_name")
                .eq("user_id", user_id)
                .eq("lifecycle_stage", "active")
                .limit(50)
                .execute()
            )
            context["lead_companies"] = [
                lead["company_name"] for lead in (leads_resp.data or []) if lead.get("company_name")
            ]

            # User's own company from user_profiles with companies join
            profile_resp = (
                client.table("user_profiles")
                .select("company_id, companies(name, settings)")
                .eq("id", user_id)
                .maybe_single()
                .execute()
            )
            if profile_resp and profile_resp.data:
                company_data = profile_resp.data.get("companies")
                if company_data and isinstance(company_data, dict):
                    context["company_name"] = company_data.get("name", "")
                    # Products from company settings
                    company_settings = company_data.get("settings") or {}
                    context["products"] = company_settings.get("products", [])

        except Exception as exc:
            logger.warning("Failed to build user context: %s", exc)

        return context

    def _parse_rss_feed(
        self,
        xml_text: str,
        feed_name: str,
        entity_names_lower: list[str],
    ) -> list[Signal]:
        """Parse RSS/Atom XML and extract matching signals.

        Uses a lightweight XML parser to avoid heavy dependencies.
        Matches articles whose title or description contain any
        monitored entity name.

        Args:
            xml_text: Raw XML string from RSS feed.
            feed_name: Name key from RSS_FEEDS dict.
            entity_names_lower: Lowercased entity names to match against.

        Returns:
            List of Signal objects matching entities.
        """
        import xml.etree.ElementTree as ET

        signals: list[Signal] = []

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            logger.warning("Failed to parse RSS feed: %s", feed_name)
            return signals

        # Handle both RSS 2.0 and Atom
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        items = root.findall(".//item")  # RSS 2.0
        if not items:
            items = root.findall(".//atom:entry", ns)  # Atom

        for item in items[:30]:
            # RSS 2.0 fields
            title_el = item.find("title")
            if title_el is None:
                title_el = item.find("atom:title", ns)
            desc_el = item.find("description")
            if desc_el is None:
                desc_el = item.find("atom:summary", ns)
            link_el = item.find("link")
            if link_el is None:
                link_el = item.find("atom:link", ns)
            pub_el = item.find("pubDate")
            if pub_el is None:
                pub_el = item.find("atom:published", ns)

            title = (title_el.text or "") if title_el is not None else ""
            description = (desc_el.text or "") if desc_el is not None else ""
            link = ""
            if link_el is not None:
                link = link_el.text or link_el.get("href", "") or ""
            pub_date = (pub_el.text or "") if pub_el is not None else ""

            # Match against entities
            combined = f"{title} {description}".lower()
            matched_entity = ""
            for entity in entity_names_lower:
                if entity in combined:
                    matched_entity = entity
                    break

            if not matched_entity:
                continue

            signal_type = self._classify_headline(title)

            signals.append(
                Signal(
                    company_name=matched_entity.title(),
                    signal_type=signal_type,
                    headline=title[:300],
                    summary=self._strip_html_tags(description)[:500],
                    source_url=link,
                    source_name=feed_name.replace("_", " ").title(),
                    metadata={
                        "feed": feed_name,
                        "published": pub_date,
                    },
                )
            )

        return signals

    def _parse_wire_html(self, html: str, company: str, source: str) -> list[Signal]:
        """Parse wire service HTML into Signal objects.

        Args:
            html: Raw HTML from wire service search.
            company: Company name searched for.
            source: Wire service name.

        Returns:
            List of Signal objects.
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return []

        signals: list[Signal] = []
        soup = BeautifulSoup(html, "html.parser")

        articles = (
            soup.find_all("div", class_="row")
            or soup.find_all("article")
            or soup.find_all("div", class_="main-container")
        )

        for article in articles[:5]:
            title_tag = article.find("h3") or article.find("h2") or article.find("a")
            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            link_tag = article.find("a", href=True)
            url = ""
            if link_tag:
                href = str(link_tag["href"])
                base = (
                    "https://www.prnewswire.com"
                    if "PR" in source
                    else "https://www.globenewswire.com"
                )
                url = href if href.startswith("http") else f"{base}{href}"

            snippet_tag = article.find("p")
            snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""

            signal_type = self._classify_headline(title)

            signals.append(
                Signal(
                    company_name=company,
                    signal_type=signal_type,
                    headline=title[:300],
                    summary=snippet[:500],
                    source_url=url,
                    source_name=source,
                    metadata={"wire_service": source},
                )
            )

        return signals

    def _parse_linkedin_page(self, html: str, company: str) -> list[Signal]:
        """Extract basic signals from LinkedIn company page HTML.

        LinkedIn heavily rate-limits scraping. This is best-effort
        extraction from the public page; production should use the
        LinkedIn Marketing API via Composio OAuth.

        Args:
            html: Raw HTML from LinkedIn company page.
            company: Company name.

        Returns:
            List of Signal objects (may be empty if rate-limited).
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return []

        signals: list[Signal] = []
        soup = BeautifulSoup(html, "html.parser")

        # Look for hiring signals in job count
        job_elements = soup.find_all(string=lambda t: t and "job" in t.lower() if t else False)
        for elem in job_elements[:1]:
            text = elem.strip()
            if any(char.isdigit() for char in text):
                signals.append(
                    Signal(
                        company_name=company,
                        signal_type="hiring",
                        headline=f"{company} hiring activity detected",
                        summary=text[:300],
                        source_url=(
                            f"https://www.linkedin.com/company/"
                            f"{company.lower().replace(' ', '-')}/jobs/"
                        ),
                        source_name="LinkedIn",
                        metadata={"platform": "linkedin"},
                    )
                )

        return signals

    def _build_implications_prompt(self, signal: Signal, knowledge_context: dict[str, Any]) -> str:
        """Build the LLM prompt for implication detection.

        Args:
            signal: The signal to analyse.
            knowledge_context: User's business context.

        Returns:
            Formatted prompt string.
        """
        competitors = ", ".join(knowledge_context.get("tracked_competitors", [])[:10])
        leads = ", ".join(knowledge_context.get("lead_companies", [])[:10])
        areas = ", ".join(knowledge_context.get("therapeutic_areas", [])[:10])
        products = ", ".join(knowledge_context.get("products", [])[:10])
        user_company = knowledge_context.get("company_name", "Unknown")

        return f"""Analyse this market signal and identify 1-3 non-obvious implications for the user's business.

SIGNAL:
- Company: {signal.company_name}
- Type: {signal.signal_type}
- Headline: {signal.headline}
- Summary: {signal.summary}

USER CONTEXT:
- User's company: {user_company}
- Tracked competitors: {competitors or "None"}
- Active leads: {leads or "None"}
- Therapeutic areas: {areas or "None"}
- Products: {products or "None"}

Think about:
1. Second-order effects (e.g., "Company X acquired a CDMO" → their clients may need new partners)
2. Competitive dynamics (e.g., "Competitor got FDA approval" → market share implications)
3. Pipeline opportunities (e.g., "New regulation" → which leads need this capability?)
4. Relationship impacts (e.g., "Leadership change at a lead" → relationship risk)

Respond with JSON:
{{
  "implications": [
    {{
      "description": "Brief description of the implication",
      "affected_entities": ["entity1", "entity2"],
      "confidence": 0.0-1.0,
      "action_suggestion": "What the user should do",
      "reasoning": "Why this matters"
    }}
  ]
}}"""

    def _parse_implications_response(self, response: str, signal_id: str) -> list[Implication]:
        """Parse LLM JSON response into Implication objects.

        Args:
            response: Raw LLM response string.
            signal_id: ID of the source signal.

        Returns:
            List of Implication objects.
        """
        implications: list[Implication] = []

        try:
            # Strip markdown code fences if present
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            cleaned = cleaned.strip()

            data = json.loads(cleaned)
            for item in data.get("implications", []):
                implications.append(
                    Implication(
                        signal_id=signal_id,
                        description=item.get("description", ""),
                        affected_entities=item.get("affected_entities", []),
                        confidence=float(item.get("confidence", 0.5)),
                        action_suggestion=item.get("action_suggestion", ""),
                        reasoning=item.get("reasoning", ""),
                    )
                )
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("Failed to parse implications response: %s", exc)

        return implications

    def _deduplicate_signals(self, signals: list[Signal]) -> list[Signal]:
        """Remove duplicate signals by URL and headline similarity.

        Args:
            signals: Raw signal list.

        Returns:
            Deduplicated signal list.
        """
        seen_urls: set[str] = set()
        seen_hashes: set[str] = set()
        deduped: list[Signal] = []

        for signal in signals:
            # Skip exact URL duplicates
            if signal.source_url and signal.source_url in seen_urls:
                continue

            # Skip very similar headlines (hash first 6 words)
            headline_key = hashlib.md5(
                " ".join(signal.headline.lower().split()[:6]).encode()
            ).hexdigest()
            if headline_key in seen_hashes:
                continue

            seen_urls.add(signal.source_url)
            seen_hashes.add(headline_key)
            deduped.append(signal)

        return deduped

    def _store_market_signal(
        self,
        client: Any,
        user_id: str,
        signal: Signal,
    ) -> None:
        """Insert a signal into market_signals table.

        Args:
            client: Supabase client.
            user_id: User UUID.
            signal: Signal to store.
        """
        try:
            client.table("market_signals").insert(
                {
                    "id": signal.id,
                    "user_id": user_id,
                    "company_name": signal.company_name,
                    "signal_type": signal.signal_type,
                    "headline": signal.headline[:500],
                    "summary": (signal.summary or "")[:2000],
                    "source_url": signal.source_url,
                    "source_name": signal.source_name,
                    "relevance_score": signal.relevance_score,
                    "detected_at": signal.detected_at.isoformat(),
                    "linked_lead_id": signal.linked_lead_id,
                    "metadata": signal.metadata,
                }
            ).execute()
        except Exception as exc:
            logger.warning(
                "Failed to store market signal: %s",
                exc,
                extra={
                    "user_id": user_id,
                    "headline": signal.headline[:100],
                },
            )

    @staticmethod
    def _classify_headline(title: str) -> str:
        """Classify a headline into a signal type.

        Args:
            title: Article/release headline.

        Returns:
            Signal type string.
        """
        title_lower = title.lower()
        if any(kw in title_lower for kw in ("fda", "approval", "cleared", "authorized", "510(k)")):
            return "fda_approval"
        if any(kw in title_lower for kw in ("warning letter", "recall", "enforcement")):
            return "fda_warning_letter"
        if any(
            kw in title_lower for kw in ("trial", "phase", "clinical", "endpoint", "enrollment")
        ):
            return "clinical_trial"
        if any(kw in title_lower for kw in ("patent", "intellectual property", "ip filing")):
            return "patent"
        if any(kw in title_lower for kw in ("funding", "raise", "investment", "series", "ipo")):
            return "funding"
        if any(
            kw in title_lower
            for kw in (
                "hire",
                "appoint",
                "ceo",
                "cfo",
                "cmo",
                "officer",
                "board",
                "resign",
            )
        ):
            return "leadership"
        if any(kw in title_lower for kw in ("partnership", "collaboration", "agreement", "deal")):
            return "partnership"
        if any(
            kw in title_lower
            for kw in ("revenue", "earnings", "quarter", "annual", "q1", "q2", "q3", "q4")
        ):
            return "earnings"
        if any(
            kw in title_lower for kw in ("launch", "product", "platform", "release", "pipeline")
        ):
            return "product"
        if any(kw in title_lower for kw in ("hiring", "jobs", "positions", "talent", "workforce")):
            return "hiring"
        return "market_trend"

    @staticmethod
    def _strip_html_tags(text: str) -> str:
        """Remove HTML tags from text.

        Args:
            text: Text potentially containing HTML.

        Returns:
            Clean text string.
        """
        import re

        return re.sub(r"<[^>]+>", "", text).strip()

    @staticmethod
    def _extract_facts_from_signals(signals: list[Signal], user_id: str) -> list[dict[str, Any]]:
        """Extract semantic facts from signals for Graphiti/pgvector.

        Args:
            signals: List of Signal objects.
            user_id: Authenticated user UUID.

        Returns:
            List of fact dicts for CapabilityResult.extracted_facts.
        """
        return [
            {
                "subject": signal.company_name,
                "predicate": f"signal_{signal.signal_type}",
                "object": signal.headline,
                "confidence": min(0.90, signal.relevance_score + 0.1),
                "source": f"signal_radar:{user_id}",
            }
            for signal in signals
        ]

    @staticmethod
    def _extract_facts_from_implications(
        implications: list[Implication], user_id: str
    ) -> list[dict[str, Any]]:
        """Extract semantic facts from LLM-derived implications.

        Args:
            implications: List of Implication objects.
            user_id: Authenticated user UUID.

        Returns:
            List of fact dicts for CapabilityResult.extracted_facts.
        """
        facts: list[dict[str, Any]] = []
        for impl in implications:
            for entity in impl.affected_entities:
                facts.append(
                    {
                        "subject": entity,
                        "predicate": "implication_detected",
                        "object": impl.description,
                        "confidence": impl.confidence,
                        "source": f"signal_radar_implication:{user_id}",
                    }
                )
        return facts


# ── Scheduler helper ───────────────────────────────────────────────────


async def run_signal_radar_scan(user_id: str) -> dict[str, Any]:
    """Run a full signal radar scan for a single user.

    This is the entry point for the SyncScheduler cron. It creates a
    throwaway SignalRadarCapability instance and runs scan_all_sources.

    Args:
        user_id: User UUID to scan for.

    Returns:
        Summary dict with scan results.
    """
    from src.agents.capabilities.base import UserContext

    client = SupabaseClient.get_client()

    capability = SignalRadarCapability(
        supabase_client=client,
        memory_service=None,
        knowledge_graph=None,
        user_context=UserContext(user_id=user_id),
    )

    signals = await capability.scan_all_sources(user_id)

    # Run implication detection on top signals
    implication_triggers_total = 0
    if signals:
        from src.skills.implication_trigger import process_signal_with_implications

        user_context = await capability._build_user_context(user_id)
        top_signals = [s for s in signals if s.relevance_score >= 0.6][:5]
        for signal in top_signals:
            # Run both legacy implication detection (for Graphiti facts)
            # and the new implication-aware skill triggering
            await capability.detect_implications(signal, user_context)
            try:
                triggers = await process_signal_with_implications(signal, user_id)
                implication_triggers_total += len(triggers)
            except Exception as exc:
                logger.warning(
                    "Implication skill triggering failed for signal %s: %s",
                    signal.id,
                    exc,
                )

    return {
        "user_id": user_id,
        "signals_found": len(signals),
        "high_relevance": len([s for s in signals if s.relevance_score >= 0.7]),
        "implication_triggers": implication_triggers_total,
    }


async def run_signal_radar_cron() -> None:
    """Cron entry point: scan all users with active monitored entities.

    Designed to be called hourly during business hours (8am-8pm)
    by the SyncScheduler.
    """
    import asyncio

    client = SupabaseClient.get_client()

    try:
        # Find all users with active monitoring
        resp = client.table("monitored_entities").select("user_id").eq("is_active", True).execute()
        user_ids = list({row["user_id"] for row in (resp.data or [])})
    except Exception as exc:
        logger.error("Failed to fetch users for signal radar cron: %s", exc)
        return

    if not user_ids:
        logger.info("No users with active monitoring for signal radar")
        return

    logger.info("Signal radar cron starting for %d users", len(user_ids))

    # Process users in parallel (max 5 concurrent)
    semaphore = asyncio.Semaphore(5)

    async def _scan_with_limit(uid: str) -> dict[str, Any] | None:
        async with semaphore:
            try:
                return await run_signal_radar_scan(uid)
            except Exception as exc:
                logger.error(
                    "Signal radar scan failed for user %s: %s",
                    uid,
                    exc,
                )
                return None

    results = await asyncio.gather(
        *[_scan_with_limit(uid) for uid in user_ids],
        return_exceptions=True,
    )

    successes = sum(1 for r in results if isinstance(r, dict) and r is not None)
    logger.info(
        "Signal radar cron complete: %d/%d users scanned",
        successes,
        len(user_ids),
    )
