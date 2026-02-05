"""Skill index service for discovering and cataloging skills from skills.sh.

This module provides the SkillIndex class which:
1. Syncs skills metadata from skills.sh API/GitHub
2. Stores skills in Supabase with security classification
3. Enables fast search and retrieval
4. Generates compact summaries for context management
"""

import hashlib
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import httpx

from src.core.config import settings
from src.db.supabase import SupabaseClient
from src.security.trust_levels import SkillTrustLevel, determine_trust_level

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SkillIndexEntry:
    """A skill entry in the index.

    Attributes match the database schema for skills_index table.
    """

    id: str
    skill_path: str
    skill_name: str
    description: str | None
    full_content: str | None
    content_hash: str | None
    author: str | None
    version: str | None
    tags: list[str]
    trust_level: SkillTrustLevel
    life_sciences_relevant: bool
    declared_permissions: list[str]
    summary_verbosity: str  # 'minimal', 'standard', 'detailed'
    last_synced: datetime | None
    created_at: datetime
    updated_at: datetime


# Three-tier awareness constants for context management

# TIER 1: CORE skills - always loaded in working memory
# These are ARIA's built-in skills used frequently
TIER_1_CORE_SKILLS: tuple[str, ...] = (
    "aria:document-parser",
    "aria:email-generator",
    "aria:meeting-summarizer",
    # Additional CORE skills as they are built
)

# TIER 2: Life sciences relevant - loaded when analyzing domain-specific tasks
# Identified by life_sciences_relevant = True in database
TIER_2_RELEVANT_TAG = "life_sciences_relevant = True"

# TIER 3: Discovery - all other skills, searched on-demand
TIER_3_DISCOVERY_ALL = "all skills"

# Summary generation constants
MAX_SUMMARY_WORDS = 25
MAX_DESCRIPTION_WORDS_IN_SUMMARY = 15


