"""Tests for skill installer service and InstalledSkill dataclass."""

from unittest.mock import MagicMock, AsyncMock, patch
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


class TestSkillInstallerUninstall:
    """Tests for SkillInstaller.uninstall method."""

    @patch("src.skills.installer.SupabaseClient.get_client")
    async def test_uninstall_removes_skill(self, mock_get_client: MagicMock) -> None:
        """Test uninstall removes a skill installation."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        # Mock delete response
        mock_delete_response = MagicMock()
        mock_delete_response.count = 1
        mock_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = (
            mock_delete_response
        )

        result = await installer.uninstall("user-abc", "skill-id-123")

        assert result is True
        mock_client.table.assert_called_once_with("user_skills")
        mock_client.table.return_value.delete.assert_called_once()

    @patch("src.skills.installer.SupabaseClient.get_client")
    async def test_uninstall_nonexistent_skill_returns_false(self, mock_get_client: MagicMock) -> None:
        """Test uninstall returns False when skill not installed."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        # Mock delete response (no rows deleted)
        mock_delete_response = MagicMock()
        mock_delete_response.count = 0
        mock_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = (
            mock_delete_response
        )

        result = await installer.uninstall("user-abc", "nonexistent-skill")

        assert result is False

    @patch("src.skills.installer.SupabaseClient.get_client")
    async def test_uninstall_handles_database_error(self, mock_get_client: MagicMock) -> None:
        """Test uninstall returns False on database error."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        # Mock database error
        mock_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.side_effect = (
            Exception("Database connection error")
        )

        result = await installer.uninstall("user-abc", "skill-id-123")

        assert result is False

    @patch("src.skills.installer.SupabaseClient.get_client")
    async def test_uninstall_response_without_count_attribute(self, mock_get_client: MagicMock) -> None:
        """Test uninstall handles response without count attribute."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        # Mock delete response without count attribute
        mock_delete_response = MagicMock(spec=[])
        mock_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = (
            mock_delete_response
        )

        result = await installer.uninstall("user-abc", "skill-id-123")

        assert result is False


class TestSkillInstallerGetInstalled:
    """Tests for SkillInstaller.get_installed method."""

    @patch("src.skills.installer.SupabaseClient.get_client")
    async def test_get_installed_returns_installed_skill(self, mock_get_client: MagicMock) -> None:
        """Test get_installed returns an installed skill."""
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
            "permissions_granted": [],
            "installed_at": now.isoformat(),
            "auto_installed": False,
            "last_used_at": None,
            "execution_count": 0,
            "success_count": 0,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            db_row
        )

        result = await installer.get_installed("user-abc", "skill-456")

        assert result is not None
        assert result.id == "123"
        assert result.user_id == "user-abc"
        assert result.skill_id == "skill-456"
        assert result.skill_path == "anthropics/skills/pdf"

    @patch("src.skills.installer.SupabaseClient.get_client")
    async def test_get_installed_returns_none_for_nonexistent_skill(self, mock_get_client: MagicMock) -> None:
        """Test get_installed returns None when skill not installed."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        # Mock empty response
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            None
        )

        result = await installer.get_installed("user-abc", "nonexistent-skill")

        assert result is None

    @patch("src.skills.installer.SupabaseClient.get_client")
    async def test_get_installed_uses_helper_method(self, mock_get_client: MagicMock) -> None:
        """Test get_installed uses _get_by_user_and_skill_id helper."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        now = datetime.now(timezone.utc)
        db_row = {
            "id": "123",
            "user_id": "user-abc",
            "tenant_id": None,
            "skill_id": "skill-789",
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

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            db_row
        )

        result = await installer.get_installed("user-abc", "skill-789")

        assert result is not None
        assert result.skill_id == "skill-789"
        assert result.trust_level == SkillTrustLevel.COMMUNITY


