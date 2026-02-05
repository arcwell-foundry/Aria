"""Unit tests for skill trust levels system."""

import pytest

from src.security.trust_levels import (
    TRUST_DATA_ACCESS,
    TRUSTED_SKILL_SOURCES,
    SkillTrustLevel,
    can_access_data,
    determine_trust_level,
)
from src.security.data_classification import DataClass


class TestSkillTrustLevel:
    """Tests for SkillTrustLevel enum."""

    def test_trust_levels_exist(self) -> None:
        """All required trust levels should be defined."""
        assert SkillTrustLevel.CORE.value == "core"
        assert SkillTrustLevel.VERIFIED.value == "verified"
        assert SkillTrustLevel.COMMUNITY.value == "community"
        assert SkillTrustLevel.USER.value == "user"

    def test_trust_levels_are_ordered(self) -> None:
        """Trust levels should be comparable and ordered."""
        levels = [SkillTrustLevel.CORE, SkillTrustLevel.VERIFIED, SkillTrustLevel.COMMUNITY, SkillTrustLevel.USER]
        assert len(levels) == 4
        assert len(set(levels)) == 4  # All unique


class TestTrustDataAccess:
    """Tests for TRUST_DATA_ACCESS mapping."""

    def test_core_has_broadest_access(self) -> None:
        """CORE trust level should have access to most data classes."""
        core_access = TRUST_DATA_ACCESS[SkillTrustLevel.CORE]
        assert DataClass.PUBLIC in core_access
        assert DataClass.INTERNAL in core_access
        assert DataClass.CONFIDENTIAL in core_access
        assert DataClass.RESTRICTED in core_access
        # REGULATED should NOT be in automatic access (needs explicit approval)
        assert DataClass.REGULATED not in core_access

    def test_verified_limited_to_public_internal(self) -> None:
        """VERIFIED trust level should only access PUBLIC and INTERNAL."""
        verified_access = TRUST_DATA_ACCESS[SkillTrustLevel.VERIFIED]
        assert verified_access == [DataClass.PUBLIC, DataClass.INTERNAL]
        assert DataClass.CONFIDENTIAL not in verified_access
        assert DataClass.RESTRICTED not in verified_access
        assert DataClass.REGULATED not in verified_access

    def test_community_limited_to_public(self) -> None:
        """COMMUNITY trust level should only access PUBLIC."""
        community_access = TRUST_DATA_ACCESS[SkillTrustLevel.COMMUNITY]
        assert community_access == [DataClass.PUBLIC]
        assert DataClass.INTERNAL not in community_access
        assert DataClass.CONFIDENTIAL not in community_access

    def test_user_has_public_internal(self) -> None:
        """USER trust level should access PUBLIC and INTERNAL."""
        user_access = TRUST_DATA_ACCESS[SkillTrustLevel.USER]
        assert user_access == [DataClass.PUBLIC, DataClass.INTERNAL]
        assert DataClass.CONFIDENTIAL not in user_access


class TestTrustedSkillSources:
    """Tests for TRUSTED_SKILL_SOURCES list."""

    def test_required_sources_present(self) -> None:
        """All required trusted sources should be in the list."""
        required = [
            "anthropics/skills",
            "vercel-labs/agent-skills",
            "supabase/agent-skills",
            "expo/skills",
            "better-auth/skills",
        ]
        for source in required:
            assert source in TRUSTED_SKILL_SOURCES

    def test_sources_are_unique(self) -> None:
        """Trusted sources should be unique."""
        assert len(TRUSTED_SKILL_SOURCES) == len(set(TRUSTED_SKILL_SOURCES))