class SkillIndex:
    """Service for managing the skills index.

    Provides discovery, search, and retrieval of skills from skills.sh
    with proper security classification and tiered awareness.
    """

    def __init__(self) -> None:
        """Initialize the skill index."""
        self._client = SupabaseClient.get_client()
        self._http_client: httpx.AsyncClient | None = None

    def _db_row_to_entry(self, row: dict[str, Any]) -> SkillIndexEntry:
        """Convert a database row to a SkillIndexEntry.

        Args:
            row: Dictionary from Supabase representing a skills_index row.

        Returns:
            A SkillIndexEntry with all fields properly typed.

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

        return SkillIndexEntry(
            id=str(row["id"]),
            skill_path=str(row["skill_path"]),
            skill_name=str(row["skill_name"]),
            description=row.get("description"),
            full_content=row.get("full_content"),
            content_hash=row.get("content_hash"),
            author=row.get("author"),
            version=row.get("version"),
            tags=row.get("tags") or [],
            trust_level=trust_level,
            life_sciences_relevant=bool(row.get("life_sciences_relevant", False)),
            declared_permissions=row.get("declared_permissions") or [],
            summary_verbosity=str(row.get("summary_verbosity", "standard")),
            last_synced=parse_dt(row.get("last_synced")),
            created_at=parse_dt(row["created_at"]) or datetime.now(),
            updated_at=parse_dt(row["updated_at"]) or datetime.now(),
        )

    async def get_skill(self, skill_id: str) -> SkillIndexEntry | None:
        """Get a skill by ID.

        Args:
            skill_id: The UUID of the skill.

        Returns:
            The SkillIndexEntry if found, None otherwise.
        """
        try:
            response = (
                self._client.table("skills_index").select("*").eq("id", skill_id).single().execute()
            )
            if response.data:
                return self._db_row_to_entry(response.data)
            return None
        except Exception as e:
            logger.debug(f"Skill not found: {skill_id}, error: {e}")
            return None

    async def search(
        self,
        query: str,
        *,
        trust_level: SkillTrustLevel | None = None,
        life_sciences_relevant: bool | None = None,
        limit: int = 50,
    ) -> list[SkillIndexEntry]:
        """Search for skills by name, description, or tags.

        Args:
            query: Search query string.
            trust_level: Optional filter by trust level.
            life_sciences_relevant: Optional filter by life sciences relevance.
            limit: Maximum results to return.

        Returns:
            List of matching SkillIndexEntry objects.
        """
        try:
            # Build the query
            select_builder = self._client.table("skills_index").select("*")

            # Apply filters
            if trust_level:
                select_builder = select_builder.eq("trust_level", trust_level.value)

            if life_sciences_relevant is not None:
                select_builder = select_builder.eq("life_sciences_relevant", life_sciences_relevant)

            # For full-text search, use Postgres text search
            if query:
                # Sanitize query to prevent SQL injection
                sanitized_query = query.replace("%", "\\%").replace("_", "\\_")
                # Use OR filter for name, description, or tags
                select_builder = select_builder.or_(
                    f"skill_name.ilike.%{sanitized_query}%,description.ilike.%{sanitized_query}%"
                )

            # Execute with limit
            response = select_builder.limit(limit).execute()

            # Convert to entries
            return [self._db_row_to_entry(row) for row in response.data]

        except Exception as e:
            logger.error(f"Error searching skills: {e}")
            return []

    async def get_summaries(self, skill_ids: list[str]) -> dict[str, str]:
        """Get compact summaries for multiple skills.

        Generates ~20-word summaries suitable for context management.
        Used by the orchestrator to provide skill awareness without full content.

        Args:
            skill_ids: List of skill UUIDs to summarize.

        Returns:
            Dictionary mapping skill_id to summary string.
            Skills not found are omitted from the result.
        """
        if not skill_ids:
            return {}

        try:
            # Fetch skills by IDs
            response = self._client.table("skills_index").select("*").in_("id", skill_ids).execute()

            # Generate compact summaries
            summaries: dict[str, str] = {}
            for row in response.data:
                entry = self._db_row_to_entry(row)
                summary = self._generate_compact_summary(entry)
                summaries[entry.id] = summary

            return summaries

        except Exception as e:
            logger.error(f"Error getting skill summaries: {e}")
            return {}

    def _generate_compact_summary(self, entry: SkillIndexEntry) -> str:
        """Generate a compact ~20-word summary for a skill entry.

        Args:
            entry: The skill entry to summarize.

        Returns:
            A compact summary string (target: ~20 words, max: 25 words).
        """
        # Start with skill name
        parts = [entry.skill_name]

        # Add description if available (truncated)
        if entry.description:
            # Take first ~15 words of description
            desc_words = entry.description.split()[:MAX_DESCRIPTION_WORDS_IN_SUMMARY]
            parts.append(" ".join(desc_words))

        # Add trust level indicator
        trust_indicator = {
            SkillTrustLevel.CORE: "[CORE]",
            SkillTrustLevel.VERIFIED: "[Verified]",
            SkillTrustLevel.COMMUNITY: "[Community]",
            SkillTrustLevel.USER: "[User]",
        }
        parts.append(trust_indicator.get(entry.trust_level, ""))

        # Add LS indicator if relevant
        if entry.life_sciences_relevant:
            parts.append("[Life Sciences]")

        # Combine and truncate to ~25 words max
        combined = " ".join(parts)
        words = combined.split()
        if len(words) > MAX_SUMMARY_WORDS:
            combined = " ".join(words[:MAX_SUMMARY_WORDS])

        return combined

    @property
    def _http(self) -> httpx.AsyncClient:
        """Lazy initialization of HTTP client for skills.sh API.

        Returns:
            An httpx.AsyncClient instance for making API requests.
        """
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=30.0,
                headers={"Accept": "application/json"},
            )
        return self._http_client

    async def refresh_if_stale(self, max_age_hours: int = 24) -> bool:
        """Check if skills index is stale and refresh if needed.

        Args:
            max_age_hours: Maximum age in hours before considering data stale.
                           Default is 24 hours.

        Returns:
            True if a refresh was performed, False if data was fresh.
        """
        try:
            # Check the most recent sync time
            response = (
                self._client.table("skills_index")
                .select("last_synced")
                .order("last_synced", desc=True)
                .limit(1)
                .execute()
            )

            # Use timezone-aware datetime for consistency
            now = datetime.now().astimezone()

            if not response.data:
                # No skills exist, need to sync
                logger.info("No skills in index, performing initial sync")
                await self.sync_from_skills_sh()
                return True

            # Check the most recent sync time
            last_sync_str = response.data[0].get("last_synced")
            if not last_sync_str:
                logger.info("Skills exist but no sync time recorded, performing sync")
                await self.sync_from_skills_sh()
                return True

            # Parse the sync time
            if isinstance(last_sync_str, str):
                last_sync = datetime.fromisoformat(last_sync_str.replace("Z", "+00:00"))
            else:
                last_sync = last_sync_str

            # Check if stale
            age_threshold = timedelta(hours=max_age_hours)
            age = now - last_sync

            if age > age_threshold:
                logger.info(f"Skills index is stale (age: {age}), refreshing")
                await self.sync_from_skills_sh()
                return True

            logger.debug(f"Skills index is fresh (age: {age}), no refresh needed")
            return False

        except Exception as e:
            logger.error(f"Error checking if skills index is stale: {e}")
            return False

    async def sync_from_skills_sh(self) -> int:
        """Sync skills from skills.sh API/GitHub to local database.

        Fetches the latest skills metadata, calculates hashes,
        determines trust levels, and upserts to the database.

        Returns:
            The number of skills synced.
        """
        skills_synced = 0
        now = datetime.now()

        try:
            # Fetch skills from the configured skills.sh API URL
            api_url = f"{settings.SKILLS_SH_API_URL}/skills"
            response = await self._http.get(api_url)
            response.raise_for_status()
            skills_data = response.json().get("skills", [])

            # Process each skill
            for skill_data in skills_data:
                try:
                    # Extract fields from API response
                    skill_path = skill_data.get("path", "")
                    skill_name = skill_data.get("name", "")
                    description = skill_data.get("description")
                    full_content = skill_data.get("content")

                    # Calculate content hash
                    content_hash = ""
                    if full_content:
                        content_hash = hashlib.sha256(full_content.encode()).hexdigest()

                    # Determine trust level from path
                    trust_level = determine_trust_level(skill_path)

                    # Check for life sciences relevance (from tags or description)
                    life_sciences_relevant = self._is_life_sciences_relevant(skill_data)

                    # Prepare database record
                    record = {
                        "skill_path": skill_path,
                        "skill_name": skill_name,
                        "description": description,
                        "full_content": full_content,
                        "content_hash": content_hash,
                        "author": skill_data.get("author"),
                        "version": skill_data.get("version"),
                        "tags": skill_data.get("tags", []),
                        "trust_level": trust_level.value,
                        "life_sciences_relevant": life_sciences_relevant,
                        "declared_permissions": skill_data.get("permissions", []),
                        "summary_verbosity": "standard",
                        "last_synced": now.isoformat(),
                    }

                    # Upsert to database
                    self._client.table("skills_index").upsert(record).execute()
                    skills_synced += 1

                except Exception as e:
                    logger.warning(f"Error syncing skill {skill_data.get('path')}: {e}")
                    continue

            logger.info(f"Synced {skills_synced} skills from skills.sh")
            return skills_synced

        except httpx.HTTPError as e:
            logger.error(f"HTTP error fetching skills from skills.sh: {e}")
            return 0
        except Exception as e:
            logger.error(f"Error syncing skills from skills.sh: {e}")
            return 0

    def _is_life_sciences_relevant(self, skill_data: dict[str, Any]) -> bool:
        """Check if a skill is relevant to life sciences domain.

        Args:
            skill_data: The skill data from the API.

        Returns:
            True if the skill appears relevant to life sciences.
        """
        # Check tags
        tags = skill_data.get("tags", [])
        ls_tags = {
            "clinical",
            "medical",
            "healthcare",
            "pharma",
            "biotech",
            "fda",
            "clinical-trials",
            "life-sciences",
            "lifesciences",
            "pubmed",
            "research",
            "bio",
            "health",
            "drug",
            "medicine",
        }
        if any(tag.lower() in ls_tags for tag in tags):
            return True

        # Check description
        description = skill_data.get("description", "").lower()
        ls_keywords = {
            "clinical trial",
            "fda",
            "pharmaceutical",
            "medical",
            "life science",
            "healthcare",
            "biotechnology",
            "pubmed",
            "drug development",
            "regulatory",
            "patient",
            "diagnosis",
        }
        return any(keyword in description for keyword in ls_keywords)

    async def close(self) -> None:
        """Close the HTTP client.

        Should be called when the SkillIndex is no longer needed
        to properly clean up resources.
        """
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None
