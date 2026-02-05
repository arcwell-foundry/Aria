"""Tests for skill index service."""

from unittest.mock import MagicMock, Mock, patch, AsyncMock

import pytest
from datetime import datetime, timezone, timedelta

from src.security.trust_levels import SkillTrustLevel
from src.skills.index import (
    SkillIndex,
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


class TestSkillIndexDbConversion:
    """Tests for SkillIndex database conversion methods."""

    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_db_row_to_entry_converts_valid_row(self, mock_supabase: MagicMock) -> None:
        """Test _db_row_to_entry converts database row to SkillIndexEntry."""
        mock_supabase.get_client.return_value = MagicMock()
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

    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_db_row_to_entry_handles_none_values(self, mock_supabase: MagicMock) -> None:
        """Test _db_row_to_entry handles optional None values."""
        mock_supabase.get_client.return_value = MagicMock()
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


class TestSkillIndexGetSkill:
    """Tests for SkillIndex.get_skill method."""

    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_get_skill_by_id_returns_entry(self, mock_supabase: MagicMock) -> None:
        """Test get_skill returns SkillIndexEntry for valid ID."""
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
        index = SkillIndex()

        # Create the mock query chain: table().select().eq().single().execute()
        # .single() returns a single row (not a list)
        mock_query_builder = MagicMock()
        mock_query_builder.eq.return_value = mock_query_builder
        mock_query_builder.single.return_value = mock_query_builder
        mock_query_builder.execute.return_value = MagicMock(data={
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
        })

        mock_table = MagicMock()
        mock_table.select.return_value = mock_query_builder

        with patch.object(index._client, "table", return_value=mock_table):
            entry = await index.get_skill("123")

        assert entry is not None
        assert entry.skill_path == "test/skill"
        assert entry.skill_name == "Test Skill"

    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_get_skill_returns_none_for_not_found(self, mock_supabase: MagicMock) -> None:
        """Test get_skill returns None when skill doesn't exist."""
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
        index = SkillIndex()

        # Mock Supabase to raise exception for not found
        mock_query_builder = MagicMock()
        mock_query_builder.eq.side_effect = Exception("Skill not found")

        mock_table = MagicMock()
        mock_table.select.return_value = mock_query_builder

        with patch.object(index._client, "table", return_value=mock_table):
            entry = await index.get_skill("123")

        assert entry is None


class TestSkillIndexSearch:
    """Tests for SkillIndex.search method."""

    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_search_returns_matching_skills(self, mock_supabase: MagicMock) -> None:
        """Test search returns skills matching query."""
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
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

        mock_query = MagicMock()
        mock_execute_result = MagicMock()
        mock_execute_result.data = mock_data
        mock_query.execute.return_value = mock_execute_result
        mock_query.or_.return_value = mock_query
        mock_query.eq.return_value = mock_query
        mock_query.limit.return_value = mock_query

        mock_table = MagicMock()
        mock_table.select.return_value = mock_query

        with patch.object(index._client, "table", return_value=mock_table):
            results = await index.search("pdf")

        assert len(results) == 1
        assert results[0].skill_name == "PDF Parser"

    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_search_with_empty_query_returns_all(self, mock_supabase: MagicMock) -> None:
        """Test search with empty query returns all skills."""
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
        index = SkillIndex()

        mock_query = MagicMock()
        mock_execute_result = MagicMock()
        mock_execute_result.data = []
        mock_query.execute.return_value = mock_execute_result
        mock_query.eq.return_value = mock_query
        mock_query.limit.return_value = mock_query

        mock_table = MagicMock()
        mock_table.select.return_value = mock_query

        with patch.object(index._client, "table", return_value=mock_table):
            results = await index.search("")

        assert isinstance(results, list)

    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_search_filters_by_trust_level(self, mock_supabase: MagicMock) -> None:
        """Test search can filter by trust level."""
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
        index = SkillIndex()

        mock_query = MagicMock()
        mock_execute_result = MagicMock()
        mock_execute_result.data = []
        mock_query.execute.return_value = mock_execute_result
        mock_query.eq.return_value = mock_query
        mock_query.or_.return_value = mock_query
        mock_query.limit.return_value = mock_query

        mock_table = MagicMock()
        mock_table.select.return_value = mock_query

        with patch.object(index._client, "table", return_value=mock_table):
            results = await index.search("pdf", trust_level=SkillTrustLevel.VERIFIED)

        assert isinstance(results, list)

    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_search_filters_by_life_sciences(self, mock_supabase: MagicMock) -> None:
        """Test search can filter by life sciences relevance."""
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
        index = SkillIndex()

        mock_query = MagicMock()
        mock_execute_result = MagicMock()
        mock_execute_result.data = []
        mock_query.execute.return_value = mock_execute_result
        mock_query.eq.return_value = mock_query
        mock_query.or_.return_value = mock_query
        mock_query.limit.return_value = mock_query

        mock_table = MagicMock()
        mock_table.select.return_value = mock_query

        with patch.object(index._client, "table", return_value=mock_table):
            results = await index.search("clinical", life_sciences_relevant=True)

        assert isinstance(results, list)


class TestSkillIndexGetSummaries:
    """Tests for SkillIndex.get_summaries method."""

    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_get_summaries_returns_compact_summaries(self, mock_supabase: MagicMock) -> None:
        """Test get_summaries returns compact ~20-word summaries."""
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
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

        mock_query = MagicMock()
        mock_execute_result = MagicMock()
        mock_execute_result.data = mock_data
        mock_query.execute.return_value = mock_execute_result
        mock_query.in_.return_value = mock_query

        mock_table = MagicMock()
        mock_table.select.return_value = mock_query

        skill_ids = ["1", "2"]

        with patch.object(index._client, "table", return_value=mock_table):
            summaries = await index.get_summaries(skill_ids)

        assert len(summaries) == 2
        # Each summary should be compact (~20 words max)
        for summary in summaries.values():
            word_count = len(summary.split())
            assert word_count <= 25, f"Summary too long: {word_count} words - {summary}"

    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_get_summaries_handles_empty_list(self, mock_supabase: MagicMock) -> None:
        """Test get_summaries returns empty dict for empty input."""
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
        index = SkillIndex()
        summaries = await index.get_summaries([])

        assert summaries == {}

    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_get_summaries_handles_not_found_ids(self, mock_supabase: MagicMock) -> None:
        """Test get_summaries skips IDs that don't exist."""
        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
        index = SkillIndex()

        mock_query = MagicMock()
        mock_execute_result = MagicMock()
        mock_execute_result.data = []
        mock_query.execute.return_value = mock_execute_result
        mock_query.in_.return_value = mock_query

        mock_table = MagicMock()
        mock_table.select.return_value = mock_query

        with patch.object(index._client, "table", return_value=mock_table):
            summaries = await index.get_summaries(["999"])

        assert summaries == {}


class TestSkillIndexRefreshIfStale:
    """Tests for SkillIndex.refresh_if_stale method."""

    @patch("src.skills.index.SupabaseClient.get_client")
    @pytest.mark.asyncio
    async def test_refresh_if_stale_returns_false_when_fresh(self, mock_get_client: MagicMock) -> None:
        """Test refresh_if_stale returns False when data is fresh."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        index = SkillIndex()

        # Mock recent sync (1 hour ago)
        recent_time = datetime.now(timezone.utc) - timedelta(hours=1)
        mock_response = MagicMock()
        mock_response.data = [{
            "last_synced": recent_time.isoformat(),
            "count": 1,
        }]

        mock_query = MagicMock()
        mock_query.execute.return_value = mock_response
        mock_query.order.return_value = mock_query
        mock_query.limit.return_value = mock_query

        mock_table = MagicMock()
        mock_table.select.return_value = mock_query

        with patch.object(index._client, "table", return_value=mock_table):
            with patch.object(index, "sync_from_skills_sh", new_callable=AsyncMock, return_value=10):
                result = await index.refresh_if_stale(max_age_hours=24)

        assert result is False

    @patch("src.skills.index.SupabaseClient.get_client")
    @pytest.mark.asyncio
    async def test_refresh_if_stale_returns_true_when_stale(self, mock_get_client: MagicMock) -> None:
        """Test refresh_if_stale returns True and triggers sync when stale."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        index = SkillIndex()

        # Mock stale sync (48 hours ago)
        stale_time = datetime.now(timezone.utc) - timedelta(hours=48)
        mock_response = MagicMock()
        mock_response.data = [{
            "last_synced": stale_time.isoformat(),
            "count": 1,
        }]

        mock_query = MagicMock()
        mock_query.execute.return_value = mock_response
        mock_query.order.return_value = mock_query
        mock_query.limit.return_value = mock_query

        mock_table = MagicMock()
        mock_table.select.return_value = mock_query

        with patch.object(index._client, "table", return_value=mock_table):
            with patch.object(index, "sync_from_skills_sh", new_callable=AsyncMock, return_value=10) as mock_sync:
                result = await index.refresh_if_stale(max_age_hours=24)

        assert result is True
        mock_sync.assert_called_once()

    @patch("src.skills.index.SupabaseClient.get_client")
    @pytest.mark.asyncio
    async def test_refresh_if_stale_syncs_when_no_previous_sync(self, mock_get_client: MagicMock) -> None:
        """Test refresh_if_stale syncs when there's no previous sync."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        index = SkillIndex()

        # Mock no previous sync (empty result)
        mock_response = MagicMock()
        mock_response.data = []

        mock_query = MagicMock()
        mock_query.execute.return_value = mock_response
        mock_query.order.return_value = mock_query
        mock_query.limit.return_value = mock_query

        mock_table = MagicMock()
        mock_table.select.return_value = mock_query

        with patch.object(index._client, "table", return_value=mock_table):
            with patch.object(index, "sync_from_skills_sh", new_callable=AsyncMock, return_value=5) as mock_sync:
                result = await index.refresh_if_stale()

        assert result is True
        mock_sync.assert_called_once()

    @patch("src.skills.index.SupabaseClient.get_client")
    @pytest.mark.asyncio
    async def test_refresh_if_stale_respects_custom_max_age(self, mock_get_client: MagicMock) -> None:
        """Test refresh_if_stale respects custom max_age_hours parameter."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        index = SkillIndex()

        # Mock sync 2 hours ago
        sync_time = datetime.now(timezone.utc) - timedelta(hours=2)
        mock_response = MagicMock()
        mock_response.data = [{
            "last_synced": sync_time.isoformat(),
            "count": 1,
        }]

        mock_query = MagicMock()
        mock_query.execute.return_value = mock_response
        mock_query.order.return_value = mock_query
        mock_query.limit.return_value = mock_query

        mock_table = MagicMock()
        mock_table.select.return_value = mock_query

        with patch.object(index._client, "table", return_value=mock_table):
            with patch.object(index, "sync_from_skills_sh", new_callable=AsyncMock, return_value=10) as mock_sync:
                # With max_age_hours=1, 2 hours should be stale
                result = await index.refresh_if_stale(max_age_hours=1)

        assert result is True
        mock_sync.assert_called_once()


class TestSkillIndexSyncFromSkillsSh:
    """Tests for SkillIndex.sync_from_skills_sh method."""

    @patch("src.skills.index.SupabaseClient.get_client")
    @pytest.mark.asyncio
    async def test_sync_handles_empty_skills_list(self, mock_get_client: MagicMock) -> None:
        """Test sync handles empty skills list gracefully."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        index = SkillIndex()

        # Test the placeholder implementation
        count = await index.sync_from_skills_sh()

        assert count == 0

    @patch("src.skills.index.SupabaseClient.get_client")
    @pytest.mark.asyncio
    async def test_http_property_creates_client(self, mock_get_client: MagicMock) -> None:
        """Test _http property creates and caches HTTP client."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        import httpx

        index = SkillIndex()

        # First call should create the client
        client1 = index._http
        assert client1 is not None
        assert isinstance(client1, httpx.AsyncClient)

        # Second call should return the same instance
        client2 = index._http
        assert client1 is client2

    @patch("src.skills.index.SupabaseClient.get_client")
    @pytest.mark.asyncio
    async def test_close_closes_http_client(self, mock_get_client: MagicMock) -> None:
        """Test close method properly closes HTTP client."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        index = SkillIndex()

        # Initialize the HTTP client
        _ = index._http
        assert index._http_client is not None

        # Close it
        await index.close()

        # Client should be None after closing
        assert index._http_client is None

    @patch("src.skills.index.SupabaseClient.get_client")
    @pytest.mark.asyncio
    async def test_close_when_no_client_is_safe(self, mock_get_client: MagicMock) -> None:
        """Test close doesn't error when no HTTP client exists."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        index = SkillIndex()

        # Should not raise an error
        await index.close()

        assert index._http_client is None


class TestSkillIndexIsLifeSciencesRelevant:
    """Tests for SkillIndex._is_life_sciences_relevant method."""

    @patch("src.skills.index.SupabaseClient.get_client")
    def test_relevant_tag_returns_true(self, mock_get_client: MagicMock) -> None:
        """Test _is_life_sciences_relevant returns True for life sciences tags."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        index = SkillIndex()

        skill_data = {
            "tags": ["clinical", "trial", "research"],
            "description": "A generic skill",
        }

        result = index._is_life_sciences_relevant(skill_data)
        assert result is True

    @patch("src.skills.index.SupabaseClient.get_client")
    def test_medical_tag_returns_true(self, mock_get_client: MagicMock) -> None:
        """Test _is_life_sciences_relevant returns True for medical tags."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        index = SkillIndex()

        skill_data = {
            "tags": ["medical", "healthcare"],
            "description": "A generic skill",
        }

        result = index._is_life_sciences_relevant(skill_data)
        assert result is True

    @patch("src.skills.index.SupabaseClient.get_client")
    def test_relevant_description_returns_true(self, mock_get_client: MagicMock) -> None:
        """Test _is_life_sciences_relevant returns True for relevant keywords in description."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        index = SkillIndex()

        skill_data = {
            "tags": ["generic"],
            "description": "Analyze clinical trial data from FDA submissions",
        }

        result = index._is_life_sciences_relevant(skill_data)
        assert result is True

    @patch("src.skills.index.SupabaseClient.get_client")
    def test_non_relevant_returns_false(self, mock_get_client: MagicMock) -> None:
        """Test _is_life_sciences_relevant returns False for non-relevant skills."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        index = SkillIndex()

        skill_data = {
            "tags": ["pdf", "parser", "document"],
            "description": "Parse PDF files and extract text",
        }

        result = index._is_life_sciences_relevant(skill_data)
        assert result is False

    @patch("src.skills.index.SupabaseClient.get_client")
    def test_case_insensitive_matching(self, mock_get_client: MagicMock) -> None:
        """Test _is_life_sciences_relevant is case-insensitive."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        index = SkillIndex()

        skill_data = {
            "tags": ["CLINICAL", "Pharma", "BioTech"],
            "description": "A skill",
        }

        result = index._is_life_sciences_relevant(skill_data)
        assert result is True

    @patch("src.skills.index.SupabaseClient.get_client")
    def test_empty_data_returns_false(self, mock_get_client: MagicMock) -> None:
        """Test _is_life_sciences_relevant returns False for empty data."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        index = SkillIndex()

        skill_data = {
            "tags": [],
            "description": "",
        }

        result = index._is_life_sciences_relevant(skill_data)
        assert result is False

    @patch("src.skills.index.SupabaseClient.get_client")
    def test_health_tag_matches(self, mock_get_client: MagicMock) -> None:
        """Test _is_life_sciences_relevant matches health-related tags."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        index = SkillIndex()

        skill_data = {
            "tags": ["health"],
            "description": "A generic skill",
        }

        result = index._is_life_sciences_relevant(skill_data)
        assert result is True

    @patch("src.skills.index.SupabaseClient.get_client")
    def test_drug_keyword_in_description(self, mock_get_client: MagicMock) -> None:
        """Test _is_life_sciences_relevant matches drug development keywords."""
        mock_client = MagicMock()
        mock_get_client.return_value = mock_client
        index = SkillIndex()

        skill_data = {
            "tags": ["generic"],
            "description": "Track drug development pipeline and regulatory submissions",
        }

        result = index._is_life_sciences_relevant(skill_data)
        assert result is True


class TestSkillIndexIntegration:
    """Integration tests for SkillIndex with real database behavior."""

    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_full_workflow_search_to_summary(self, mock_supabase: MagicMock) -> None:
        """Test full workflow: search skill, get details, generate summary."""
        from src.skills.index import SkillIndex
        from src.db.supabase import SupabaseClient

        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
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

        mock_query = MagicMock()
        mock_execute_result = MagicMock()
        mock_execute_result.data = search_data
        mock_query.execute.return_value = mock_execute_result
        mock_query.or_.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.in_.return_value = mock_query

        mock_table = MagicMock()
        mock_table.select.return_value = mock_query

        with patch.object(index._client, "table", return_value=mock_table):
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

    @patch("src.skills.index.SupabaseClient")
    @pytest.mark.asyncio
    async def test_trust_levels_match_security_module(self, mock_supabase: MagicMock) -> None:
        """Test trust level consistency with security module."""
        from src.security import SkillTrustLevel
        from src.skills.index import SkillIndex

        mock_client = MagicMock()
        mock_supabase.get_client.return_value = mock_client
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

        mock_query = MagicMock()
        mock_execute_result = MagicMock()
        mock_execute_result.data = mock_data
        mock_query.execute.return_value = mock_execute_result
        mock_query.or_.return_value = mock_query
        mock_query.limit.return_value = mock_query

        mock_table = MagicMock()
        mock_table.select.return_value = mock_query

        with patch.object(index._client, "table", return_value=mock_table):
            results = await index.search("test")
            assert len(results) == 1
            assert isinstance(results[0].trust_level, SkillTrustLevel)