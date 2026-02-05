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
