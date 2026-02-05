# US-524: Skill Index Service Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a skill index service that discovers, catalogs, and searches skills from skills.sh with proper security classification and tiered awareness for ARIA's agent ecosystem.

**Architecture:** A new `SkillIndex` class with async httpx client for fetching skills from skills.sh API/GitHub. Data is stored in Supabase with RLS policies (readable by all authenticated users). The service supports full-text search, summary generation for context management, and three-tier awareness (CORE always-loaded, life-sciences relevant, and discovery). Trust levels are determined using existing `SkillTrustLevel` from security module.

**Tech Stack:** FastAPI, Pydantic, Supabase (PostgreSQL), httpx, existing security module (trust_levels.py)

---

## Task 1: Create Database Schema

**Files:**
- Create: `supabase/migrations/20260204_create_skills_index.sql`

**Step 1: Write the SQL migration**

Create the migration file with the schema for skills index:

```sql
-- Migration: Create skills_index table
-- US-524: Skill Index Service

-- Create enum for trust level (matches SkillTrustLevel in backend/src/security/trust_levels.py)
DO $$ BEGIN
    CREATE TYPE skill_trust_level AS ENUM (
        'core',
        'verified',
        'community',
        'user'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Create enum for summary verbosity
DO $$ BEGIN
    CREATE TYPE skill_summary_verbosity AS ENUM (
        'minimal',
        'standard',
        'detailed'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Create skills_index table
CREATE TABLE skills_index (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_path TEXT UNIQUE NOT NULL,
    skill_name TEXT NOT NULL,
    description TEXT,
    full_content TEXT,
    content_hash TEXT,
    author TEXT,
    version TEXT,
    tags TEXT[] DEFAULT '{}',
    trust_level skill_trust_level DEFAULT 'community',
    life_sciences_relevant BOOLEAN DEFAULT FALSE,
    declared_permissions TEXT[] DEFAULT '{}',
    summary_verbosity skill_summary_verbosity DEFAULT 'standard',
    last_synced TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Create indexes for efficient querying
CREATE INDEX idx_skills_index_skill_path ON skills_index(skill_path);
CREATE INDEX idx_skills_index_trust_level ON skills_index(trust_level);
CREATE INDEX idx_skills_index_life_sciences ON skills_index(life_sciences_relevant);
CREATE INDEX idx_skills_index_tags ON skills_index USING GIN(tags);
CREATE INDEX idx_skills_index_name_gin ON skills_index USING GIN(to_tsvector('english', skill_name || ' ' || COALESCE(description, '')));
CREATE INDEX idx_skills_index_last_synced ON skills_index(last_synced DESC);

-- Enable RLS
ALTER TABLE skills_index ENABLE ROW LEVEL SECURITY;

-- RLS Policies: All authenticated users can read skills (skill catalog is shared)
CREATE POLICY "Authenticated users can view skills"
    ON skills_index FOR SELECT
    USING (auth.uid() IS NOT NULL);

-- Only service role can insert/update skills (via backend service)
CREATE POLICY "Service role can insert skills"
    ON skills_index FOR INSERT
    WITH CHECK (auth.uid() IS NOT NULL);  -- Will be checked via service role key

CREATE POLICY "Service role can update skills"
    ON skills_index FOR UPDATE
    USING (auth.uid() IS NOT NULL);

-- Trigger for updated_at
CREATE OR REPLACE FUNCTION update_skills_index_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_skills_index_updated_at
    BEFORE UPDATE ON skills_index
    FOR EACH ROW
    EXECUTE FUNCTION update_skills_index_updated_at();

-- Comment on table
COMMENT ON TABLE skills_index IS 'Catalog of skills from skills.sh with metadata for search and security classification';
```

**Step 2: Verify migration is syntactically correct**

Run: `psql -h localhost -U postgres -d aria -f supabase/migrations/20260204_create_skills_index.sql` (or use Supabase CLI)
Expected: Tables and enums created successfully

**Step 3: Push migration to Supabase**

Run: `supabase db push`
Expected: Migration applied successfully

**Step 4: Commit**

```bash
git add supabase/migrations/20260204_create_skills_index.sql
git commit -m "feat(skills): add skills_index table with RLS policies"
```

---

## Task 2: Create Skills Module Init File

**Files:**
- Create: `backend/src/skills/__init__.py`

**Step 1: Write the module init**

Create the init file with exports for the skills module:

```python
"""Skills module for ARIA.

This module manages integration with skills.sh, providing:
- Skill discovery and indexing
- Search and retrieval
- Security-aware execution
- Multi-skill orchestration
"""

from src.skills.index import (
    SkillIndex,
    SkillIndexEntry,
    TIER_1_CORE_SKILLS,
    TIER_2_RELEVANT_TAG,
    TIER_3_DISCOVERY_ALL,
)

__all__ = [
    "SkillIndex",
    "SkillIndexEntry",
    "TIER_1_CORE_SKILLS",
    "TIER_2_RELEVANT_TAG",
    "TIER_3_DISCOVERY_ALL",
]
```

**Step 2: Verify module can be imported**

Run: `cd backend && python -c "from src.skills import SkillIndex; print('Import successful')"`
Expected: No errors, "Import successful" printed

**Step 3: Commit**

```bash
git add backend/src/skills/__init__.py
git commit -m "feat(skills): add skills module with exports"
```

---

## Task 3: Create SkillIndexEntry Dataclass

**Files:**
- Create: `backend/src/skills/index.py`

**Step 1: Write the SkillIndexEntry dataclass and module skeleton**

Create the index.py file with the dataclass and constants:

