"""Data classification system for ARIA skill security.

Every piece of data in ARIA has a classification that determines
what skills can access it. Skills are treated as untrusted code
until proven otherwise.
"""

from enum import Enum


class DataClass(Enum):
    """Data classification levels - determines what skills can access.

    Ordered from least sensitive (PUBLIC) to most sensitive (REGULATED).
    """

    PUBLIC = "public"  # Can be shared freely (company names, public info)
    INTERNAL = "internal"  # Company internal (goals, strategies, notes)
    CONFIDENTIAL = "confidential"  # Need-to-know (deal details, contacts)
    RESTRICTED = "restricted"  # Financial, competitive (revenue, pricing, contracts)
    REGULATED = "regulated"  # PHI, PII - legal requirements (HIPAA, GDPR)


# Placeholder classes for the __init__.py imports
# These will be implemented in subsequent tasks
class ClassifiedData:
    """Placeholder for classified data container - to be implemented."""

    pass


class DataClassifier:
    """Placeholder for data classifier - to be implemented."""

    pass
