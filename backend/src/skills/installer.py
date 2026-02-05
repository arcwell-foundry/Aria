"""Skill installer service for managing user-installed skills.

This module provides the SkillInstaller class which:
1. Manages skill installation/uninstallation for users
2. Tracks usage statistics (execution count, success rate)
3. Enforces trust level and permission requirements
4. Provides skill lifecycle management
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from src.db.supabase import SupabaseClient
from src.security.trust_levels import SkillTrustLevel

logger = logging.getLogger(__name__)


class SkillNotFoundError(Exception):
    """Raised when a skill is not found in the skills index."""

    pass


@dataclass(frozen=True)
class InstalledSkill:
    """A skill installed by a user.

    Attributes match the database schema for user_skills table.

    This dataclass represents a skill that has been installed by a specific user,
    including cached metadata from the skills index and usage statistics.
    """

    id: str
    user_id: str
    tenant_id: str | None
    skill_id: str
    skill_path: str
    trust_level: SkillTrustLevel
    permissions_granted: list[str]
    installed_at: datetime
    auto_installed: bool
    last_used_at: datetime | None
    execution_count: int
    success_count: int
    created_at: datetime
    updated_at: datetime


class SkillInstaller:
    """Service for managing skill installation and lifecycle.

    Handles installation, uninstallation, and usage tracking for skills
    while enforcing security policies and trust level restrictions.
    """

    def __init__(self) -> None:
        """Initialize the skill installer."""
        self._client = SupabaseClient.get_client()

    def _db_row_to_installed_skill(self, row: dict[str, Any]) -> InstalledSkill:
        """Convert a database row to an InstalledSkill.

        Args:
            row: Dictionary from Supabase representing a user_skills row.

        Returns:
            An InstalledSkill with all fields properly typed.

        Raises:
            ValueError: If required fields are missing.
        """
        # Convert trust_level string to enum
        trust_level_str = row.get("trust_level", "community")
        try:
            trust_level = SkillTrustLevel(trust_level_str)
        except ValueError:
            logger.warning(f"Unknown trust level '{trust_level_str}', defaulting to COMMUNITY")
            trust_level = SkillTrustLevel.COMMUNITY

        # Parse timestamps
        def parse_dt(value: Any) -> datetime | None:
            if value is None:
                return None
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            return None

        return InstalledSkill(
            id=str(row["id"]),
            user_id=str(row["user_id"]),
            tenant_id=row.get("tenant_id"),
            skill_id=str(row["skill_id"]),
            skill_path=str(row["skill_path"]),
            trust_level=trust_level,
            permissions_granted=row.get("permissions_granted") or [],
            installed_at=parse_dt(row["installed_at"]) or datetime.now(),
            auto_installed=bool(row.get("auto_installed", False)),
            last_used_at=parse_dt(row.get("last_used_at")),
            execution_count=int(row.get("execution_count", 0)),
            success_count=int(row.get("success_count", 0)),
            created_at=parse_dt(row["created_at"]) or datetime.now(),
            updated_at=parse_dt(row["updated_at"]) or datetime.now(),
        )

    async def _get_by_user_and_skill_id(self, user_id: str, skill_id: str) -> InstalledSkill | None:
        """Get an installed skill by user ID and skill ID.

        Args:
            user_id: The user's UUID.
            skill_id: The skill's UUID from skills_index.

        Returns:
            The InstalledSkill if found, None otherwise.
        """
        try:
            response = (
                self._client.table("user_skills")
                .select("*")
                .eq("user_id", user_id)
                .eq("skill_id", skill_id)
                .single()
                .execute()
            )
            if response.data:
                return self._db_row_to_installed_skill(response.data)
            return None
        except Exception as e:
            logger.debug(f"Installed skill not found for user {user_id}, skill {skill_id}: {e}")
            return None

    async def install(
        self,
        user_id: str,
        skill_id: str,
        *,
        tenant_id: str | None = None,
        auto_installed: bool = False,
        permissions_granted: list[str] | None = None,
    ) -> InstalledSkill:
        """Install a skill for a user.

        Validates that the skill exists in the skills index, then creates
        a user_skills record. If already installed, returns the existing record.

        Args:
            user_id: The user's UUID.
            skill_id: The skill's UUID from skills_index.
            tenant_id: Optional tenant/company ID for multi-tenant scenarios.
            auto_installed: True if ARIA auto-installed this, False if user-initiated.
            permissions_granted: Optional list of specific permissions granted.

        Returns:
            The InstalledSkill record.

        Raises:
            SkillNotFoundError: If the skill_id doesn't exist in skills_index.
        """
        # Import here to avoid circular dependency
        from src.skills.index import SkillIndex

        # First, verify the skill exists in the skills index
        skill_index = SkillIndex()
        skill_entry = await skill_index.get_skill(skill_id)

        if skill_entry is None:
            logger.error(f"Skill not found in index: {skill_id}")
            raise SkillNotFoundError(f"Skill with id {skill_id} not found in skills index")

        # Check if already installed
        existing = await self._get_by_user_and_skill_id(user_id, skill_id)
        if existing:
            logger.info(f"Skill {skill_id} already installed for user {user_id}")
            return existing

        # Create the installation record
        now = datetime.now()
        record = {
            "user_id": user_id,
            "tenant_id": tenant_id,
            "skill_id": skill_id,
            "skill_path": skill_entry.skill_path,
            "trust_level": skill_entry.trust_level.value,
            "permissions_granted": permissions_granted or skill_entry.declared_permissions,
            "installed_at": now.isoformat(),
            "auto_installed": auto_installed,
            "last_used_at": None,
            "execution_count": 0,
            "success_count": 0,
        }

        try:
            response = self._client.table("user_skills").insert(record).execute()
            if response.data:
                installed_skill = self._db_row_to_installed_skill(response.data[0])
                logger.info(
                    f"Installed skill {skill_entry.skill_path} for user {user_id} "
                    f"(trust_level={skill_entry.trust_level.value}, auto_installed={auto_installed})"
                )
                return installed_skill
            raise Exception("No data returned from insert")
        except Exception as e:
            logger.error(f"Failed to install skill {skill_id} for user {user_id}: {e}")
            raise

    async def uninstall(self, user_id: str, skill_id: str) -> bool:
        """Uninstall a skill for a user.

        Args:
            user_id: The user's UUID.
            skill_id: The skill's UUID from skills_index.

        Returns:
            True if the skill was uninstalled, False if it wasn't installed.
        """
        try:
            response = (
                self._client.table("user_skills")
                .delete()
                .eq("user_id", user_id)
                .eq("skill_id", skill_id)
                .execute()
            )
            # Check if any rows were deleted
            count = getattr(response, "count", None)
            return count is not None and count > 0
        except Exception as e:
            logger.error(f"Error uninstalling skill {skill_id} for user {user_id}: {e}")
            return False