class TestSkillInstallerIsInstalled:
    """Tests for SkillInstaller.is_installed method."""

    @patch("src.skills.installer.SupabaseClient.get_client")
    async def test_is_installed_returns_true_for_installed_skill(self, mock_get_client: MagicMock) -> None:
        """Test is_installed returns True when skill is installed."""
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
            "permissions_granted": [],
            "installed_at": now.isoformat(),
            "auto_installed": False,
            "last_used_at": None,
            "execution_count": 0,
            "success_count": 0,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            db_row
        )

        result = await installer.is_installed("user-abc", "skill-456")

        assert result is True

    @patch("src.skills.installer.SupabaseClient.get_client")
    async def test_is_installed_returns_false_for_nonexistent_skill(self, mock_get_client: MagicMock) -> None:
        """Test is_installed returns False when skill not installed."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        # Mock empty response
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            None
        )

        result = await installer.is_installed("user-abc", "nonexistent-skill")

        assert result is False

    @patch("src.skills.installer.SupabaseClient.get_client")
    async def test_is_installed_handles_database_error(self, mock_get_client: MagicMock) -> None:
        """Test is_installed returns False on database error."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        # Mock database error
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.side_effect = (
            Exception("Database connection error")
        )

        result = await installer.is_installed("user-abc", "skill-456")

        assert result is False