```python
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


# Placeholder class - will be implemented in subsequent tasks
class SkillIndex:
    """Service for managing the skills index."""
    pass
```

**Step 2: Verify dataclass can be imported and instantiated**

Run: `cd backend && python -c "from src.skills.index import SkillIndexEntry, TIER_1_CORE_SKILLS; print('Success:', TIER_1_CORE_SKILLS)"`
Expected: No errors, tuple printed

**Step 3: Commit**

```bash
git add backend/src/skills/index.py
git commit -m "feat(skills): add SkillIndexEntry dataclass and tier constants"
```

---

## Task 4: Write Unit Tests for Constants and Dataclass

**Files:**
- Create: `backend/tests/test_skill_index.py`

**Step 1: Write tests for SkillIndexEntry and constants**

```python
"""Tests for skill index service."""

import pytest
from datetime import datetime

from src.security.trust_levels import SkillTrustLevel
from src.skills.index import (
    SkillIndexEntry,
    TIER_1_CORE_SKILLS,
    TIER_2_RELEVANT_TAG,
    TIER_3_DISCOVERY_ALL,
)


class TestTierConstants:
    """Tests for three-tier awareness constants."""

    def test_tier_1_core_skills_is_tuple(self) -> None:
        """Test TIER_1_CORE_SKILLS is a tuple of strings."""
        assert isinstance(TIER_1_CORE_SKILLS, tuple)
        assert len(TIER_1_CORE_SKILLS) >= 3  # At least the 3 we defined

    def test_tier_1_core_skills_have_aria_prefix(self) -> None:
        """Test TIER_1_CORE_SKILLS all have 'aria:' prefix."""
        for skill_path in TIER_1_CORE_SKILLS:
            assert skill_path.startswith("aria:")

    def test_tier_2_relevant_tag_is_string(self) -> None:
        """Test TIER_2_RELEVANT_TAG is a descriptive string."""
        assert isinstance(TIER_2_RELEVANT_TAG, str)
        assert "life_sciences" in TIER_2_RELEVANT_TAG.lower()

    def test_tier_3_discovery_all_is_string(self) -> None:
        """Test TIER_3_DISCOVERY_ALL is a descriptive string."""
        assert isinstance(TIER_3_DISCOVERY_ALL, str)


class TestSkillIndexEntry:
    """Tests for SkillIndexEntry dataclass."""

    def test_create_minimal_entry(self) -> None:
        """Test creating a SkillIndexEntry with required fields."""
        entry = SkillIndexEntry(
            id="123",
            skill_path="test/skill",
            skill_name="Test Skill",
            description=None,
            full_content=None,
            content_hash=None,
            author=None,
            version=None,
            tags=[],
            trust_level=SkillTrustLevel.COMMUNITY,
            life_sciences_relevant=False,
            declared_permissions=[],
            summary_verbosity="standard",
            last_synced=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        assert entry.skill_path == "test/skill"
        assert entry.skill_name == "Test Skill"

    def test_create_full_entry(self) -> None:
        """Test creating a SkillIndexEntry with all fields."""
        now = datetime.now()
        entry = SkillIndexEntry(
            id="123",
            skill_path="anthropics/skills/pdf",
            skill_name="PDF Parser",
            description="Parse PDF documents",
            full_content="# PDF Parser\nFull content here",
            content_hash="abc123",
            author="anthropic",
            version="1.0.0",
            tags=["pdf", "parser", "document"],
            trust_level=SkillTrustLevel.VERIFIED,
            life_sciences_relevant=True,
            declared_permissions=["network_read"],
            summary_verbosity="detailed",
            last_synced=now,
            created_at=now,
            updated_at=now,
        )
        assert entry.trust_level == SkillTrustLevel.VERIFIED
        assert entry.life_sciences_relevant is True
        assert "pdf" in entry.tags

    def test_entry_is_frozen(self) -> None:
        """Test SkillIndexEntry is frozen (immutable)."""
        entry = SkillIndexEntry(
            id="123",
            skill_path="test/skill",
            skill_name="Test",
            description=None,
            full_content=None,
            content_hash=None,
            author=None,
            version=None,
            tags=[],
            trust_level=SkillTrustLevel.COMMUNITY,
            life_sciences_relevant=False,
            declared_permissions=[],
            summary_verbosity="standard",
            last_synced=None,
            created_at=datetime.now(),
            updated_at=datetime.now(),
        )
        with pytest.raises(Exception):  # FrozenInstanceError
            entry.skill_name = "Modified"

    def test_trust_level_enum_conversion(self) -> None:
        """Test trust_level accepts SkillTrustLevel enum."""
        for level in SkillTrustLevel:
            entry = SkillIndexEntry(
                id="123",
                skill_path="test/skill",
                skill_name="Test",
                description=None,
                full_content=None,
                content_hash=None,
                author=None,
                version=None,
                tags=[],
                trust_level=level,
                life_sciences_relevant=False,
                declared_permissions=[],
                summary_verbosity="standard",
                last_synced=None,
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            assert entry.trust_level == level
```

