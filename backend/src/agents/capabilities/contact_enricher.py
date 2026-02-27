"""Contact enrichment capability for HunterAgent.

Aggregates enrichment data from multiple providers (Exa primary, Apollo
secondary when available), merges results with source attribution and
per-field confidence, caches in lead_memory_stakeholders with 7-day TTL,
and detects intent signals from enrichment data.

Key responsibilities:
- Enrich individual contacts with profile intelligence
- Build org charts by discovering people at a company
- Detect intent signals (job changes, growth, publications)
- Cache results with TTL to avoid redundant API calls

Integration Checklist:
- [x] Data stored in lead_memory_stakeholders (Lead Memory)
- [x] Semantic facts extracted for Graphiti/pgvector
- [x] Signals detected → market_signals / notifications
- [x] Activity logged to aria_activity
- [x] Source and confidence per field
"""

import json
import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel, Field

from src.agents.capabilities.base import BaseCapability, CapabilityResult
from src.agents.capabilities.enrichment_providers.base import (
    BaseEnrichmentProvider,
    CompanyEnrichment,
    PersonEnrichment,
)
from src.agents.capabilities.enrichment_providers.exa_provider import (
    ExaEnrichmentProvider,
)
from src.core.llm import LLMClient
from src.core.task_types import TaskType
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)

# Cache TTL for enrichment results
CACHE_TTL_DAYS = 7


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


class EnrichedContact(BaseModel):
    """Merged enrichment result with source attribution per field."""

    name: str
    company: str = ""
    role: str = ""
    profile_intelligence: dict[str, Any] = Field(
        default_factory=dict,
        description="Intelligence from Exa (web presence, publications, bio)",
    )
    contact_details: dict[str, Any] = Field(
        default_factory=dict,
        description="Contact info from Apollo/ZoomInfo (email, phone, etc.)",
    )
    field_sources: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
        description="Per-field source and confidence: {field: {source, confidence, value}}",
    )
    overall_confidence: float = 0.0
    enriched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    cached: bool = False


class OrgChartEntry(BaseModel):
    """A person discovered during org chart building."""

    name: str
    title: str = ""
    department: str = ""
    linkedin_url: str = ""
    relationship_to_target: str = ""
    confidence: float = 0.0


class IntentSignal(BaseModel):
    """A detected intent signal from enrichment data."""

    signal_type: str = ""  # job_change, company_growth, publication, hiring
    contact_name: str = ""
    company: str = ""
    description: str = ""
    relevance_score: float = 0.0
    source_url: str = ""
    detected_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ---------------------------------------------------------------------------
# Capability implementation
# ---------------------------------------------------------------------------