class TestDetermineTrustLevel:
    """Tests for determine_trust_level function."""

    @pytest.mark.parametrize(
        ("skill_path", "expected_level"),
        [
            # Anthropic skills
            ("anthropics/skills/pdf", SkillTrustLevel.VERIFIED),
            ("anthropics/skills/docx", SkillTrustLevel.VERIFIED),
            # Vercel skills
            ("vercel-labs/agent-skills/something", SkillTrustLevel.VERIFIED),
            ("vercel-labs/agent-skills", SkillTrustLevel.VERIFIED),
            # Supabase skills
            ("supabase/agent-skills/anything", SkillTrustLevel.VERIFIED),
            # Expo skills
            ("expo/skills/test", SkillTrustLevel.VERIFIED),
            # Better-auth skills
            ("better-auth/skills/auth-helper", SkillTrustLevel.VERIFIED),
        ],
    )
    def test_verified_sources(self, skill_path: str, expected_level: SkillTrustLevel) -> None:
        """Skills from trusted sources should get VERIFIED level."""
        assert determine_trust_level(skill_path) == expected_level

    @pytest.mark.parametrize(
        ("skill_path", "expected_level"),
        [
            # User skills with explicit prefix
            ("user:my-custom-skill", SkillTrustLevel.USER),
            ("user:data-processor", SkillTrustLevel.USER),
            ("user:advanced-analytics", SkillTrustLevel.USER),
        ],
    )
    def test_user_skills(self, skill_path: str, expected_level: SkillTrustLevel) -> None:
        """User-created skills should get USER level."""
        assert determine_trust_level(skill_path) == expected_level

    @pytest.mark.parametrize(
        ("skill_path", "expected_level"),
        [
            # CORE skills with aria: prefix
            ("aria:pdf-parser", SkillTrustLevel.CORE),
            ("aria:document-analyzer", SkillTrustLevel.CORE),
            ("aria:clinical-trials-extractor", SkillTrustLevel.CORE),
        ],
    )
    def test_core_skills(self, skill_path: str, expected_level: SkillTrustLevel) -> None:
        """Built-in ARIA skills should get CORE level."""
        assert determine_trust_level(skill_path) == expected_level

    @pytest.mark.parametrize(
        ("skill_path", "expected_level"),
        [
            # Community skills (no slash, not prefixed)
            ("community-skill", SkillTrustLevel.COMMUNITY),
            ("random-helper", SkillTrustLevel.COMMUNITY),
            ("unknown-source/tool", SkillTrustLevel.COMMUNITY),
            ("random-repo/skill", SkillTrustLevel.COMMUNITY),
        ],
    )
    def test_community_skills(self, skill_path: str, expected_level: SkillTrustLevel) -> None:
        """Unknown skills should default to COMMUNITY level."""
        assert determine_trust_level(skill_path) == expected_level


class TestCanAccessData:
    """Tests for can_access_data function."""

    def test_core_can_access_confidential(self) -> None:
        """CORE skills can access CONFIDENTIAL data."""
        assert can_access_data(SkillTrustLevel.CORE, DataClass.CONFIDENTIAL) is True

    def test_core_can_access_restricted(self) -> None:
        """CORE skills can access RESTRICTED data."""
        assert can_access_data(SkillTrustLevel.CORE, DataClass.RESTRICTED) is True

    def test_core_cannot_auto_access_regulated(self) -> None:
        """CORE skills cannot automatically access REGULATED data."""
        assert can_access_data(SkillTrustLevel.CORE, DataClass.REGULATED) is False

    def test_verified_can_access_internal(self) -> None:
        """VERIFIED skills can access INTERNAL data."""
        assert can_access_data(SkillTrustLevel.VERIFIED, DataClass.INTERNAL) is True

    def test_verified_cannot_access_confidential(self) -> None:
        """VERIFIED skills cannot access CONFIDENTIAL data."""
        assert can_access_data(SkillTrustLevel.VERIFIED, DataClass.CONFIDENTIAL) is False

    def test_verified_cannot_access_restricted(self) -> None:
        """VERIFIED skills cannot access RESTRICTED data."""
        assert can_access_data(SkillTrustLevel.VERIFIED, DataClass.RESTRICTED) is False

    def test_community_can_access_public(self) -> None:
        """COMMUNITY skills can access PUBLIC data."""
        assert can_access_data(SkillTrustLevel.COMMUNITY, DataClass.PUBLIC) is True

    def test_community_cannot_access_internal(self) -> None:
        """COMMUNITY skills cannot access INTERNAL data."""
        assert can_access_data(SkillTrustLevel.COMMUNITY, DataClass.INTERNAL) is False

    def test_user_can_access_internal(self) -> None:
        """USER skills can access INTERNAL data (their own)."""
        assert can_access_data(SkillTrustLevel.USER, DataClass.INTERNAL) is True

    def test_user_cannot_access_confidential(self) -> None:
        """USER skills cannot access CONFIDENTIAL data."""
        assert can_access_data(SkillTrustLevel.USER, DataClass.CONFIDENTIAL) is False