**Step 2: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_skill_index.py -v`
Expected: All tests pass

**Step 3: Commit**

```bash
git add backend/tests/test_skill_index.py
git commit -m "test(skills): add tests for SkillIndexEntry and tier constants"
```

---

## Task 5: Implement SkillIndex._db_row_to_entry Method

**Files:**
- Modify: `backend/src/skills/index.py`

**Step 1: Write the failing test first**

Add to `backend/tests/test_skill_index.py`:

```python
class TestSkillIndexDbConversion:
    """Tests for SkillIndex database conversion methods."""

    @pytest.mark.asyncio
    async def test_db_row_to_entry_converts_valid_row(self) -> None:
        """Test _db_row_to_entry converts database row to SkillIndexEntry."""
        from src.skills.index import SkillIndex

        index = SkillIndex()

        db_row = {
            "id": "123",
            "skill_path": "test/skill",
            "skill_name": "Test Skill",
            "description": "A test skill",
            "full_content": "# Content",
            "content_hash": "hash123",
            "author": "test",
            "version": "1.0",
            "tags": ["test", "skill"],
            "trust_level": "community",
            "life_sciences_relevant": True,
            "declared_permissions": [],
            "summary_verbosity": "standard",
            "last_synced": "2024-01-01T00:00:00+00:00",
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }

        entry = index._db_row_to_entry(db_row)

        assert entry.skill_path == "test/skill"
        assert entry.skill_name == "Test Skill"
        assert entry.trust_level == SkillTrustLevel.COMMUNITY
        assert entry.life_sciences_relevant is True

    @pytest.mark.asyncio
    async def test_db_row_to_entry_handles_none_values(self) -> None:
        """Test _db_row_to_entry handles optional None values."""
        from src.skills.index import SkillIndex

        index = SkillIndex()

        db_row = {
            "id": "123",
            "skill_path": "test/skill",
            "skill_name": "Test Skill",
            "description": None,
            "full_content": None,
            "content_hash": None,
            "author": None,
            "version": None,
            "tags": [],
            "trust_level": "community",
            "life_sciences_relevant": False,
            "declared_permissions": [],
            "summary_verbosity": "standard",
            "last_synced": None,
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }

        entry = index._db_row_to_entry(db_row)

        assert entry.description is None
        assert entry.full_content is None
        assert entry.last_synced is None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_skill_index.py::TestSkillIndexDbConversion -v`
Expected: FAIL with "SkillIndex has no attribute '_db_row_to_entry'" or similar

**Step 3: Implement the method**

Modify `backend/src/skills/index.py` - replace the placeholder SkillIndex class with:

```python
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
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_skill_index.py::TestSkillIndexDbConversion -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/skills/index.py backend/tests/test_skill_index.py
git commit -m "feat(skills): add _db_row_to_entry conversion method with tests"
```

---

## Task 6: Implement SkillIndex.get_skill Method

**Files:**
- Modify: `backend/src/skills/index.py`
- Modify: `backend/tests/test_skill_index.py`

**Step 1: Write the failing test first**

Add to `backend/tests/test_skill_index.py`:

```python
class TestSkillIndexGetSkill:
    """Tests for SkillIndex.get_skill method."""

    @pytest.mark.asyncio
    async def test_get_skill_by_id_returns_entry(self) -> None:
        """Test get_skill returns SkillIndexEntry for valid ID."""
        from src.skills.index import SkillIndex
        from unittest.mock import Mock, patch

        index = SkillIndex()

        # Mock the Supabase response
        mock_response = Mock()
        mock_response.data = [{
            "id": "123",
            "skill_path": "test/skill",
            "skill_name": "Test Skill",
            "description": "A test skill",
            "full_content": "# Content",
            "content_hash": "hash123",
            "author": "test",
            "version": "1.0",
            "tags": ["test"],
            "trust_level": "community",
            "life_sciences_relevant": False,
            "declared_permissions": [],
            "summary_verbosity": "standard",
            "last_synced": None,
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }]
        mock_response.single = Mock(return_value=mock_response)

        with patch.object(SupabaseClient, "get_client", return_value=Mock()):
            with patch.object(index._client.table("skills_index"), "select", return_value=mock_response):
                entry = await index.get_skill("123")

        assert entry is not None
        assert entry.skill_path == "test/skill"
        assert entry.skill_name == "Test Skill"

    @pytest.mark.asyncio
    async def test_get_skill_returns_none_for_not_found(self) -> None:
        """Test get_skill returns None when skill doesn't exist."""
        from src.skills.index import SkillIndex
        from src.core.exceptions import NotFoundError
        from unittest.mock import Mock, patch

        index = SkillIndex()

        # Mock Supabase to raise NotFoundError
        with patch.object(SupabaseClient, "get_client", return_value=Mock()):
            with patch.object(
                index._client.table("skills_index"),
                "select",
                side_effect=NotFoundError("Skill", "123"),
            ):
                entry = await index.get_skill("123")

        assert entry is None
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_skill_index.py::TestSkillIndexGetSkill -v`
Expected: FAIL with "SkillIndex has no attribute 'get_skill'" or similar

**Step 3: Implement the method**

Add to `SkillIndex` class in `backend/src/skills/index.py`:

```python
    async def get_skill(self, skill_id: str) -> SkillIndexEntry | None:
        """Get a skill by ID.

        Args:
            skill_id: The UUID of the skill.

        Returns:
            The SkillIndexEntry if found, None otherwise.
        """
        try:
            response = (
                self._client.table("skills_index")
                .select("*")
                .eq("id", skill_id)
                .single()
                .execute()
            )
            if response.data:
                return self._db_row_to_entry(response.data)
            return None
        except Exception as e:
            logger.debug(f"Skill not found: {skill_id}, error: {e}")
            return None
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_skill_index.py::TestSkillIndexGetSkill -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/skills/index.py backend/tests/test_skill_index.py
git commit -m "feat(skills): add get_skill method with tests"
```

---

## Task 7: Implement SkillIndex.search Method

**Files:**
- Modify: `backend/src/skills/index.py`
- Modify: `backend/tests/test_skill_index.py`

**Step 1: Write the failing test first**

Add to `backend/tests/test_skill_index.py`:

```python
class TestSkillIndexSearch:
    """Tests for SkillIndex.search method."""

    @pytest.mark.asyncio
    async def test_search_returns_matching_skills(self) -> None:
        """Test search returns skills matching query."""
        from src.skills.index import SkillIndex
        from unittest.mock import Mock, patch

        index = SkillIndex()

        mock_data = [
            {
                "id": "1",
                "skill_path": "anthropics/skills/pdf",
                "skill_name": "PDF Parser",
                "description": "Parse PDF documents",
                "full_content": None,
                "content_hash": None,
                "author": "anthropic",
                "version": "1.0",
                "tags": ["pdf", "parser"],
                "trust_level": "verified",
                "life_sciences_relevant": False,
                "declared_permissions": [],
                "summary_verbosity": "standard",
                "last_synced": None,
                "created_at": "2024-01-01T00:00:00+00:00",
                "updated_at": "2024-01-01T00:00:00+00:00",
            },
        ]
        mock_response = Mock()
        mock_response.data = mock_data

        with patch.object(SupabaseClient, "get_client", return_value=Mock()):
            with patch.object(index._client.table("skills_index"), "select", return_value=mock_response):
                results = await index.search("pdf")

        assert len(results) == 1
        assert results[0].skill_name == "PDF Parser"

    @pytest.mark.asyncio
    async def test_search_with_empty_query_returns_all(self) -> None:
        """Test search with empty query returns all skills."""
        from src.skills.index import SkillIndex
        from unittest.mock import Mock, patch

        index = SkillIndex()

        mock_response = Mock()
        mock_response.data = []

        with patch.object(SupabaseClient, "get_client", return_value=Mock()):
            with patch.object(index._client.table("skills_index"), "select", return_value=mock_response):
                results = await index.search("")

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_filters_by_trust_level(self) -> None:
        """Test search can filter by trust level."""
        from src.skills.index import SkillIndex
        from unittest.mock import Mock, patch

        index = SkillIndex()

        mock_response = Mock()
        mock_response.data = []

        with patch.object(SupabaseClient, "get_client", return_value=Mock()):
            with patch.object(index._client.table("skills_index"), "select", return_value=mock_response):
                results = await index.search("pdf", trust_level=SkillTrustLevel.VERIFIED)

        assert isinstance(results, list)

    @pytest.mark.asyncio
    async def test_search_filters_by_life_sciences(self) -> None:
        """Test search can filter by life sciences relevance."""
        from src.skills.index import SkillIndex
        from unittest.mock import Mock, patch

        index = SkillIndex()

        mock_response = Mock()
        mock_response.data = []

        with patch.object(SupabaseClient, "get_client", return_value=Mock()):
            with patch.object(index._client.table("skills_index"), "select", return_value=mock_response):
                results = await index.search("clinical", life_sciences_relevant=True)

        assert isinstance(results, list)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_skill_index.py::TestSkillIndexSearch -v`
Expected: FAIL with "SkillIndex has no attribute 'search'" or similar

**Step 3: Implement the method**

Add to `SkillIndex` class in `backend/src/skills/index.py`:

```python
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
                # Use OR filter for name, description, or tags
                select_builder = select_builder.or_(
                    f"skill_name.ilike.%{query}%,description.ilike.%{query}%"
                )

            # Execute with limit
            response = select_builder.limit(limit).execute()

            # Convert to entries
            return [self._db_row_to_entry(row) for row in response.data]

        except Exception as e:
            logger.error(f"Error searching skills: {e}")
            return []
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_skill_index.py::TestSkillIndexSearch -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/skills/index.py backend/tests/test_skill_index.py
git commit -m "feat(skills): add search method with filters and tests"
```

---

## Task 8: Implement SkillIndex.get_summaries Method

**Files:**
- Modify: `backend/src/skills/index.py`
- Modify: `backend/tests/test_skill_index.py`

**Step 1: Write the failing test first**

Add to `backend/tests/test_skill_index.py`:

```python
class TestSkillIndexGetSummaries:
    """Tests for SkillIndex.get_summaries method."""

    @pytest.mark.asyncio
    async def test_get_summaries_returns_compact_summaries(self) -> None:
        """Test get_summaries returns compact ~20-word summaries."""
        from src.skills.index import SkillIndex
        from unittest.mock import Mock, patch

        index = SkillIndex()

        mock_data = [
            {
                "id": "1",
                "skill_path": "anthropics/skills/pdf",
                "skill_name": "PDF Parser",
                "description": "Extract text and structured data from PDF documents with OCR support for scanned files",
                "full_content": None,
                "content_hash": None,
                "author": "anthropic",
                "version": "1.0",
                "tags": ["pdf", "parser", "ocr"],
                "trust_level": "verified",
                "life_sciences_relevant": False,
                "declared_permissions": [],
                "summary_verbosity": "standard",
                "last_synced": None,
                "created_at": "2024-01-01T00:00:00+00:00",
                "updated_at": "2024-01-01T00:00:00+00:00",
            },
            {
                "id": "2",
                "skill_path": "test/clinical",
                "skill_name": "Clinical Trial Analyzer",
                "description": "Analyze clinical trial data from ClinicalTrials.gov and extract endpoints, phases, and eligibility criteria",
                "full_content": None,
                "content_hash": None,
                "author": "test",
                "version": "1.0",
                "tags": ["clinical", "trials", "fda"],
                "trust_level": "community",
                "life_sciences_relevant": True,
                "declared_permissions": ["network_read"],
                "summary_verbosity": "standard",
                "last_synced": None,
                "created_at": "2024-01-01T00:00:00+00:00",
                "updated_at": "2024-01-01T00:00:00+00:00",
            },
        ]
        mock_response = Mock()
        mock_response.data = mock_data

        skill_ids = ["1", "2"]

        with patch.object(SupabaseClient, "get_client", return_value=Mock()):
            with patch.object(index._client.table("skills_index"), "select", return_value=mock_response):
                summaries = await index.get_summaries(skill_ids)

        assert len(summaries) == 2
        # Each summary should be compact (~20 words max)
        for summary in summaries:
            word_count = len(summary.split())
            assert word_count <= 25, f"Summary too long: {word_count} words - {summary}"

    @pytest.mark.asyncio
    async def test_get_summaries_handles_empty_list(self) -> None:
        """Test get_summaries returns empty dict for empty input."""
        from src.skills.index import SkillIndex

        index = SkillIndex()
        summaries = await index.get_summaries([])

        assert summaries == {}

    @pytest.mark.asyncio
    async def test_get_summaries_handles_not_found_ids(self) -> None:
        """Test get_summaries skips IDs that don't exist."""
        from src.skills.index import SkillIndex
        from unittest.mock import Mock, patch

        index = SkillIndex()

        mock_response = Mock()
        mock_response.data = []

        with patch.object(SupabaseClient, "get_client", return_value=Mock()):
            with patch.object(index._client.table("skills_index"), "select", return_value=mock_response):
                summaries = await index.get_summaries(["999"])

        assert summaries == {}
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_skill_index.py::TestSkillIndexGetSummaries -v`
Expected: FAIL with "SkillIndex has no attribute 'get_summaries'" or similar

**Step 3: Implement the method**

Add to `SkillIndex` class in `backend/src/skills/index.py`:

```python
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
            response = (
                self._client.table("skills_index")
                .select("*")
                .in_("id", skill_ids)
                .execute()
            )

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
            desc_words = entry.description.split()[:15]
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
        if len(words) > 25:
            combined = " ".join(words[:25])

        return combined
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_skill_index.py::TestSkillIndexGetSummaries -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/skills/index.py backend/tests/test_skill_index.py
git commit -m "feat(skills): add get_summaries method for compact summaries with tests"
```

---

## Task 9: Implement SkillIndex.refresh_if_stale Method

**Files:**
- Modify: `backend/src/skills/index.py`
- Modify: `backend/tests/test_skill_index.py`

**Step 1: Write the failing test first**

Add to `backend/tests/test_skill_index.py`:

```python
class TestSkillIndexRefreshIfStale:
    """Tests for SkillIndex.refresh_if_stale method."""

    @pytest.mark.asyncio
    async def test_refresh_if_stale_returns_false_when_fresh(self) -> None:
        """Test refresh_if_stale returns False when data is fresh."""
        from src.skills.index import SkillIndex
        from unittest.mock import Mock, patch, AsyncMock
        from datetime import datetime, timezone

        index = SkillIndex()

        # Mock recent sync (1 hour ago)
        recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
        mock_response = Mock()
        mock_response.data = [{
            "last_synced": recent_time.isoformat(),
            "count": 1,
        }]

        with patch.object(SupabaseClient, "get_client", return_value=Mock()):
            with patch.object(index._client.table("skills_index"), "select", return_value=mock_response):
                result = await index.refresh_if_stale(max_age_hours=24)

        assert result is False

    @pytest.mark.asyncio
    async def test_refresh_if_stale_returns_true_when_stale(self) -> None:
        """Test refresh_if_stale returns True and triggers sync when stale."""
        from src.skills.index import SkillIndex
        from unittest.mock import Mock, patch, AsyncMock
        from datetime import datetime, timezone

        index = SkillIndex()

        # Mock stale sync (48 hours ago)
        stale_time = datetime.now(timezone.utc) - timedelta(hours=48)
        mock_response = Mock()
        mock_response.data = [{
            "last_synced": stale_time.isoformat(),
            "count": 1,
        }]

        with patch.object(SupabaseClient, "get_client", return_value=Mock()):
            with patch.object(index._client.table("skills_index"), "select", return_value=mock_response):
                with patch.object(index, "sync_from_skills_sh", new_callable=AsyncMock, return_value=10):
                    result = await index.refresh_if_stale(max_age_hours=24)

        assert result is True

    @pytest.mark.asyncio
    async def test_refresh_if_stale_syncs_when_no_previous_sync(self) -> None:
        """Test refresh_if_stale syncs when there's no previous sync."""
        from src.skills.index import SkillIndex
        from unittest.mock import Mock, patch, AsyncMock

        index = SkillIndex()

        # Mock no previous sync (empty result)
        mock_response = Mock()
        mock_response.data = []

        with patch.object(SupabaseClient, "get_client", return_value=Mock()):
            with patch.object(index._client.table("skills_index"), "select", return_value=mock_response):
                with patch.object(index, "sync_from_skills_sh", new_callable=AsyncMock, return_value=5):
                    result = await index.refresh_if_stale()

        assert result is True

    @pytest.mark.asyncio
    async def test_refresh_if_stale_respects_custom_max_age(self) -> None:
        """Test refresh_if_stale respects custom max_age_hours parameter."""
        from src.skills.index import SkillIndex
        from unittest.mock import Mock, patch, AsyncMock
        from datetime import datetime, timezone

        index = SkillIndex()

        # Mock sync 2 hours ago
        sync_time = datetime.now(timezone.utc) - timedelta(hours=2)
        mock_response = Mock()
        mock_response.data = [{
            "last_synced": sync_time.isoformat(),
            "count": 1,
        }]

        with patch.object(SupabaseClient, "get_client", return_value=Mock()):
            with patch.object(index._client.table("skills_index"), "select", return_value=mock_response):
                with patch.object(index, "sync_from_skills_sh", new_callable=AsyncMock, return_value=10):
                    # With max_age_hours=1, 2 hours should be stale
                    result = await index.refresh_if_stale(max_age_hours=1)

        assert result is True
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_skill_index.py::TestSkillIndexRefreshIfStale -v`
Expected: FAIL with "SkillIndex has no attribute 'refresh_if_stale'" or similar

**Step 3: Implement the method**

Add to `SkillIndex` class in `backend/src/skills/index.py`:

```python
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

            now = datetime.now()

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
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_skill_index.py::TestSkillIndexRefreshIfStale -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/skills/index.py backend/tests/test_skill_index.py
git commit -m "feat(skills): add refresh_if_stale method with staleness detection"
```

---

## Task 10: Implement SkillIndex.sync_from_skills_sh Method

**Files:**
- Modify: `backend/src/skills/index.py`
- Modify: `backend/tests/test_skill_index.py`

**Step 1: Write the failing test first**

Add to `backend/tests/test_skill_index.py`:

```python
class TestSkillIndexSyncFromSkillsSh:
    """Tests for SkillIndex.sync_from_skills_sh method."""

    @pytest.mark.asyncio
    async def test_sync_from_skills_sh_fetches_and_stores_skills(self) -> None:
        """Test sync_from_skills_sh fetches from API and stores in database."""
        from src.skills.index import SkillIndex
        from unittest.mock import Mock, patch, AsyncMock
        import httpx

        index = SkillIndex()

        # Mock HTTP response from skills.sh
        mock_http_response = Mock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = {
            "skills": [
                {
                    "path": "test/skill1",
                    "name": "Test Skill 1",
                    "description": "A test skill",
                    "content": "# Test Skill 1\nFull content",
                    "author": "test",
                    "version": "1.0",
                    "tags": ["test"],
                },
                {
                    "path": "test/skill2",
                    "name": "Test Skill 2",
                    "description": "Another test skill",
                    "content": "# Test Skill 2\nContent",
                    "author": "test",
                    "version": "1.0",
                    "tags": ["test"],
                },
            ]
        }

        # Mock Supabase upsert
        mock_upsert_response = Mock()
        mock_upsert_response.data = [{"id": "1"}]

        with patch.object(httpx.AsyncClient, "get", return_value=mock_http_response):
            with patch.object(SupabaseClient, "get_client", return_value=Mock()):
                with patch.object(
                    index._client.table("skills_index"),
                    "upsert",
                    return_value=mock_upsert_response,
                ):
                    count = await index.sync_from_skills_sh()

        assert count == 2

    @pytest.mark.asyncio
    async def test_sync_handles_http_errors_gracefully(self) -> None:
        """Test sync handles HTTP errors without crashing."""
        from src.skills.index import SkillIndex
        from unittest.mock import Mock, patch
        import httpx

        index = SkillIndex()

        # Mock HTTP error
        mock_http_response = Mock()
        mock_http_response.status_code = 404
        mock_http_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Not found", request=Mock(), response=mock_http_response
        )

        with patch.object(httpx.AsyncClient, "get", return_value=mock_http_response):
            count = await index.sync_from_skills_sh()

        assert count == 0

    @pytest.mark.asyncio
    async def test_sync_calculates_content_hash(self) -> None:
        """Test sync calculates SHA256 hash of skill content."""
        from src.skills.index import SkillIndex
        from unittest.mock import Mock, patch, call
        import httpx

        index = SkillIndex()

        mock_http_response = Mock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = {
            "skills": [
                {
                    "path": "test/skill",
                    "name": "Test",
                    "description": "Test",
                    "content": "test content",
                    "author": "test",
                    "version": "1.0",
                    "tags": [],
                }
            ]
        }

        mock_upsert_response = Mock()
        mock_upsert_response.data = []

        with patch.object(httpx.AsyncClient, "get", return_value=mock_http_response):
            with patch.object(SupabaseClient, "get_client", return_value=Mock()):
                with patch.object(
                    index._client.table("skills_index"),
                    "upsert",
                    return_value=mock_upsert_response,
                ) as mock_upsert:
                    await index.sync_from_skills_sh()

                    # Verify upsert was called with hash
                    call_args = mock_upsert.call_args
                    if call_args:
                        data = call_args[1].get("data") if len(call_args) > 1 else None
                        if data and len(data) > 0:
                            assert "content_hash" in data[0]

    @pytest.mark.asyncio
    async def test_sync_determines_trust_level_from_path(self) -> None:
        """Test sync assigns correct trust level based on skill path."""
        from src.skills.index import SkillIndex
        from unittest.mock import Mock, patch, call
        import httpx

        index = SkillIndex()

        mock_http_response = Mock()
        mock_http_response.status_code = 200
        mock_http_response.json.return_value = {
            "skills": [
                {
                    "path": "anthropics/skills/pdf",
                    "name": "PDF",
                    "description": "PDF parser",
                    "content": "# PDF",
                    "author": "anthropic",
                    "version": "1.0",
                    "tags": ["pdf"],
                }
            ]
        }

        mock_upsert_response = Mock()
        mock_upsert_response.data = []

        with patch.object(httpx.AsyncClient, "get", return_value=mock_http_response):
            with patch.object(SupabaseClient, "get_client", return_value=Mock()):
                with patch.object(
                    index._client.table("skills_index"),
                    "upsert",
                    return_value=mock_upsert_response,
                ) as mock_upsert:
                    await index.sync_from_skills_sh()

                    # Verify trust level is VERIFIED for anthropics/skills
                    call_args = mock_upsert.call_args
                    if call_args:
                        data = call_args[1].get("data") if len(call_args) > 1 else None
                        if data and len(data) > 0:
                            assert data[0].get("trust_level") == "verified"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_skill_index.py::TestSkillIndexSyncFromSkillsSh -v`
Expected: FAIL with "SkillIndex has no attribute 'sync_from_skills_sh'" or similar

**Step 3: Implement the method**

First, add the httpx client property to the `SkillIndex` class (in `__init__` or as property):

```python
    @property
    def _http(self) -> httpx.AsyncClient:
        """Lazy initialization of HTTP client for skills.sh API."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                timeout=30.0,
                headers={"Accept": "application/json"},
            )
        return self._http_client
```

Then add the sync method:

```python
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
            # TODO: Configure the actual skills.sh API URL
            # For now, this is a placeholder implementation
            # In production, this would call: await self._http.get(SKILLS_SH_API_URL)

            # Placeholder: Simulate API response structure
            # When implementing, replace with actual API call:
            # response = await self._http.get("https://api.skills.sh/v1/skills")
            # response.raise_for_status()
            # skills_data = response.json().get("skills", [])

            skills_data = []  # Placeholder - will be populated from actual API

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
            "clinical", "medical", "healthcare", "pharma", "biotech",
            "fda", "clinical-trials", "life-sciences", "lifesciences",
            "pubmed", "research", "bio", "health", "drug", "medicine"
        }
        if any(tag.lower() in ls_tags for tag in tags):
            return True

        # Check description
        description = skill_data.get("description", "").lower()
        ls_keywords = {
            "clinical trial", "fda", "pharmaceutical", "medical",
            "life science", "healthcare", "biotechnology", "pubmed",
            "drug development", "regulatory", "patient", "diagnosis"
        }
        if any(keyword in description for keyword in ls_keywords):
            return True

        return False
```

Also add the async `close` method:

```python
    async def close(self) -> None:
        """Close the HTTP client."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_skill_index.py::TestSkillIndexSyncFromSkillsSh -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/skills/index.py backend/tests/test_skill_index.py
