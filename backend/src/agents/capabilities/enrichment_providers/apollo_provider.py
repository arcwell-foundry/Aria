"""Apollo.io enrichment provider.

Uses Apollo API for B2B contact and company enrichment. Apollo provides
high-quality data for people search, email/phone reveal, and company
intelligence with a credit-based consumption model.

Credit costs (configurable via vendor_api_pricing table):
- people_search: FREE (0 credits)
- people_enrich_email: 1 credit
- people_enrich_phone: 8 credits (1 base + 7 for phone)
- org_enrich: 1 credit
- job_postings: FREE (0 credits)

This provider integrates with the ApolloClient for dual-mode support
(BYOK vs LuminOne-provided) and credit metering.
"""

import logging
from datetime import UTC, datetime
from typing import Any, Optional

import httpx

from src.agents.capabilities.enrichment_providers.base import (
    BaseEnrichmentProvider,
    CompanyEnrichment,
    PersonEnrichment,
    PublicationResult,
)
from src.core.config import settings
from src.integrations.apollo_client import ApolloClient

logger = logging.getLogger(__name__)

APOLLO_BASE_URL = "https://api.apollo.io/api/v1"


class ApolloEnrichmentProvider(BaseEnrichmentProvider):
    """Apollo.io enrichment provider for B2B contact and company data.

    Provides:
    - People search by company/title (FREE)
    - Person enrichment with email/phone reveal (costs credits)
    - Company enrichment (costs credits)
    - Job postings as hiring signals (FREE)

    Requires company_id and user_id context for credit metering.
    """

    provider_name: str = "apollo"

    def __init__(
        self,
        company_id: Optional[str] = None,
        user_id: Optional[str] = None,
        apollo_client: Optional[ApolloClient] = None,
    ) -> None:
        """Initialize Apollo provider.

        Args:
            company_id: Company UUID for credit metering.
            user_id: User UUID for audit logging.
            apollo_client: Pre-configured ApolloClient (optional).
        """
        self._company_id = company_id
        self._user_id = user_id
        self._client = apollo_client or ApolloClient()

        if not settings.apollo_configured:
            logger.warning(
                "ApolloEnrichmentProvider initialized WITHOUT API key - "
                "all operations will return empty results"
            )

    async def _get_api_key(self) -> tuple[Optional[str], str]:
        """Resolve API key for the configured company.

        Returns:
            Tuple of (api_key, mode) or (None, 'unconfigured').
        """
        if not self._company_id:
            # No company context - try master key directly
            if settings.APOLLO_API_KEY:
                return settings.APOLLO_API_KEY.get_secret_value(), "luminone_provided"
            return None, "unconfigured"

        # Try company-specific config first (BYOK or luminone_provided with limits)
        key, mode = await self._client.resolve_api_key(self._company_id)
        if key:
            return key, mode

        # Fallback to master key if company has no apollo_config row
        if mode == "unconfigured" and settings.APOLLO_API_KEY:
            return settings.APOLLO_API_KEY.get_secret_value(), "luminone_provided"

        return key, mode

    # ── People Search (FREE) ─────────────────────────────────────────────

    async def search_people(
        self,
        company_domain: str,
        person_titles: Optional[list[str]] = None,
        person_seniorities: Optional[list[str]] = None,
        per_page: int = 10,
    ) -> list[dict[str, Any]]:
        """Search for people at a company. FREE - no credits consumed.

        Args:
            company_domain: Company domain (e.g., 'repligen.com').
            person_titles: Job titles to filter (e.g., ['VP Sales', 'Director']).
            person_seniorities: Seniority levels (e.g., ['vp', 'director', 'c_suite']).
            per_page: Results per page (max 100).

        Returns:
            List of person dicts with name, title, linkedin_url, etc.
        """
        api_key, mode = await self._get_api_key()
        if not api_key:
            logger.warning(f"Apollo not available: {mode}")
            return []

        # Get credit cost (should be 0 for search)
        credits_per_call, _ = await self._client.get_pricing("people_search")

        try:
            async with httpx.AsyncClient() as http:
                response = await http.post(
                    f"{APOLLO_BASE_URL}/mixed_people/search",
                    headers={
                        "Api-Key": api_key,
                        "Content-Type": "application/json",
                    },
                    json={
                        "q_organization_domains_list": [company_domain],
                        "person_titles": person_titles
                        or ["VP Sales", "Director Business Development", "VP Business Development"],
                        "person_seniorities": person_seniorities
                        or ["vp", "director", "c_suite", "manager"],
                        "per_page": min(per_page, 100),
                    },
                    timeout=20.0,
                )

            if response.status_code != 200:
                logger.error(
                    f"Apollo people search failed: {response.status_code} - {response.text[:200]}"
                )
                if self._company_id and self._user_id:
                    await self._client.consume_credits(
                        self._company_id,
                        self._user_id,
                        "people_search",
                        0,
                        target_company=company_domain,
                        mode=mode,
                        status="error",
                    )
                return []

            data = response.json()
            people = data.get("people", [])

            # Log the search (0 credits)
            if self._company_id and self._user_id:
                await self._client.consume_credits(
                    self._company_id,
                    self._user_id,
                    "people_search",
                    0,
                    target_company=company_domain,
                    mode=mode,
                    status="success",
                )

            return [
                {
                    "name": f"{p.get('first_name', '')} {p.get('last_name', '')}".strip(),
                    "first_name": p.get("first_name", ""),
                    "last_name": p.get("last_name", ""),
                    "title": p.get("title", ""),
                    "linkedin_url": p.get("linkedin_url", ""),
                    "seniority": p.get("seniority", ""),
                    "city": p.get("city", ""),
                    "state": p.get("state", ""),
                    "country": p.get("country", ""),
                    "apollo_id": p.get("id", ""),
                    "organization": p.get("organization", {}).get("name", ""),
                    "email_status": p.get("email_status", ""),
                    "source": "apollo_search",
                }
                for p in people
                if p.get("first_name")
            ]

        except Exception as e:
            logger.error(f"Apollo people search error: {e}")
            return []

    # ── Person Enrichment (COSTS CREDITS) ─────────────────────────────────

    async def enrich_person(
        self,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        email: Optional[str] = None,
        domain: Optional[str] = None,
        organization_name: Optional[str] = None,
        linkedin_url: Optional[str] = None,
        reveal_emails: bool = True,
        reveal_phone: bool = False,
    ) -> Optional[dict[str, Any]]:
        """Enrich a person with verified email/phone. COSTS CREDITS.

        1 credit for email reveal, 8 credits for email + phone.
        Only call for approved/high-value leads.

        Args:
            first_name: Person's first name.
            last_name: Person's last name.
            email: Known email (for matching).
            domain: Company domain.
            organization_name: Company name.
            linkedin_url: LinkedIn profile URL.
            reveal_emails: Whether to reveal emails (costs 1 credit).
            reveal_phone: Whether to reveal phone (adds 7 credits).

        Returns:
            Enriched person dict or None if not found.
        """
        action = "people_enrich_phone" if reveal_phone else "people_enrich_email"
        credits_needed, cost_per_credit = await self._client.get_pricing(action)

        api_key, mode = await self._get_api_key()
        if not api_key:
            logger.warning(f"Apollo not available: {mode}")
            return None

        # Check credits for luminone_provided mode
        if mode == "luminone_provided" and self._company_id:
            has_credits = await self._client.check_credits(
                self._company_id, credits_needed
            )
            if not has_credits:
                logger.warning(f"Insufficient Apollo credits for company {self._company_id}")
                return {"error": "credit_limit_reached", "credits_needed": credits_needed}

        try:
            payload: dict[str, Any] = {}
            if email:
                payload["email"] = email
            if first_name:
                payload["first_name"] = first_name
            if last_name:
                payload["last_name"] = last_name
            if domain:
                payload["domain"] = domain
            if organization_name:
                payload["organization_name"] = organization_name
            if linkedin_url:
                payload["linkedin_url"] = linkedin_url

            # Reveal options
            payload["reveal_personal_emails"] = reveal_emails
            payload["reveal_phone_number"] = reveal_phone

            async with httpx.AsyncClient() as http:
                response = await http.post(
                    f"{APOLLO_BASE_URL}/people/match",
                    headers={
                        "Api-Key": api_key,
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=20.0,
                )

            if response.status_code == 404:
                # Person not found - log with 0 credits
                if self._company_id and self._user_id:
                    await self._client.consume_credits(
                        self._company_id,
                        self._user_id,
                        action,
                        0,
                        target_person=f"{first_name} {last_name}",
                        target_company=domain or organization_name,
                        mode=mode,
                        status="not_found",
                    )
                return None

            if response.status_code != 200:
                logger.error(f"Apollo person enrich failed: {response.status_code}")
                if self._company_id and self._user_id:
                    await self._client.consume_credits(
                        self._company_id,
                        self._user_id,
                        action,
                        0,
                        target_person=f"{first_name} {last_name}",
                        mode=mode,
                        status="error",
                    )
                return None

            data = response.json()
            person = data.get("person")

            if not person:
                if self._company_id and self._user_id:
                    await self._client.consume_credits(
                        self._company_id,
                        self._user_id,
                        action,
                        0,
                        target_person=f"{first_name} {last_name}",
                        mode=mode,
                        status="not_found",
                    )
                return None

            # Consume credits on success
            if self._company_id and self._user_id:
                await self._client.consume_credits(
                    self._company_id,
                    self._user_id,
                    action,
                    credits_needed,
                    target_company=domain or organization_name,
                    target_person=f"{person.get('first_name', '')} {person.get('last_name', '')}",
                    mode=mode,
                    status="success",
                )

            # Extract phone number
            phone_numbers = person.get("phone_numbers", [])
            phone = phone_numbers[0].get("sanitized_number") if phone_numbers else None

            return {
                "name": f"{person.get('first_name', '')} {person.get('last_name', '')}".strip(),
                "first_name": person.get("first_name", ""),
                "last_name": person.get("last_name", ""),
                "title": person.get("title", ""),
                "email": person.get("email", ""),
                "phone": phone,
                "linkedin_url": person.get("linkedin_url", ""),
                "city": person.get("city", ""),
                "state": person.get("state", ""),
                "country": person.get("country", ""),
                "seniority": person.get("seniority", ""),
                "company": person.get("organization", {}).get("name", ""),
                "company_domain": person.get("organization", {}).get("primary_domain", ""),
                "apollo_id": person.get("id", ""),
                "source": "apollo_enrich",
            }

        except Exception as e:
            logger.error(f"Apollo person enrich error: {e}")
            return None

    # ── BaseEnrichmentProvider Interface ─────────────────────────────────

    async def search_person(
        self,
        name: str,
        company: str = "",
        role: str = "",
    ) -> PersonEnrichment:
        """Search for a person by name with optional company/role context.

        This is the BaseEnrichmentProvider interface method. It tries to
        find the person via Apollo match endpoint.

        Args:
            name: Full name of the person.
            company: Company name for disambiguation.
            role: Role/title for disambiguation.

        Returns:
            PersonEnrichment with available data.
        """
        # Parse name into first/last
        parts = name.strip().split()
        first_name = parts[0] if parts else ""
        last_name = " ".join(parts[1:]) if len(parts) > 1 else ""

        result = await self.enrich_person(
            first_name=first_name,
            last_name=last_name,
            organization_name=company,
            reveal_emails=False,  # Don't spend credits for basic search
        )

        if not result or result.get("error"):
            return PersonEnrichment(
                provider=self.provider_name,
                name=name,
                company=company,
                title=role,
                confidence=0.0,
            )

        return PersonEnrichment(
            provider=self.provider_name,
            name=result.get("name", name),
            title=result.get("title", ""),
            company=result.get("company", company),
            email=result.get("email", ""),
            phone=result.get("phone", ""),
            linkedin_url=result.get("linkedin_url", ""),
            location=f"{result.get('city', '')}, {result.get('state', '')}".strip(", "),
            raw_data=result,
            confidence=0.8 if result.get("email") else 0.5,
            enriched_at=datetime.now(UTC),
        )

    async def search_company(
        self,
        company_name: str,
    ) -> CompanyEnrichment:
        """Search for a company and return enrichment data. COSTS CREDITS.

        Args:
            company_name: Company name to search for.

        Returns:
            CompanyEnrichment with available data.
        """
        action = "org_enrich"
        credits_needed, _ = await self._client.get_pricing(action)

        api_key, mode = await self._get_api_key()
        if not api_key:
            return CompanyEnrichment(
                provider=self.provider_name,
                name=company_name,
                confidence=0.0,
            )

        # Check credits
        if mode == "luminone_provided" and self._company_id:
            has_credits = await self._client.check_credits(
                self._company_id, credits_needed
            )
            if not has_credits:
                return CompanyEnrichment(
                    provider=self.provider_name,
                    name=company_name,
                    confidence=0.0,
                    raw_data={"error": "credit_limit_reached"},
                )

        try:
            async with httpx.AsyncClient() as http:
                response = await http.post(
                    f"{APOLLO_BASE_URL}/organizations/enrich",
                    headers={
                        "Api-Key": api_key,
                        "Content-Type": "application/json",
                    },
                    json={"name": company_name},
                    timeout=20.0,
                )

            if response.status_code != 200:
                return CompanyEnrichment(
                    provider=self.provider_name,
                    name=company_name,
                    confidence=0.0,
                )

            data = response.json()
            org = data.get("organization")

            if not org:
                return CompanyEnrichment(
                    provider=self.provider_name,
                    name=company_name,
                    confidence=0.0,
                )

            # Consume credits
            if self._company_id and self._user_id:
                await self._client.consume_credits(
                    self._company_id,
                    self._user_id,
                    action,
                    credits_needed,
                    target_company=org.get("primary_domain", company_name),
                    mode=mode,
                    status="success",
                )

            return CompanyEnrichment(
                provider=self.provider_name,
                name=org.get("name", company_name),
                domain=org.get("primary_domain", ""),
                description=org.get("short_description", ""),
                industry=org.get("industry", ""),
                employee_count=org.get("estimated_num_employees"),
                revenue_range=org.get("revenue_range", ""),
                headquarters=f"{org.get('city', '')}, {org.get('state', '')}".strip(", "),
                founded_year=org.get("founded_year"),
                funding_total=str(org.get("total_funding", "")),
                latest_funding_round=org.get("latest_funding_round_type", ""),
                raw_data=org,
                confidence=0.85,
                enriched_at=datetime.now(UTC),
            )

        except Exception as e:
            logger.error(f"Apollo company enrich error: {e}")
            return CompanyEnrichment(
                provider=self.provider_name,
                name=company_name,
                confidence=0.0,
            )

    async def search_publications(
        self,
        person_name: str,
        therapeutic_area: str = "",
    ) -> list[PublicationResult]:
        """Search for publications by a person.

        Apollo does not support publication search. Returns empty list.

        Args:
            person_name: Author name to search for.
            therapeutic_area: Optional therapeutic area filter.

        Returns:
            Empty list (not supported by Apollo).
        """
        # Apollo doesn't have publication data
        return []

    async def get_job_postings(
        self,
        organization_id: str,
        domain: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        """Get job postings for a company. FREE - no credits consumed.

        Useful for hiring signals - companies hiring for specific roles
        often indicate buying intent.

        Args:
            organization_id: Apollo organization ID.
            domain: Company domain (optional).

        Returns:
            List of job posting dicts.
        """
        api_key, mode = await self._get_api_key()
        if not api_key:
            return []

        try:
            params = {"per_page": 25}
            if domain:
                params["domain"] = domain

            async with httpx.AsyncClient() as http:
                response = await http.get(
                    f"{APOLLO_BASE_URL}/organizations/{organization_id}/job_postings",
                    headers={"Api-Key": api_key},
                    params=params,
                    timeout=20.0,
                )

            if response.status_code != 200:
                logger.warning(f"Apollo job postings failed: {response.status_code}")
                return []

            data = response.json()
            postings = data.get("job_postings", [])

            # Log (0 credits)
            if self._company_id and self._user_id:
                await self._client.consume_credits(
                    self._company_id,
                    self._user_id,
                    "job_postings",
                    0,
                    target_company=domain,
                    mode=mode,
                    status="success",
                )

            return [
                {
                    "title": p.get("title", ""),
                    "location": p.get("location", ""),
                    "url": p.get("url", ""),
                    "posted_at": p.get("posted_at", ""),
                    "department": p.get("department", ""),
                }
                for p in postings
            ]

        except Exception as e:
            logger.error(f"Apollo job postings error: {e}")
            return []

    async def health_check(self) -> bool:
        """Verify Apollo API is reachable and authenticated.

        Returns:
            True if operational, False otherwise.
        """
        api_key, mode = await self._get_api_key()
        if not api_key:
            return False

        try:
            async with httpx.AsyncClient() as http:
                response = await http.get(
                    f"{APOLLO_BASE_URL}/users/api_usage",
                    headers={"Api-Key": api_key},
                    timeout=10.0,
                )
                return response.status_code == 200
        except Exception as e:
            logger.error(f"Apollo health check failed: {e}")
            return False
