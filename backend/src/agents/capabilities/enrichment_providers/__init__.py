"""Enrichment provider interface and implementations.

Defines a pluggable provider interface for contact and company enrichment.
Exa API is the primary provider; Apollo/ZoomInfo can be added as secondary
providers by implementing BaseEnrichmentProvider.
"""

from src.agents.capabilities.enrichment_providers.base import (
    BaseEnrichmentProvider,
    CompanyEnrichment,
    PersonEnrichment,
    PublicationResult,
)
from src.agents.capabilities.enrichment_providers.exa_provider import (
    ExaEnrichmentProvider,
)

__all__ = [
    "BaseEnrichmentProvider",
    "CompanyEnrichment",
    "ExaEnrichmentProvider",
    "PersonEnrichment",
    "PublicationResult",
]