git commit -m "feat(skills): add sync_from_skills_sh method with httpx client"
```

---

## Task 11: Update Security Module Exports

**Files:**
- Modify: `backend/src/security/__init__.py`

**Step 1: Add SkillTrustLevel to security module exports**

Check current exports and add `SkillTrustLevel` if not present:

```python
"""Security module for ARIA.

Exports data classification, sanitization, sandbox, trust levels, and audit.
"""

from src.security.data_classification import DataClass, ClassifiedData, DataClassifier
from src.security.sanitization import DataSanitizer
from src.security.sandbox import Sandbox
from src.security.trust_levels import SkillTrustLevel, TRUST_DATA_ACCESS, determine_trust_level
from src.security.audit import AuditLogger

__all__ = [
    # Data classification
    "DataClass",
    "ClassifiedData",
    "DataClassifier",
    # Sanitization
    "DataSanitizer",
    # Sandbox
    "Sandbox",
    # Trust levels
    "SkillTrustLevel",
    "TRUST_DATA_ACCESS",
    "determine_trust_level",
    # Audit
    "AuditLogger",
]
```

**Step 2: Verify exports work**

Run: `cd backend && python -c "from src.security import SkillTrustLevel; print('Success:', SkillTrustLevel.VERIFIED)"`
Expected: No errors, "Success: verified" printed

**Step 3: Commit**

```bash
git add backend/src/security/__init__.py
git commit -m "refactor(security): export SkillTrustLevel from security module"
```

---

## Task 12: Run All Tests and Verify Module Structure

**Files:**
- Test: `backend/tests/test_skill_index.py`

**Step 1: Run all skill index tests**

Run: `cd backend && pytest tests/test_skill_index.py -v`
Expected: All tests pass

**Step 2: Verify module can be imported from package root**

Run: `cd backend && python -c "from src.skills import SkillIndex, SkillIndexEntry, TIER_1_CORE_SKILLS; print('All exports successful')"`
Expected: No errors, "All exports successful" printed

**Step 3: Run mypy type checking**

Run: `cd backend && mypy src/skills/`
Expected: No errors

**Step 4: Run ruff formatting and linting**

Run: `cd backend && ruff format src/skills/ && ruff check src/skills/`
Expected: No errors

**Step 5: Commit**

```bash
git add backend/src/skills/ backend/tests/test_skill_index.py
git commit -m "test(skills): verify all tests pass and module structure is correct"
```

---

## Task 13: Add Configuration for Skills Service

**Files:**
- Modify: `backend/src/core/config.py`

**Step 1: Add skills configuration to Settings class**

Add to the `Settings` class in `backend/src/core/config.py` (after Composio section):

```python
    # Skills.sh Integration Configuration
    SKILLS_SH_API_URL: str = "https://api.skills.sh/v1"
    SKILLS_SH_GITHUB_URL: str = "https://raw.githubusercontent.com/skills-sh/skills/main"
    SKILLS_SYNC_INTERVAL_HOURS: int = 24
    SKILLS_MAX_CONTEXT_SUMMARIES: int = 50