class ContactEnricherCapability(BaseCapability):
    """Contact enrichment using Exa as primary provider.

    Designed for HunterAgent to enrich leads and contacts with
    profile intelligence, org charts, and intent signals.

    Task types:
    - ``enrich_contact``: Enrich a single contact
    - ``build_org_chart``: Discover people at a company
    - ``detect_intent_signals``: Scan contacts for intent signals
    """

    capability_name: str = "contact-enricher"
    agent_types: list[str] = ["HunterAgent"]
    oauth_scopes: list[str] = []
    data_classes: list[str] = ["INTERNAL", "CONFIDENTIAL"]

    def __init__(
        self,
        supabase_client: Any,
        memory_service: Any,
        knowledge_graph: Any,
        user_context: Any,
    ) -> None:
        super().__init__(supabase_client, memory_service, knowledge_graph, user_context)
        self._providers: list[BaseEnrichmentProvider] = [ExaEnrichmentProvider()]
        self._llm = LLMClient()

    # ── BaseCapability abstract interface ──────────────────────────────

    async def can_handle(self, task: dict[str, Any]) -> float:
        """Return confidence for contact enrichment tasks."""
        task_type = task.get("type", "")
        if task_type in {"enrich_contact", "build_org_chart", "detect_intent_signals"}:
            return 0.95
        if any(
            kw in task_type.lower()
            for kw in ("enrich", "contact", "org_chart", "stakeholder", "intent")
        ):
            return 0.6
        return 0.0

    async def execute(
        self,
        task: dict[str, Any],
        context: dict[str, Any],  # noqa: ARG002
    ) -> CapabilityResult:
        """Route to the correct method based on task type."""
        start = time.monotonic()
        task_type = task.get("type", "")

        try:
            if task_type == "enrich_contact":
                name = task.get("name", "")
                company = task.get("company", "")
                role = task.get("role", "")
                result = await self.enrich_contact(name, company, role)
                data = result.model_dump(mode="json")
                facts = self._extract_facts_from_contact(result)

            elif task_type == "build_org_chart":
                company_name = task.get("company_name", "")
                entries = await self.build_org_chart(company_name)
                data = {
                    "company": company_name,
                    "org_chart": [e.model_dump(mode="json") for e in entries],
                }
                facts = self._extract_facts_from_org_chart(entries, company_name)

            elif task_type == "detect_intent_signals":
                contacts = task.get("contacts", [])
                signals = await self.detect_intent_signals(contacts)
                data = {"signals": [s.model_dump(mode="json") for s in signals]}
                facts = self._extract_facts_from_signals(signals)

            else:
                return CapabilityResult(
                    success=False,
                    error=f"Unknown task type: {task_type}",
                    execution_time_ms=int((time.monotonic() - start) * 1000),
                )

            elapsed_ms = int((time.monotonic() - start) * 1000)
            await self.log_activity(
                activity_type="contact_enrichment",
                title=f"Contact enrichment: {task_type}",
                description=f"Completed {task_type} for user {self._user_context.user_id}",
                confidence=0.80,
                metadata={"task_type": task_type},
            )
            return CapabilityResult(
                success=True,
                data=data,
                extracted_facts=facts,
                execution_time_ms=elapsed_ms,
            )

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.exception("Contact enrichment capability failed")
            return CapabilityResult(
                success=False,
                error=str(exc),
                execution_time_ms=elapsed_ms,
            )

    def get_data_classes_accessed(self) -> list[str]:
        """Declare data classification levels."""
        return ["internal", "confidential"]

    # ── Public methods ────────────────────────────────────────────────

    async def enrich_contact(
        self,
        name: str,
        company: str = "",
        role: str = "",
    ) -> EnrichedContact:
        """Enrich a single contact using all available providers.

        Checks cache first (7-day TTL). If cache miss, queries all
        providers and merges results with per-field source attribution.

        Profile intelligence (Exa) is separated from contact details
        (Apollo, when available) so the UI can distinguish data sources.

        Args:
            name: Full name of the contact.
            company: Company name for disambiguation.
            role: Role/title for disambiguation.

        Returns:
            EnrichedContact with merged data and source attribution.
        """
        user_id = self._user_context.user_id

        # Check cache
        cached = await self._get_cached_enrichment(name, company, user_id)
        if cached:
            logger.info(
                "Cache hit for contact enrichment",
                extra={"name": name, "company": company},
            )
            return cached

        # Query all providers
        person_results: list[PersonEnrichment] = []
        for provider in self._providers:
            try:
                result = await provider.search_person(name, company, role)
                person_results.append(result)
            except Exception as exc:
                logger.warning(
                    "Provider %s failed for person search: %s",
                    provider.provider_name,
                    exc,
                )

        # Merge results
        enriched = self._merge_person_results(name, company, role, person_results)

        # Cache in lead_memory_stakeholders
        await self._cache_enrichment(enriched, user_id)

        return enriched

    async def build_org_chart(
        self,
        company_name: str,
    ) -> list[OrgChartEntry]:
        """Find multiple people at a company and infer relationships.

        Uses Exa to discover leadership, department heads, and key
        stakeholders. Results are stored in lead_memory_stakeholders.

        Args:
            company_name: Company name to build org chart for.

        Returns:
            List of OrgChartEntry objects with inferred relationships.
        """
        user_id = self._user_context.user_id
        entries: list[OrgChartEntry] = []

        # Use Exa to find company leadership
        exa = self._get_exa_provider()
        if not exa:
            return entries

        company_enrichment = await exa.search_company(company_name)

        # Use LLM to extract people from company enrichment
        people = await self._extract_people_from_company(company_name, company_enrichment)

        for person_data in people:
            entry = OrgChartEntry(
                name=person_data.get("name", ""),
                title=person_data.get("title", ""),
                department=person_data.get("department", ""),
                linkedin_url=person_data.get("linkedin_url", ""),
                relationship_to_target=person_data.get("relationship", ""),
                confidence=person_data.get("confidence", 0.5),
            )
            entries.append(entry)

            # Store each person in lead_memory_stakeholders
            await self._store_stakeholder(
                user_id=user_id,
                name=entry.name,
                company=company_name,
                title=entry.title,
                department=entry.department,
                linkedin_url=entry.linkedin_url,
                relationship=entry.relationship_to_target,
                confidence=entry.confidence,
                source="exa_org_chart",
            )

        await self.log_activity(
            activity_type="org_chart_built",
            title=f"Org chart built: {company_name}",
            description=f"Discovered {len(entries)} people at {company_name}",
            confidence=0.75,
            related_entity_type="company",
            metadata={"company": company_name, "people_found": len(entries)},
        )

        return entries

    async def detect_intent_signals(
        self,
        contacts: list[dict[str, Any]],
    ) -> list[IntentSignal]:
        """Detect intent signals from contact enrichment data.

        Scans for:
        - Job changes (new role, new company)
        - Company growth signals (funding, hiring)
        - Publication activity (new papers, patents)

        Args:
            contacts: List of contact dicts with name, company, role.

        Returns:
            List of IntentSignal objects.
        """
        signals: list[IntentSignal] = []
        user_id = self._user_context.user_id

        for contact in contacts:
            name = contact.get("name", "")
            company = contact.get("company", "")
            role = contact.get("role", "")

            if not name:
                continue

            # Get fresh enrichment (bypass cache to detect changes)
            exa = self._get_exa_provider()
            if not exa:
                continue

            try:
                person = await exa.search_person(name, company, role)
            except Exception as exc:
                logger.warning("Intent signal detection failed for %s: %s", name, exc)
                continue

            # Check for job changes
            if person.title and role and person.title.lower() != role.lower():
                signals.append(
                    IntentSignal(
                        signal_type="job_change",
                        contact_name=name,
                        company=company,
                        description=(
                            f"{name} may have changed roles: "
                            f"was '{role}', now appears as '{person.title}'"
                        ),
                        relevance_score=0.8,
                        source_url=person.linkedin_url,
                    )
                )

            # Check for publication activity
            pubs = await exa.search_publications(name)
            recent_pubs = [
                p
                for p in pubs
                if p.published_date
                and p.published_date >= (datetime.now(UTC) - timedelta(days=90)).isoformat()
            ]
            if recent_pubs:
                signals.append(
                    IntentSignal(
                        signal_type="publication",
                        contact_name=name,
                        company=company,
                        description=(
                            f"{name} has {len(recent_pubs)} recent publication(s): "
                            f"{recent_pubs[0].title}"
                        ),
                        relevance_score=0.6,
                        source_url=recent_pubs[0].url,
                    )
                )

            # Check company growth via web mentions
            for mention in person.web_mentions:
                snippet = mention.get("snippet", "").lower()
                if any(
                    kw in snippet
                    for kw in ("funding", "series", "raised", "growth", "expansion", "hiring")
                ):
                    signals.append(
                        IntentSignal(
                            signal_type="company_growth",
                            contact_name=name,
                            company=company,
                            description=mention.get("title", "Company growth signal detected"),
                            relevance_score=0.7,
                            source_url=mention.get("url", ""),
                        )
                    )
                    break  # One growth signal per contact

        # Store high-relevance signals as market_signals
        if signals:
            client = SupabaseClient.get_client()
            for signal in signals:
                if signal.relevance_score >= 0.6:
                    self._store_market_signal(
                        client=client,
                        user_id=user_id,
                        signal=signal,
                    )

        return signals

    # ── Provider management ───────────────────────────────────────────

    def add_provider(self, provider: BaseEnrichmentProvider) -> None:
        """Register an additional enrichment provider.

        Args:
            provider: An enrichment provider instance to add.
        """
        self._providers.append(provider)

    def _get_exa_provider(self) -> ExaEnrichmentProvider | None:
        """Return the Exa provider if available."""
        for p in self._providers:
            if isinstance(p, ExaEnrichmentProvider):
                return p
        return None

    # ── Private helpers ───────────────────────────────────────────────

    def _merge_person_results(
        self,
        name: str,
        company: str,
        role: str,
        results: list[PersonEnrichment],
    ) -> EnrichedContact:
        """Merge results from multiple providers with source attribution.

        Exa results go into ``profile_intelligence``; Apollo/ZoomInfo
        results would go into ``contact_details``.

        Args:
            name: Contact name.
            company: Company name.
            role: Role/title.
            results: PersonEnrichment from each provider.

        Returns:
            EnrichedContact with merged data.
        """
        enriched = EnrichedContact(name=name, company=company, role=role)
        field_sources: dict[str, dict[str, Any]] = {}

        for result in results:
            provider = result.provider

            if provider == "exa":
                # Exa → profile_intelligence
                enriched.profile_intelligence = {
                    "bio": result.bio,
                    "linkedin_url": result.linkedin_url,
                    "web_mentions": result.web_mentions,
                    "publications": result.publications,
                    "social_profiles": result.social_profiles,
                }
            else:
                # Apollo, ZoomInfo, etc. → contact_details
                enriched.contact_details = {
                    "email": result.email,
                    "phone": result.phone,
                    "location": result.location,
                }

            # Track field-level sources
            for field_name in ["bio", "linkedin_url", "email", "phone", "location", "title"]:
                value = getattr(result, field_name, "")
                if value and field_name not in field_sources:
                    field_sources[field_name] = {
                        "source": provider,
                        "confidence": result.confidence,
                        "value": value,
                    }

        enriched.field_sources = field_sources
        enriched.overall_confidence = (
            max((r.confidence for r in results), default=0.0) if results else 0.0
        )

        return enriched

    async def _get_cached_enrichment(
        self,
        name: str,
        company: str,
        user_id: str,
    ) -> EnrichedContact | None:
        """Check lead_memory_stakeholders for a cached enrichment.

        Args:
            name: Contact name.
            company: Company name.
            user_id: User UUID for RLS.

        Returns:
            EnrichedContact if cache hit and TTL valid, else None.
        """
        client = SupabaseClient.get_client()

        try:
            resp = (
                client.table("lead_memory_stakeholders")
                .select("*")
                .eq("user_id", user_id)
                .eq("name", name)
                .eq("company", company)
                .order("enriched_at", desc=True)
                .limit(1)
                .execute()
            )

            if not resp.data:
                return None

            row = resp.data[0]
            enriched_at_str = row.get("enriched_at")
            if not enriched_at_str:
                return None

            enriched_at = datetime.fromisoformat(enriched_at_str.replace("Z", "+00:00"))
            if datetime.now(UTC) - enriched_at > timedelta(days=CACHE_TTL_DAYS):
                return None

            # Reconstruct from cached data
            metadata = row.get("metadata") or {}
            return EnrichedContact(
                name=row.get("name", name),
                company=row.get("company", company),
                role=row.get("title", ""),
                profile_intelligence=metadata.get("profile_intelligence", {}),
                contact_details=metadata.get("contact_details", {}),
                field_sources=metadata.get("field_sources", {}),
                overall_confidence=row.get("confidence", 0.0),
                enriched_at=enriched_at,
                cached=True,
            )

        except Exception as exc:
            logger.warning("Cache lookup failed: %s", exc)
            return None

    async def _cache_enrichment(
        self,
        enriched: EnrichedContact,
        user_id: str,
    ) -> None:
        """Store enrichment result in lead_memory_stakeholders.

        Args:
            enriched: The enriched contact data.
            user_id: User UUID for RLS.
        """
        client = SupabaseClient.get_client()

        metadata = {
            "profile_intelligence": enriched.profile_intelligence,
            "contact_details": enriched.contact_details,
            "field_sources": enriched.field_sources,
        }

        record = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "name": enriched.name,
            "company": enriched.company,
            "title": enriched.role,
            "linkedin_url": enriched.profile_intelligence.get("linkedin_url", ""),
            "confidence": enriched.overall_confidence,
            "source": "contact_enricher",
            "enriched_at": enriched.enriched_at.isoformat(),
            "metadata": json.dumps(metadata),
        }

        try:
            # Upsert by name + company + user_id
            client.table("lead_memory_stakeholders").upsert(
                record,
                on_conflict="user_id,name,company",
            ).execute()
        except Exception as exc:
            logger.warning(
                "Failed to cache enrichment for %s at %s: %s",
                enriched.name,
                enriched.company,
                exc,
            )

    async def _store_stakeholder(
        self,
        *,
        user_id: str,
        name: str,
        company: str,
        title: str,
        department: str,
        linkedin_url: str,
        relationship: str,
        confidence: float,
        source: str,
    ) -> None:
        """Store an org chart entry in lead_memory_stakeholders.

        Args:
            user_id: User UUID.
            name: Person name.
            company: Company name.
            title: Job title.
            department: Department name.
            linkedin_url: LinkedIn URL.
            relationship: Relationship to other contacts.
            confidence: Confidence score.
            source: Data source identifier.
        """
        client = SupabaseClient.get_client()

        record = {
            "id": str(uuid.uuid4()),
            "user_id": user_id,
            "name": name,
            "company": company,
            "title": title,
            "department": department,
            "linkedin_url": linkedin_url,
            "relationship": relationship,
            "confidence": confidence,
            "source": source,
            "enriched_at": datetime.now(UTC).isoformat(),
            "metadata": json.dumps({}),
        }

        try:
            client.table("lead_memory_stakeholders").upsert(
                record,
                on_conflict="user_id,name,company",
            ).execute()
        except Exception as exc:
            logger.warning(
                "Failed to store stakeholder %s at %s: %s",
                name,
                company,
                exc,
            )

    async def _extract_people_from_company(
        self,
        company_name: str,
        company_enrichment: CompanyEnrichment,
    ) -> list[dict[str, Any]]:
        """Use LLM to extract people and roles from company enrichment data.

        Args:
            company_name: Company name.
            company_enrichment: Enrichment data from Exa.

        Returns:
            List of person dicts with name, title, department, confidence.
        """
        # Build context from enrichment data
        news_text = "\n".join(
            f"- {n.get('title', '')}: {n.get('snippet', '')[:200]}"
            for n in company_enrichment.recent_news[:10]
        )
        leadership_text = "\n".join(
            f"- {entry.get('text', '')[:300]}"
            for entry in company_enrichment.raw_data.get("leadership_mentions", [])[:5]
        )

        prompt = f"""Extract all named people and their roles at {company_name} from this data.

Company description: {company_enrichment.description[:500]}

Recent news:
{news_text or "No recent news available."}

Leadership mentions:
{leadership_text or "No leadership data available."}

Return a JSON array of objects:
[
  {{
    "name": "Full Name",
    "title": "Job Title",
    "department": "Department (inferred)",
    "relationship": "reports_to / peer_of / manages (if inferable)",
    "confidence": 0.0-1.0
  }}
]

Only include people with clear names. Return valid JSON array only."""

        try:
            response = await self._llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                system_prompt=(
                    "You are a data extraction assistant. Extract structured "
                    "people data from text. Return ONLY a valid JSON array."
                ),
                max_tokens=2048,
                temperature=0.2,
                task=TaskType.HUNTER_ENRICH,
                agent_id="contact_enricher",
            )

            # Parse response
            cleaned = response.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
            if cleaned.endswith("```"):
                cleaned = cleaned.rsplit("```", 1)[0]
            cleaned = cleaned.strip()

            people = json.loads(cleaned)
            if isinstance(people, list):
                return people
            return []

        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Failed to extract people from company data: %s", exc)
            return []

    def _store_market_signal(
        self,
        *,
        client: Any,
        user_id: str,
        signal: IntentSignal,
    ) -> None:
        """Insert an intent signal into market_signals.

        Args:
            client: Supabase client.
            user_id: User UUID.
            signal: IntentSignal to store.
        """
        try:
            client.table("market_signals").insert(
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "company_name": signal.company,
                    "signal_type": signal.signal_type,
                    "headline": f"{signal.signal_type}: {signal.contact_name}"[:500],
                    "summary": signal.description[:2000],
                    "source_url": signal.source_url,
                    "relevance_score": signal.relevance_score,
                    "detected_at": signal.detected_at.isoformat(),
                    "metadata": {
                        "contact_name": signal.contact_name,
                        "source": "contact_enricher",
                    },
                }
            ).execute()
        except Exception as exc:
            logger.warning(
                "Failed to store intent signal: %s",
                exc,
                extra={"contact": signal.contact_name},
            )

    # ── Fact extraction ───────────────────────────────────────────────

    def _extract_facts_from_contact(
        self,
        contact: EnrichedContact,
    ) -> list[dict[str, Any]]:
        """Extract semantic facts from enriched contact data."""
        user_id = self._user_context.user_id
        facts: list[dict[str, Any]] = []

        if contact.company:
            facts.append(
                {
                    "subject": contact.name,
                    "predicate": "works_at",
                    "object": contact.company,
                    "confidence": contact.overall_confidence,
                    "source": f"contact_enricher:{user_id}",
                }
            )

        if contact.role:
            facts.append(
                {
                    "subject": contact.name,
                    "predicate": "has_role",
                    "object": contact.role,
                    "confidence": contact.overall_confidence,
                    "source": f"contact_enricher:{user_id}",
                }
            )

        linkedin = contact.profile_intelligence.get("linkedin_url")
        if linkedin:
            facts.append(
                {
                    "subject": contact.name,
                    "predicate": "has_linkedin",
                    "object": linkedin,
                    "confidence": 0.95,
                    "source": f"contact_enricher:{user_id}",
                }
            )

        return facts

    @staticmethod
    def _extract_facts_from_org_chart(
        entries: list[OrgChartEntry],
        company_name: str,
    ) -> list[dict[str, Any]]:
        """Extract semantic facts from org chart data."""
        return [
            {
                "subject": entry.name,
                "predicate": "works_at",
                "object": company_name,
                "confidence": entry.confidence,
                "source": "contact_enricher:org_chart",
            }
            for entry in entries
        ]

    @staticmethod
    def _extract_facts_from_signals(
        signals: list[IntentSignal],
    ) -> list[dict[str, Any]]:
        """Extract semantic facts from intent signals."""
        return [
            {
                "subject": signal.contact_name,
                "predicate": f"intent_signal_{signal.signal_type}",
                "object": signal.description,
                "confidence": signal.relevance_score,
                "source": "contact_enricher:intent",
            }
            for signal in signals
        ]