class TestSkillInstallerRecordUsage:
    """Tests for SkillInstaller.record_usage method."""

    @patch("src.skills.installer.SupabaseClient.get_client")
    async def test_record_usage_increments_execution_count(self, mock_get_client: MagicMock) -> None:
        """Test record_usage increments execution_count."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        now = datetime.now(timezone.utc)
        existing_row = {
            "id": "123",
            "user_id": "user-abc",
            "tenant_id": "tenant-xyz",
            "skill_id": "skill-456",
            "skill_path": "anthropics/skills/pdf",
            "trust_level": "verified",
            "permissions_granted": [],
            "installed_at": now.isoformat(),
            "auto_installed": False,
            "last_used_at": None,
            "execution_count": 10,
            "success_count": 9,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        # Mock select to return existing skill
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            existing_row
        )

        # Mock update response
        updated_row = existing_row.copy()
        updated_row["execution_count"] = 11
        updated_row["success_count"] = 10
        updated_row["last_used_at"] = now.isoformat()
        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
            [updated_row]
        )

        result = await installer.record_usage("user-abc", "skill-456", success=True)

        assert result is not None
        assert result.execution_count == 11
        assert result.success_count == 10
        assert result.last_used_at is not None

    @patch("src.skills.installer.SupabaseClient.get_client")
    async def test_record_usage_increments_success_count_on_success(self, mock_get_client: MagicMock) -> None:
        """Test record_usage increments success_count when success=True."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        now = datetime.now(timezone.utc)
        existing_row = {
            "id": "123",
            "user_id": "user-abc",
            "tenant_id": "tenant-xyz",
            "skill_id": "skill-456",
            "skill_path": "anthropics/skills/pdf",
            "trust_level": "verified",
            "permissions_granted": [],
            "installed_at": now.isoformat(),
            "auto_installed": False,
            "last_used_at": None,
            "execution_count": 5,
            "success_count": 4,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            existing_row
        )

        updated_row = existing_row.copy()
        updated_row["execution_count"] = 6
        updated_row["success_count"] = 5
        updated_row["last_used_at"] = now.isoformat()
        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
            [updated_row]
        )

        result = await installer.record_usage("user-abc", "skill-456", success=True)

        assert result is not None
        assert result.success_count == 5

    @patch("src.skills.installer.SupabaseClient.get_client")
    async def test_record_usage_does_not_increment_success_count_on_failure(
        self, mock_get_client: MagicMock
    ) -> None:
        """Test record_usage does not increment success_count when success=False."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        now = datetime.now(timezone.utc)
        existing_row = {
            "id": "123",
            "user_id": "user-abc",
            "tenant_id": "tenant-xyz",
            "skill_id": "skill-456",
            "skill_path": "anthropics/skills/pdf",
            "trust_level": "verified",
            "permissions_granted": [],
            "installed_at": now.isoformat(),
            "auto_installed": False,
            "last_used_at": None,
            "execution_count": 5,
            "success_count": 4,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            existing_row
        )

        updated_row = existing_row.copy()
        updated_row["execution_count"] = 6
        updated_row["success_count"] = 4  # Unchanged
        updated_row["last_used_at"] = now.isoformat()
        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
            [updated_row]
        )

        result = await installer.record_usage("user-abc", "skill-456", success=False)

        assert result is not None
        assert result.execution_count == 6
        assert result.success_count == 4

    @patch("src.skills.installer.SupabaseClient.get_client")
    async def test_record_usage_updates_last_used_at(self, mock_get_client: MagicMock) -> None:
        """Test record_usage updates last_used_at timestamp."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        now = datetime.now(timezone.utc)
        existing_row = {
            "id": "123",
            "user_id": "user-abc",
            "tenant_id": "tenant-xyz",
            "skill_id": "skill-456",
            "skill_path": "anthropics/skills/pdf",
            "trust_level": "verified",
            "permissions_granted": [],
            "installed_at": now.isoformat(),
            "auto_installed": False,
            "last_used_at": None,
            "execution_count": 0,
            "success_count": 0,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            existing_row
        )

        updated_row = existing_row.copy()
        updated_row["execution_count"] = 1
        updated_row["success_count"] = 1
        updated_row["last_used_at"] = now.isoformat()
        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
            [updated_row]
        )

        result = await installer.record_usage("user-abc", "skill-456", success=True)

        assert result is not None
        assert result.last_used_at is not None

    @patch("src.skills.installer.SupabaseClient.get_client")
    async def test_record_usage_returns_none_for_nonexistent_skill(self, mock_get_client: MagicMock) -> None:
        """Test record_usage returns None when skill not installed."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        # Mock empty response
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            None
        )

        result = await installer.record_usage("user-abc", "nonexistent-skill", success=True)

        assert result is None

    @patch("src.skills.installer.SupabaseClient.get_client")
    async def test_record_usage_handles_database_error(self, mock_get_client: MagicMock) -> None:
        """Test record_usage returns None on database error."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        now = datetime.now(timezone.utc)
        existing_row = {
            "id": "123",
            "user_id": "user-abc",
            "tenant_id": "tenant-xyz",
            "skill_id": "skill-456",
            "skill_path": "anthropics/skills/pdf",
            "trust_level": "verified",
            "permissions_granted": [],
            "installed_at": now.isoformat(),
            "auto_installed": False,
            "last_used_at": None,
            "execution_count": 0,
            "success_count": 0,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            existing_row
        )

        # Mock update error
        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.side_effect = (
            Exception("Database connection error")
        )

        result = await installer.record_usage("user-abc", "skill-456", success=True)

        assert result is None

    @patch("src.skills.installer.SupabaseClient.get_client")
    async def test_record_usage_defaults_success_to_true(self, mock_get_client: MagicMock) -> None:
        """Test record_usage defaults success parameter to True."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        now = datetime.now(timezone.utc)
        existing_row = {
            "id": "123",
            "user_id": "user-abc",
            "tenant_id": "tenant-xyz",
            "skill_id": "skill-456",
            "skill_path": "anthropics/skills/pdf",
            "trust_level": "verified",
            "permissions_granted": [],
            "installed_at": now.isoformat(),
            "auto_installed": False,
            "last_used_at": None,
            "execution_count": 0,
            "success_count": 0,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            existing_row
        )

        updated_row = existing_row.copy()
        updated_row["execution_count"] = 1
        updated_row["success_count"] = 1  # Should increment since default is True
        updated_row["last_used_at"] = now.isoformat()
        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value.data = (
            [updated_row]
        )

        result = await installer.record_usage("user-abc", "skill-456")

        assert result is not None
        assert result.execution_count == 1
        assert result.success_count == 1


class TestSkillInstallerIntegration:
    """Integration tests for full skill installer workflow."""

    @patch("src.skills.installer.SupabaseClient.get_client")
    async def test_full_workflow_install_is_installed_record_usage_uninstall(self, mock_get_client: MagicMock) -> None:
        """Test complete workflow: install -> is_installed -> record_usage -> uninstall."""
        from src.skills.installer import SkillInstaller
        from src.skills.index import SkillIndex, SkillIndexEntry
        from src.security.trust_levels import SkillTrustLevel
        from datetime import datetime, timezone

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        user_id = "user-123"
        skill_id = "skill-456"
        now = datetime.now(timezone.utc)

        # Step 1: Install - skill not yet installed, skill index lookup succeeds
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            None
        )

        # Mock SkillIndex.get_skill with AsyncMock
        with patch.object(SkillIndex, "get_skill", new=AsyncMock()) as mock_get_skill:
            mock_skill_entry = SkillIndexEntry(
                id=skill_id,
                skill_path="anthropics/skills/pdf",
                skill_name="PDF Reader",
                description="Read PDF files",
                full_content="Skill content here",
                content_hash="abc123",
                author="Anthropic",
                version="1.0.0",
                tags=["pdf", "reader"],
                trust_level=SkillTrustLevel.VERIFIED,
                life_sciences_relevant=False,
                declared_permissions=[],
                summary_verbosity="standard",
                last_synced=now,
                created_at=now,
                updated_at=now,
            )
            mock_get_skill.return_value = mock_skill_entry

            # Mock insert response
            installed_row = {
                "id": "install-123",
                "user_id": user_id,
                "tenant_id": None,
                "skill_id": skill_id,
                "skill_path": "anthropics/skills/pdf",
                "trust_level": "verified",
                "permissions_granted": [],
                "installed_at": now.isoformat(),
                "auto_installed": False,
                "last_used_at": None,
                "execution_count": 0,
                "success_count": 0,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }

            mock_insert_response = MagicMock()
            mock_insert_response.data = [installed_row]
            mock_client.table.return_value.insert.return_value.execute.return_value = mock_insert_response

            # Execute install
            installed_skill = await installer.install(user_id, skill_id)

            # Verify install
            assert installed_skill is not None
            assert installed_skill.user_id == user_id
            assert installed_skill.skill_id == skill_id
            assert installed_skill.execution_count == 0
            assert installed_skill.success_count == 0
            mock_get_skill.assert_called_once_with(skill_id)

        # Step 2: is_installed - skill is now installed
        mock_client.reset_mock()
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            installed_row
        )

        is_installed = await installer.is_installed(user_id, skill_id)
        assert is_installed is True

        # Step 3: record_usage - increment counters
        mock_client.reset_mock()
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            installed_row
        )

        updated_row = installed_row.copy()
        updated_row["execution_count"] = 1
        updated_row["success_count"] = 1
        updated_row["last_used_at"] = now.isoformat()

        mock_update_response = MagicMock()
        mock_update_response.data = [updated_row]
        mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = (
            mock_update_response
        )

        result = await installer.record_usage(user_id, skill_id, success=True)
        assert result is not None
        assert result.execution_count == 1
        assert result.success_count == 1
        assert result.last_used_at is not None

        # Step 4: uninstall - remove the skill
        mock_client.reset_mock()
        mock_delete_response = MagicMock()
        mock_delete_response.count = 1
        mock_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = (
            mock_delete_response
        )

        uninstalled = await installer.uninstall(user_id, skill_id)
        assert uninstalled is True

        # Verify uninstall was called correctly
        mock_client.table.assert_called_with("user_skills")
        mock_client.table.return_value.delete.assert_called_once()

    @patch("src.skills.installer.SupabaseClient.get_client")
    async def test_install_idempotent_reinstall_returns_existing(self, mock_get_client: MagicMock) -> None:
        """Test installing an already-installed skill returns existing installation."""
        from src.skills.installer import SkillInstaller
        from src.skills.index import SkillIndex, SkillIndexEntry
        from src.security.trust_levels import SkillTrustLevel
        from datetime import datetime, timezone

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        user_id = "user-123"
        skill_id = "skill-456"
        now = datetime.now(timezone.utc)

        # Existing installation
        existing_row = {
            "id": "install-123",
            "user_id": user_id,
            "tenant_id": None,
            "skill_id": skill_id,
            "skill_path": "anthropics/skills/pdf",
            "trust_level": "verified",
            "permissions_granted": [],
            "installed_at": now.isoformat(),
            "auto_installed": False,
            "last_used_at": None,
            "execution_count": 5,
            "success_count": 5,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        # Mock: skill already installed
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            existing_row
        )

        # Mock skill index entry
        mock_skill_entry = SkillIndexEntry(
            id=skill_id,
            skill_path="anthropics/skills/pdf",
            skill_name="PDF Reader",
            description="Read PDF files",
            full_content="Skill content",
            content_hash="abc123",
            author="Anthropic",
            version="1.0.0",
            tags=["pdf"],
            trust_level=SkillTrustLevel.VERIFIED,
            life_sciences_relevant=False,
            declared_permissions=[],
            summary_verbosity="standard",
            last_synced=now,
            created_at=now,
            updated_at=now,
        )

        with patch.object(SkillIndex, "get_skill", new=AsyncMock(return_value=mock_skill_entry)):
            # Attempt to reinstall
            result = await installer.install(user_id, skill_id)

            # Should return existing installation without creating new one
            assert result is not None
            assert result.id == "install-123"
            assert result.execution_count == 5
            assert result.success_count == 5

            # Verify no insert was performed
            mock_client.table.return_value.insert.assert_not_called()

    @patch("src.skills.installer.SupabaseClient.get_client")
    async def test_record_usage_multiple_executions_builds_history(self, mock_get_client: MagicMock) -> None:
        """Test recording multiple usages builds accurate execution history."""
        from src.skills.installer import SkillInstaller
        from datetime import datetime, timezone

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        user_id = "user-123"
        skill_id = "skill-456"
        now = datetime.now(timezone.utc)

        # Initial state
        base_row = {
            "id": "install-123",
            "user_id": user_id,
            "tenant_id": None,
            "skill_id": skill_id,
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

        # Simulate 10 executions with 2 failures
        execution_count = 0
        success_count = 0

        for i in range(10):
            mock_client.reset_mock()

            # Current state
            current_row = base_row.copy()
            current_row["execution_count"] = execution_count
            current_row["success_count"] = success_count

            mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
                current_row
            )

            # Determine success (fail on iterations 3 and 7)
            success = i not in [3, 7]
            execution_count += 1
            if success:
                success_count += 1

            # Updated state
            updated_row = current_row.copy()
            updated_row["execution_count"] = execution_count
            updated_row["success_count"] = success_count
            updated_row["last_used_at"] = now.isoformat()

            mock_update_response = MagicMock()
            mock_update_response.data = [updated_row]
            mock_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = (
                mock_update_response
            )

            # Record usage
            result = await installer.record_usage(user_id, skill_id, success=success)

            assert result is not None
            assert result.execution_count == execution_count
            assert result.success_count == success_count

        # Final state: 10 executions, 8 successes
        assert execution_count == 10
        assert success_count == 8

    @patch("src.skills.installer.SupabaseClient.get_client")
    async def test_install_with_tenant_and_permissions(self, mock_get_client: MagicMock) -> None:
        """Test installing a skill with tenant ID and custom permissions."""
        from src.skills.installer import SkillInstaller
        from src.skills.index import SkillIndex, SkillIndexEntry
        from src.security.trust_levels import SkillTrustLevel
        from datetime import datetime, timezone

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        user_id = "user-123"
        skill_id = "skill-456"
        tenant_id = "tenant-abc"
        custom_permissions = ["network_read", "file_write"]
        now = datetime.now(timezone.utc)

        # Mock: skill not yet installed
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.side_effect = [
            MagicMock(data=None),  # Not installed
        ]

        # Mock skill index entry
        mock_skill_entry = SkillIndexEntry(
            id=skill_id,
            skill_path="aria:clinical-analyzer",
            skill_name="Clinical Analyzer",
            description="Analyze clinical data",
            full_content="Skill content",
            content_hash="xyz789",
            author="ARIA",
            version="2.0.0",
            tags=["clinical", "healthcare"],
            trust_level=SkillTrustLevel.CORE,
            life_sciences_relevant=True,
            declared_permissions=["network_read"],
            summary_verbosity="detailed",
            last_synced=now,
            created_at=now,
            updated_at=now,
        )

        with patch.object(SkillIndex, "get_skill", new=AsyncMock(return_value=mock_skill_entry)):
            # Mock insert response
            installed_row = {
                "id": "install-456",
                "user_id": user_id,
                "tenant_id": tenant_id,
                "skill_id": skill_id,
                "skill_path": "aria:clinical-analyzer",
                "trust_level": "core",
                "permissions_granted": custom_permissions,
                "installed_at": now.isoformat(),
                "auto_installed": True,
                "last_used_at": None,
                "execution_count": 0,
                "success_count": 0,
                "created_at": now.isoformat(),
                "updated_at": now.isoformat(),
            }

            mock_insert_response = MagicMock()
            mock_insert_response.data = [installed_row]
            mock_client.table.return_value.insert.return_value.execute.return_value = mock_insert_response

            # Install with tenant and custom permissions
            result = await installer.install(
                user_id,
                skill_id,
                tenant_id=tenant_id,
                auto_installed=True,
                permissions_granted=custom_permissions,
            )

            # Verify
            assert result is not None
            assert result.tenant_id == tenant_id
            assert result.permissions_granted == custom_permissions
            assert result.auto_installed is True
            assert result.trust_level == SkillTrustLevel.CORE

    @patch("src.skills.installer.SupabaseClient.get_client")
    async def test_install_nonexistent_skill_raises_error(self, mock_get_client: MagicMock) -> None:
        """Test installing a non-existent skill raises SkillNotFoundError."""
        from src.skills.installer import SkillInstaller, SkillNotFoundError
        from src.skills.index import SkillIndex

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        user_id = "user-123"
        skill_id = "nonexistent-skill"

        # Mock: skill not installed, and not in index
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            None
        )

        with patch.object(SkillIndex, "get_skill", new=AsyncMock(return_value=None)):
            # Attempt to install non-existent skill
            with pytest.raises(SkillNotFoundError) as exc_info:
                await installer.install(user_id, skill_id)

            assert "not found in skills index" in str(exc_info.value)

    @patch("src.skills.installer.SupabaseClient.get_client")
    async def test_get_installed_returns_none_for_uninstalled_skill(self, mock_get_client: MagicMock) -> None:
        """Test get_installed returns None for a skill that was never installed."""
        from src.skills.installer import SkillInstaller

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        user_id = "user-123"
        skill_id = "skill-456"

        # Mock: skill not found
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            None
        )

        result = await installer.get_installed(user_id, skill_id)
        assert result is None

    @patch("src.skills.installer.SupabaseClient.get_client")
    async def test_uninstall_idempotent(self, mock_get_client: MagicMock) -> None:
        """Test uninstalling an already-uninstalled skill returns False."""
        from src.skills.installer import SkillInstaller

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        user_id = "user-123"
        skill_id = "skill-456"

        # Mock: no rows deleted
        mock_delete_response = MagicMock()
        mock_delete_response.count = 0
        mock_client.table.return_value.delete.return_value.eq.return_value.eq.return_value.execute.return_value = (
            mock_delete_response
        )

        # First uninstall
        result1 = await installer.uninstall(user_id, skill_id)
        assert result1 is False

        # Second uninstall (should also return False)
        result2 = await installer.uninstall(user_id, skill_id)
        assert result2 is False

    @patch("src.skills.installer.SupabaseClient.get_client")
    async def test_workflow_get_installed_before_install(self, mock_get_client: MagicMock) -> None:
        """Test calling get_installed before install returns None, then returns value after install."""
        from src.skills.installer import SkillInstaller
        from src.skills.index import SkillIndex, SkillIndexEntry
        from src.security.trust_levels import SkillTrustLevel
        from datetime import datetime, timezone

        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        installer = SkillInstaller()

        user_id = "user-123"
        skill_id = "skill-456"
        now = datetime.now(timezone.utc)

        # Before install: get_installed returns None
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value.data = (
            None
        )

        result_before = await installer.get_installed(user_id, skill_id)
        assert result_before is None

        # Install the skill
        mock_client.reset_mock()

        # Mock: not yet installed
        mock_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.side_effect = [
            MagicMock(data=None),  # Not installed check
        ]

        # Mock skill index
        mock_skill_entry = SkillIndexEntry(
            id=skill_id,
            skill_path="test/skill",
            skill_name="Test Skill",
            description="A test skill",
            full_content="Content",
            content_hash="hash",
            author="Test",
            version="1.0",
            tags=["test"],
            trust_level=SkillTrustLevel.COMMUNITY,
            life_sciences_relevant=False,
            declared_permissions=[],
            summary_verbosity="standard",
            last_synced=now,
            created_at=now,
            updated_at=now,
        )

        with patch.object(SkillIndex, "get_skill", new=AsyncMock(return_value=mock_skill_entry)):
            installed_row = {
                "id": "install-123",
                "user_id": user_id,
                "tenant_id": None,
                "skill_id": skill_id,
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

            mock_insert_response = MagicMock()
            mock_insert_response.data = [installed_row]
            mock_client.table.return_value.insert.return_value.execute.return_value = mock_insert_response

            await installer.install(user_id, skill_id)

        # After install: get_installed returns the skill
        # Don't reset - just reconfigure for the new call
        def setup_get_installed_mock(row):
            mock_select = MagicMock()
            mock_eq1 = MagicMock()
            mock_eq2 = MagicMock()
            mock_single = MagicMock()
            mock_exec = MagicMock()
            mock_exec.data = row

            mock_single.execute.return_value = mock_exec
            mock_eq2.single.return_value = mock_single
            mock_eq1.eq.return_value = mock_eq2
            mock_select.eq.return_value = mock_eq1
            mock_client.table.return_value.select.return_value = mock_select

        setup_get_installed_mock(installed_row)

        result_after = await installer.get_installed(user_id, skill_id)
        assert result_after is not None
        assert result_after.skill_id == skill_id
        assert result_after.user_id == user_id
