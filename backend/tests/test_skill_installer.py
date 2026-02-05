"""Tests for skill installer service and InstalledSkill dataclass."""

from unittest.mock import MagicMock, patch
from datetime import datetime, timezone, timedelta

import pytest

from src.security.trust_levels import SkillTrustLevel
from src.skills.installer import InstalledSkill, SkillInstaller


class TestInstalledSkillDataclass:
    """Tests for InstalledSkill dataclass."""

    def test_create_minimal_installed_skill(self) -> None:
        """Test creating an InstalledSkill with all required fields."""
        now = datetime.now(timezone.utc)
        skill = InstalledSkill(
            id="123",
            user_id="user-abc",
            tenant_id="tenant-xyz",
            skill_id="skill-456",
            skill_path="anthropics/skills/pdf",
            trust_level=SkillTrustLevel.VERIFIED,
            permissions_granted=[],
            installed_at=now,
            auto_installed=False,
            last_used_at=None,
            execution_count=0,
            success_count=0,
            created_at=now,
            updated_at=now,
        )
        assert skill.id == "123"
        assert skill.user_id == "user-abc"
        assert skill.tenant_id == "tenant-xyz"
        assert skill.skill_path == "anthropics/skills/pdf"
        assert skill.trust_level == SkillTrustLevel.VERIFIED
        assert skill.execution_count == 0
        assert skill.last_used_at is None

    def test_create_installed_skill_with_all_fields(self) -> None:
        """Test creating an InstalledSkill with all fields populated."""
        now = datetime.now(timezone.utc)
        used_at = now - timedelta(hours=1)
        skill = InstalledSkill(
            id="123",
            user_id="user-abc",
            tenant_id="tenant-xyz",
            skill_id="skill-456",
            skill_path="aria:clinical-trials-analyzer",
            trust_level=SkillTrustLevel.CORE,
            permissions_granted=["network_read"],
            installed_at=now - timedelta(days=30),
            auto_installed=True,
            last_used_at=used_at,
            execution_count=150,
            success_count=142,
            created_at=now - timedelta(days=30),
            updated_at=used_at,
        )
        assert skill.trust_level == SkillTrustLevel.CORE
        assert skill.permissions_granted == ["network_read"]
        assert skill.auto_installed is True
        assert skill.execution_count == 150
        assert skill.success_count == 142
        assert skill.last_used_at == used_at

    def test_installed_skill_is_frozen(self) -> None:
        """Test InstalledSkill is frozen (immutable)."""
        now = datetime.now(timezone.utc)
        skill = InstalledSkill(
            id="123",
            user_id="user-abc",
            tenant_id="tenant-xyz",
            skill_id="skill-456",
            skill_path="test/skill",
            trust_level=SkillTrustLevel.COMMUNITY,
            permissions_granted=[],
            installed_at=now,
            auto_installed=False,
            last_used_at=None,
            execution_count=0,
            success_count=0,
            created_at=now,
            updated_at=now,
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            skill.execution_count = 10

    def test_trust_level_enum_accepts_all_levels(self) -> None:
        """Test trust_level accepts all SkillTrustLevel enum values."""
        now = datetime.now(timezone.utc)
        for level in SkillTrustLevel:
            skill = InstalledSkill(
                id="123",
                user_id="user-abc",
                tenant_id="tenant-xyz",
                skill_id="skill-456",
                skill_path="test/skill",
                trust_level=level,
                permissions_granted=[],
                installed_at=now,
                auto_installed=False,
                last_used_at=None,
                execution_count=0,
                success_count=0,
                created_at=now,
                updated_at=now,
            )
            assert skill.trust_level == level

    def test_tenant_id_can_be_none(self) -> None:
        """Test tenant_id can be None for single-tenant installations."""
        now = datetime.now(timezone.utc)
        skill = InstalledSkill(
            id="123",
            user_id="user-abc",
            tenant_id=None,
            skill_id="skill-456",
            skill_path="test/skill",
            trust_level=SkillTrustLevel.USER,
            permissions_granted=[],
            installed_at=now,
            auto_installed=False,
            last_used_at=None,
            execution_count=0,
            success_count=0,
            created_at=now,
            updated_at=now,
        )
        assert skill.tenant_id is None

    def test_last_used_at_can_be_none(self) -> None:
        """Test last_used_at can be None for never-used skills."""
        now = datetime.now(timezone.utc)
        skill = InstalledSkill(
            id="123",
            user_id="user-abc",
            tenant_id="tenant-xyz",
            skill_id="skill-456",
            skill_path="test/skill",
            trust_level=SkillTrustLevel.COMMUNITY,
            permissions_granted=[],
            installed_at=now,
            auto_installed=False,
            last_used_at=None,
            execution_count=0,
            success_count=0,
            created_at=now,
            updated_at=now,
        )
        assert skill.last_used_at is None
        assert skill.execution_count == 0

    def test_permissions_granted_can_be_empty_list(self) -> None:
        """Test permissions_granted can be an empty list."""
        now = datetime.now(timezone.utc)
        skill = InstalledSkill(
            id="123",
            user_id="user-abc",
            tenant_id="tenant-xyz",
            skill_id="skill-456",
            skill_path="test/skill",
            trust_level=SkillTrustLevel.COMMUNITY,
            permissions_granted=[],
            installed_at=now,
            auto_installed=False,
            last_used_at=None,
            execution_count=0,
            success_count=0,
            created_at=now,
            updated_at=now,
        )
        assert skill.permissions_granted == []

    def test_success_rate_calculation(self) -> None:
        """Test success rate can be calculated from execution_count and success_count."""
        now = datetime.now(timezone.utc)
        skill = InstalledSkill(
            id="123",
            user_id="user-abc",
            tenant_id="tenant-xyz",
            skill_id="skill-456",
            skill_path="test/skill",
            trust_level=SkillTrustLevel.VERIFIED,
            permissions_granted=[],
            installed_at=now,
            auto_installed=False,
            last_used_at=now,
            execution_count=100,
            success_count=95,
            created_at=now,
            updated_at=now,
        )
        success_rate = skill.success_count / skill.execution_count if skill.execution_count > 0 else 0
        assert success_rate == 0.95

    def test_success_rate_for_zero_executions(self) -> None:
        """Test success rate is 0 when execution_count is 0."""
        now = datetime.now(timezone.utc)
        skill = InstalledSkill(
            id="123",
            user_id="user-abc",
            tenant_id="tenant-xyz",
            skill_id="skill-456",
            skill_path="test/skill",
            trust_level=SkillTrustLevel.COMMUNITY,
            permissions_granted=[],
            installed_at=now,
            auto_installed=False,
            last_used_at=None,
            execution_count=0,
            success_count=0,
            created_at=now,
            updated_at=now,
        )
        success_rate = skill.success_count / skill.execution_count if skill.execution_count > 0 else 0
        assert success_rate == 0


class TestSkillInstallerDbConversion:
    """Tests for SkillInstaller database conversion methods."""

    @patch("src.skills.installer.SupabaseClient.get_client")
    def test_db_row_to_installed_skill_converts_valid_row(self, mock_get_client: MagicMock) -> None:
        """Test _db_row_to_installed_skill converts database row to InstalledSkill."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        now = datetime.now(timezone.utc)
        db_row = {
            "id": "123",
            "user_id": "user-abc",
            "tenant_id": "tenant-xyz",
            "skill_id": "skill-456",
            "skill_path": "anthropics/skills/pdf",
            "trust_level": "verified",
            "permissions_granted": ["network_read"],
            "installed_at": now.isoformat(),
            "auto_installed": True,
            "last_used_at": now.isoformat(),
            "execution_count": 50,
            "success_count": 48,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        skill = installer._db_row_to_installed_skill(db_row)

        assert skill.id == "123"
        assert skill.user_id == "user-abc"
        assert skill.tenant_id == "tenant-xyz"
        assert skill.skill_path == "anthropics/skills/pdf"
        assert skill.trust_level == SkillTrustLevel.VERIFIED
        assert skill.permissions_granted == ["network_read"]
        assert skill.auto_installed is True
        assert skill.execution_count == 50
        assert skill.success_count == 48

    @patch("src.skills.installer.SupabaseClient.get_client")
    def test_db_row_to_installed_skill_handles_missing_tenant_id(self, mock_get_client: MagicMock) -> None:
        """Test _db_row_to_installed_skill handles missing tenant_id."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        now = datetime.now(timezone.utc)
        db_row = {
            "id": "123",
            "user_id": "user-abc",
            "skill_id": "skill-456",
            "skill_path": "test/skill",
            "trust_level": "community",
            "permissions_granted": [],
            "installed_at": now.isoformat(),
            "auto_installed": False,
            "last_used_at": None,
            "execution_count": 0,
            "success_count": 0,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        skill = installer._db_row_to_installed_skill(db_row)

        assert skill.tenant_id is None

    @patch("src.skills.installer.SupabaseClient.get_client")
    def test_db_row_to_installed_skill_handles_none_last_used_at(self, mock_get_client: MagicMock) -> None:
        """Test _db_row_to_installed_skill handles None last_used_at."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        now = datetime.now(timezone.utc)
        db_row = {
            "id": "123",
            "user_id": "user-abc",
            "tenant_id": "tenant-xyz",
            "skill_id": "skill-456",
            "skill_path": "test/skill",
            "trust_level": "community",
            "permissions_granted": [],
            "installed_at": now.isoformat(),
            "auto_installed": False,
            "last_used_at": None,
            "execution_count": 0,
            "success_count": 0,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        skill = installer._db_row_to_installed_skill(db_row)

        assert skill.last_used_at is None

    @patch("src.skills.installer.SupabaseClient.get_client")
    def test_db_row_to_installed_skill_handles_missing_permissions(self, mock_get_client: MagicMock) -> None:
        """Test _db_row_to_installed_skill handles missing permissions_granted."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        now = datetime.now(timezone.utc)
        db_row = {
            "id": "123",
            "user_id": "user-abc",
            "tenant_id": "tenant-xyz",
            "skill_id": "skill-456",
            "skill_path": "test/skill",
            "trust_level": "community",
            "installed_at": now.isoformat(),
            "auto_installed": False,
            "last_used_at": None,
            "execution_count": 0,
            "success_count": 0,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        skill = installer._db_row_to_installed_skill(db_row)

        assert skill.permissions_granted == []

    @patch("src.skills.installer.SupabaseClient.get_client")
    def test_db_row_to_installed_skill_handles_unknown_trust_level(self, mock_get_client: MagicMock) -> None:
        """Test _db_row_to_installed_skill defaults to COMMUNITY for unknown trust levels."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        now = datetime.now(timezone.utc)
        db_row = {
            "id": "123",
            "user_id": "user-abc",
            "tenant_id": "tenant-xyz",
            "skill_id": "skill-456",
            "skill_path": "test/skill",
            "trust_level": "unknown_level",
            "permissions_granted": [],
            "installed_at": now.isoformat(),
            "auto_installed": False,
            "last_used_at": None,
            "execution_count": 0,
            "success_count": 0,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        skill = installer._db_row_to_installed_skill(db_row)

        assert skill.trust_level == SkillTrustLevel.COMMUNITY

    @patch("src.skills.installer.SupabaseClient.get_client")
    def test_db_row_to_installed_skill_handles_datetime_parsing(self, mock_get_client: MagicMock) -> None:
        """Test _db_row_to_installed_skill parses ISO format datetime strings."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        db_row = {
            "id": "123",
            "user_id": "user-abc",
            "tenant_id": "tenant-xyz",
            "skill_id": "skill-456",
            "skill_path": "test/skill",
            "trust_level": "core",
            "permissions_granted": [],
            "installed_at": "2024-01-15T10:30:00+00:00",
            "auto_installed": False,
            "last_used_at": "2024-01-20T14:45:00+00:00",
            "execution_count": 10,
            "success_count": 9,
            "created_at": "2024-01-15T10:30:00+00:00",
            "updated_at": "2024-01-20T14:45:00+00:00",
        }

        skill = installer._db_row_to_installed_skill(db_row)

        assert isinstance(skill.installed_at, datetime)
        assert isinstance(skill.last_used_at, datetime)
        assert isinstance(skill.created_at, datetime)
        assert isinstance(skill.updated_at, datetime)

    @patch("src.skills.installer.SupabaseClient.get_client")
    def test_db_row_to_installed_skill_handles_missing_auto_installed(self, mock_get_client: MagicMock) -> None:
        """Test _db_row_to_installed_skill defaults auto_installed to False."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        now = datetime.now(timezone.utc)
        db_row = {
            "id": "123",
            "user_id": "user-abc",
            "tenant_id": "tenant-xyz",
            "skill_id": "skill-456",
            "skill_path": "test/skill",
            "trust_level": "community",
            "permissions_granted": [],
            "installed_at": now.isoformat(),
            "last_used_at": None,
            "execution_count": 0,
            "success_count": 0,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        skill = installer._db_row_to_installed_skill(db_row)

        assert skill.auto_installed is False

    @patch("src.skills.installer.SupabaseClient.get_client")
    def test_db_row_to_installed_skill_handles_missing_execution_counts(self, mock_get_client: MagicMock) -> None:
        """Test _db_row_to_installed_skill defaults execution counts to 0."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        now = datetime.now(timezone.utc)
        db_row = {
            "id": "123",
            "user_id": "user-abc",
            "tenant_id": "tenant-xyz",
            "skill_id": "skill-456",
            "skill_path": "test/skill",
            "trust_level": "community",
            "permissions_granted": [],
            "installed_at": now.isoformat(),
            "auto_installed": False,
            "last_used_at": None,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        skill = installer._db_row_to_installed_skill(db_row)

        assert skill.execution_count == 0
        assert skill.success_count == 0


class TestSkillInstallerInit:
    """Tests for SkillInstaller initialization."""

    @patch("src.skills.installer.SupabaseClient.get_client")
    def test_init_creates_supabase_client(self, mock_get_client: MagicMock) -> None:
        """Test SkillInstaller initializes with Supabase client."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client

        installer = SkillInstaller()

        assert installer._client is not None
        mock_get_client.assert_called_once()
