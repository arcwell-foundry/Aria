"""Enrichment provider interface and implementations.

Defines a pluggable provider interface for contact and company enrichment.
Exa API is the primary provider; Apollo is now available as a secondary
provider for B2B contact data with credit metering.
"""

from src.agents.capabilities.enrichment_providers.apollo_provider import (
    ApolloEnrichmentProvider,
)
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
    "ApolloEnrichmentProvider",
    "BaseEnrichmentProvider",
    "CompanyEnrichment",
    "ExaEnrichmentProvider",
    "PersonEnrichment",
    "PublicationResult",
]
