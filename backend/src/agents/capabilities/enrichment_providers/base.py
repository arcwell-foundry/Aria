"""Base enrichment provider interface.

All enrichment data sources (Exa, Apollo, ZoomInfo, etc.) implement this
abstract class so the ContactEnricher capability can aggregate results
from multiple providers with source attribution and confidence scoring.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Result models
# ---------------------------------------------------------------------------


class PersonEnrichment(BaseModel):
    """Structured person enrichment data from a single provider."""

    provider: str = Field(..., description="Provider name (exa, apollo, etc.)")
    name: str = ""
    title: str = ""
    company: str = ""
    linkedin_url: str = ""
    bio: str = ""
    email: str = ""
    phone: str = ""
    location: str = ""
    profile_image_url: str = ""
    web_mentions: list[dict[str, Any]] = Field(default_factory=list)
    publications: list[dict[str, Any]] = Field(default_factory=list)
    social_profiles: dict[str, str] = Field(default_factory=dict)
    raw_data: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    enriched_at: datetime | None = None


class CompanyEnrichment(BaseModel):
    """Structured company enrichment data from a single provider."""

    provider: str = Field(..., description="Provider name (exa, apollo, etc.)")
    name: str = ""
    domain: str = ""
    description: str = ""
    industry: str = ""
    employee_count: int | None = None
    revenue_range: str = ""
    headquarters: str = ""
    founded_year: int | None = None
    funding_total: str = ""
    latest_funding_round: str = ""
    leadership: list[dict[str, str]] = Field(default_factory=list)
    recent_news: list[dict[str, Any]] = Field(default_factory=list)
    products: list[str] = Field(default_factory=list)
    competitors: list[str] = Field(default_factory=list)
    raw_data: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(0.0, ge=0.0, le=1.0)
    enriched_at: datetime | None = None


class PublicationResult(BaseModel):
    """A single publication or patent search result."""

    title: str = ""
    authors: list[str] = Field(default_factory=list)
    abstract: str = ""
    url: str = ""
    published_date: str = ""
    source: str = ""
    citation_count: int | None = None
    relevance_score: float = 0.0


# ---------------------------------------------------------------------------
# Abstract base class
# ---------------------------------------------------------------------------


class BaseEnrichmentProvider(ABC):
    """Abstract enrichment provider interface.

    Implementations must provide search methods for people, companies,
    and publications. Each method returns provider-specific structured
    data with confidence scores and source attribution.

    Providers are expected to handle their own rate limiting and
    API key management internally.
    """

    provider_name: str = ""
    """Identifier for this provider (e.g. ``"exa"``, ``"apollo"``)."""

    @abstractmethod
    async def search_person(
        self,
        name: str,
        company: str = "",
        role: str = "",
    ) -> PersonEnrichment:
        """Search for a person and return enrichment data.

        Args:
            name: Full name of the person.
            company: Company name for disambiguation.
            role: Role/title for disambiguation.

        Returns:
            PersonEnrichment with available data and confidence score.
        """

    @abstractmethod
    async def search_company(
        self,
        company_name: str,
    ) -> CompanyEnrichment:
        """Search for a company and return enrichment data.

        Args:
            company_name: Company name to search for.

        Returns:
            CompanyEnrichment with available data and confidence score.
        """

    @abstractmethod
    async def search_publications(
        self,
        person_name: str,
        therapeutic_area: str = "",
    ) -> list[PublicationResult]:
        """Search for publications by a person in a therapeutic area.

        Args:
            person_name: Author name to search for.
            therapeutic_area: Optional therapeutic area filter.

        Returns:
            List of PublicationResult objects.
        """

    @abstractmethod
    async def health_check(self) -> bool:
        """Verify the provider's API is reachable and authenticated.

        Returns:
            True if the provider is operational.
        """