```

**Step 2: Verify configuration loads**

Run: `cd backend && python -c "from src.core.config import settings; print('Skills API:', settings.SKILLS_SH_API_URL)"`
Expected: Prints the configured API URL

**Step 3: Commit**

```bash
git add backend/src/core/config.py
git commit -m "feat(skills): add skills.sh configuration to Settings"
```

---

## Task 14: Update SkillIndex to Use Configuration

**Files:**
- Modify: `backend/src/skills/index.py`

**Step 1: Import settings and use configured values**

Update imports in `backend/src/skills/index.py`:

```python
from src.core.config import settings
```

Update `sync_from_skills_sh` to use the configured API URL:

```python
    async def sync_from_skills_sh(self) -> int:
        """Sync skills from skills.sh API/GitHub to local database."""
        skills_synced = 0
        now = datetime.now()

        try:
            # Fetch skills from configured API URL
            api_url = f"{settings.SKILLS_SH_API_URL}/skills"
            response = await self._http.get(api_url)
            response.raise_for_status()

            skills_data = response.json().get("skills", [])
            # ... rest of method unchanged
```

**Step 2: Verify configuration is used**

Run: `cd backend && python -c "from src.skills.index import SkillIndex; from src.core.config import settings; print('API URL:', settings.SKILLS_SH_API_URL)"`
Expected: Prints configured API URL

**Step 3: Commit**

```bash
git add backend/src/skills/index.py
git commit -m "refactor(skills): use configured API URL from settings"
```

---

## Task 15: Final Integration Tests

**Files:**
- Modify: `backend/tests/test_skill_index.py`

**Step 1: Add integration test class**

Add to `backend/tests/test_skill_index.py`:

```python
class TestSkillIndexIntegration:
    """Integration tests for SkillIndex with real database behavior."""

    @pytest.mark.asyncio
    async def test_full_workflow_search_to_summary(self) -> None:
        """Test full workflow: search skill, get details, generate summary."""
        from src.skills.index import SkillIndex
        from unittest.mock import Mock, patch

        index = SkillIndex()

        # Mock search results
        search_data = [{
            "id": "test-id",
            "skill_path": "anthropics/skills/pdf",
            "skill_name": "PDF Parser",
            "description": "Extract text from PDF",
            "full_content": None,
            "content_hash": None,
            "author": "anthropic",
            "version": "1.0",
            "tags": ["pdf"],
            "trust_level": "verified",
            "life_sciences_relevant": False,
            "declared_permissions": [],
            "summary_verbosity": "standard",
            "last_synced": None,
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }]
        search_response = Mock()
        search_response.data = search_data

        with patch.object(SupabaseClient, "get_client", return_value=Mock()):
            with patch.object(index._client.table("skills_index"), "select", return_value=search_response):
                # Step 1: Search
                results = await index.search("pdf")
                assert len(results) == 1

                # Step 2: Get summary
                summaries = await index.get_summaries([results[0].id])
                assert results[0].id in summaries
                assert len(summaries[results[0].id].split()) <= 25

    @pytest.mark.asyncio
    async def test_tier_1_skills_are_always_accessible(self) -> None:
        """Test TIER_1_CORE_SKILLS can be queried."""
        from src.skills.index import TIER_1_CORE_SKILLS

        assert len(TIER_1_CORE_SKILLS) > 0
        assert all(s.startswith("aria:") for s in TIER_1_CORE_SKILLS)

    @pytest.mark.asyncio
    async def test_trust_levels_match_security_module(self) -> None:
        """Test trust level consistency with security module."""
        from src.security import SkillTrustLevel
        from src.skills.index import SkillIndex
        from unittest.mock import Mock, patch

        index = SkillIndex()

        # Test each trust level value
        mock_data = [{
            "id": "1",
            "skill_path": "test/skill",
            "skill_name": "Test",
            "description": None,
            "full_content": None,
            "content_hash": None,
            "author": None,
            "version": None,
            "tags": [],
            "trust_level": "verified",
            "life_sciences_relevant": False,
            "declared_permissions": [],
            "summary_verbosity": "standard",
            "last_synced": None,
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
        }]
        mock_response = Mock()
        mock_response.data = mock_data

        with patch.object(SupabaseClient, "get_client", return_value=Mock()):
            with patch.object(index._client.table("skills_index"), "select", return_value=mock_response):
                results = await index.search("test")
                assert len(results) == 1
                assert isinstance(results[0].trust_level, SkillTrustLevel)
```

**Step 2: Run integration tests**

Run: `cd backend && pytest tests/test_skill_index.py::TestSkillIndexIntegration -v`
Expected: All integration tests pass

**Step 3: Run all tests one final time**

Run: `cd backend && pytest tests/test_skill_index.py -v`
Expected: All tests pass

**Step 4: Final commit**

```bash
git add backend/tests/test_skill_index.py
git commit -m "test(skills): add integration tests for full workflow"
```

---

## Summary

This implementation plan creates a complete skill index service for ARIA that:

1. **Stores skills in Supabase** with proper RLS policies (all authenticated users can read)
2. **Discovers skills from skills.sh** via HTTP API with content hashing
3. **Enables fast search** by name, description, tags with trust level filtering
4. **Generates compact summaries** for context management (~20 words max)
5. **Supports three-tier awareness**: CORE (always-loaded), life sciences relevant, and discovery
6. **Integrates with security module** using existing `SkillTrustLevel` enum

The service is fully tested with unit and integration tests, follows existing codebase patterns (httpx for HTTP, Supabase client patterns, Pydantic/dataclass patterns), and is ready for integration with the skill orchestrator and executor components.
