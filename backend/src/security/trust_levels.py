"""Skill trust levels for ARIA security.

Skills have different trust levels that determine what data they can access.
This is a critical component of ARIA's security architecture - treating all
external skills as untrusted until proven otherwise.
"""

from enum import Enum
from typing import Final

from src.security.data_classification import DataClass


class SkillTrustLevel(Enum):
    """Trust levels for skills - determines data access permissions.

    Ordered from most trusted (CORE) to least trusted (COMMUNITY).
    Each level has specific data access permissions and execution constraints.
    """

    CORE = "core"
    # Built by ARIA team, fully audited, part of the product
    # Can access: ALL data classes with user permission
    # Examples: ARIA's built-in document skills, analysis tools

    VERIFIED = "verified"
    # From trusted sources (Anthropic, Vercel, Supabase), security reviewed
    # Can access: PUBLIC, INTERNAL only
    # Examples: anthropics/skills/pdf, vercel-labs/agent-skills

    COMMUNITY = "community"
    # From skills.sh, no security review
    # Can access: PUBLIC only
    # Examples: Most skills.sh community skills

    USER = "user"
    # Created by this user/tenant
    # Can access: PUBLIC, INTERNAL (their own data only)
    # Examples: Custom skills created within ARIA


# What each trust level can access
TRUST_DATA_ACCESS: Final[dict[SkillTrustLevel, list[DataClass]]] = {
    SkillTrustLevel.CORE: [
        DataClass.PUBLIC,
        DataClass.INTERNAL,
        DataClass.CONFIDENTIAL,
        DataClass.RESTRICTED,
        # Note: REGULATED requires explicit per-execution approval
    ],
    SkillTrustLevel.VERIFIED: [
        DataClass.PUBLIC,
        DataClass.INTERNAL,
    ],
    SkillTrustLevel.COMMUNITY: [
        DataClass.PUBLIC,
    ],
    SkillTrustLevel.USER: [
        DataClass.PUBLIC,
        DataClass.INTERNAL,
    ],
}


# Trusted sources that get VERIFIED status automatically
TRUSTED_SKILL_SOURCES: Final[list[str]] = [
    "anthropics/skills",
    "vercel-labs/agent-skills",
    "supabase/agent-skills",
    "expo/skills",
    "better-auth/skills",
]


def determine_trust_level(skill_path: str) -> SkillTrustLevel:
    """Determine trust level for a skill based on its path.

    Skills from trusted sources get VERIFIED status automatically.
    Skills from skills.sh not in trusted list get COMMUNITY status.
    User-created skills (identified by prefix) get USER status.
    Built-in ARIA skills (no path prefix) get CORE status.

    Args:
        skill_path: The skill's path identifier (e.g., "anthropics/skills/pdf").

    Returns:
        The appropriate SkillTrustLevel for this skill.

    Examples:
        >>> determine_trust_level("anthropics/skills/pdf")
        <SkillTrustLevel.VERIFIED: 'verified'>
        >>> determine_trust_level("community-skill")
        <SkillTrustLevel.COMMUNITY: 'community'>
        >>> determine_trust_level("user:my-custom-skill")
        <SkillTrustLevel.USER: 'user'>
        >>> determine_trust_level("aria-pdf-parser")
        <SkillTrustLevel.CORE: 'core'>
    """
    # Check for user-created skills (explicit prefix)
    if skill_path.startswith("user:"):
        return SkillTrustLevel.USER

    # Check for trusted verified sources
    for trusted_source in TRUSTED_SKILL_SOURCES:
        if skill_path.startswith(trusted_source + "/") or skill_path == trusted_source:
            return SkillTrustLevel.VERIFIED

    # Check for CORE skills (built-in to ARIA)
    # These are identified by having an explicit "aria:" prefix
    # and not matching other patterns
    if (
        "/" not in skill_path
        and not skill_path.startswith("user:")
        and skill_path.startswith("aria:")
    ):
        return SkillTrustLevel.CORE

    # Default to COMMUNITY for all other skills
    return SkillTrustLevel.COMMUNITY


def can_access_data(trust_level: SkillTrustLevel, data_class: DataClass) -> bool:
    """Check if a trust level allows access to a data class.

    Args:
        trust_level: The skill's trust level.
        data_class: The classification of the data to access.

    Returns:
        True if the trust level allows access to this data class.

    Examples:
        >>> can_access_data(SkillTrustLevel.CORE, DataClass.CONFIDENTIAL)
        True
        >>> can_access_data(SkillTrustLevel.COMMUNITY, DataClass.INTERNAL)
        False
    """
    allowed_classes = TRUST_DATA_ACCESS.get(trust_level, [])
    return data_class in allowed_classes
