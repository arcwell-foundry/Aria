"""Tests for Narrative Identity Engine (US-807)."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.companion.narrative import (
    MilestoneType,
    NarrativeIdentityEngine,
    NarrativeState,
    RelationshipMilestone,
)


@pytest.fixture
def mock_db():
    """Create a mock database client."""
    db = MagicMock()
    db.table = MagicMock(return_value=db)
    db.select = MagicMock(return_value=db)
    db.eq = MagicMock(return_value=db)
    db.single = MagicMock(return_value=db)
    db.order = MagicMock(return_value=db)
    db.limit = MagicMock(return_value=db)
    db.insert = MagicMock(return_value=db)
    db.update = MagicMock(return_value=db)
    db.execute = MagicMock()
    return db


@pytest.fixture
def mock_llm():
    """Create a mock LLM client."""
    llm = MagicMock()
    llm.generate_response = AsyncMock()
    return llm


@pytest.fixture
def engine(mock_db, mock_llm):
    """Create an engine with mocked dependencies."""
    return NarrativeIdentityEngine(
        db_client=mock_db,
        llm_client=mock_llm,
        memory_service=None,
    )


class TestMilestone:
    """Tests for RelationshipMilestone dataclass."""

    def test_milestone_creation(self):
        """Test creating a milestone."""
        now = datetime.now(UTC)
        milestone = RelationshipMilestone(
            id="test-id",
            type="first_deal",
            date=now,
            description="First deal closed",
            significance=0.8,
            related_entity_type="deal",
            related_entity_id="deal-123",
        )

        assert milestone.id == "test-id"
        assert milestone.type == "first_deal"
        assert milestone.description == "First deal closed"
        assert milestone.significance == 0.8

    def test_milestone_serialization(self):
        """Test milestone to_dict and from_dict."""
        now = datetime.now(UTC)
        original = RelationshipMilestone(
            id="test-id",
            type="deal_closed",
            date=now,
            description="Closed Lonza deal",
            significance=0.9,
            related_entity_type="deal",
            related_entity_id="deal-456",
            created_at=now,
        )

        data = original.to_dict()
        assert data["id"] == "test-id"
        assert data["type"] == "deal_closed"
        assert data["description"] == "Closed Lonza deal"

        restored = RelationshipMilestone.from_dict(data)
        assert restored.id == original.id
        assert restored.type == original.type
        assert restored.description == original.description
        assert restored.significance == original.significance


class TestNarrativeState:
    """Tests for NarrativeState dataclass."""

    def test_narrative_initialization(self):
        """Test creating a narrative state."""
        now = datetime.now(UTC)
        state = NarrativeState(
            user_id="user-123",
            relationship_start=now,
            total_interactions=10,
            trust_score=0.7,
        )

        assert state.user_id == "user-123"
        assert state.total_interactions == 10
        assert state.trust_score == 0.7

    def test_narrative_initialization_first_interaction(self):
        """Test narrative state for first-time user."""
        now = datetime.now(UTC)
        state = NarrativeState(
            user_id="new-user",
            relationship_start=now,
        )

        assert state.total_interactions == 0
        assert state.trust_score == 0.5
        assert state.shared_victories == []
        assert state.shared_challenges == []
        assert state.inside_references == []

    def test_narrative_serialization(self):
        """Test narrative state to_dict and from_dict."""
        now = datetime.now(UTC)
        original = NarrativeState(
            user_id="user-789",
            relationship_start=now,
            total_interactions=50,
            trust_score=0.85,
            shared_victories=[{"description": "Won major account"}],
            shared_challenges=[{"description": "Tough quarter"}],
            inside_references=["remember the Lonza presentation"],
            updated_at=now,
        )

        data = original.to_dict()
        assert data["user_id"] == "user-789"
        assert data["total_interactions"] == 50
        assert data["trust_score"] == 0.85

        restored = NarrativeState.from_dict(data)
        assert restored.user_id == original.user_id
        assert restored.total_interactions == original.total_interactions
        assert restored.trust_score == original.trust_score
        assert len(restored.shared_victories) == 1


class TestNarrativeEngine:
    """Tests for NarrativeIdentityEngine."""

    @pytest.mark.asyncio
    async def test_milestone_recording(self, engine, mock_db):
        """Test recording a milestone."""
        # Mock the narrative state fetch to return existing state
        mock_db.execute.side_effect = [
            # get_narrative_state query
            MagicMock(data=None),
            # _initialize_narrative insert
            MagicMock(data={"user_id": "user-1"}),
            # record_milestone insert
            MagicMock(data={"id": "milestone-1"}),
            # _update_trust_for_milestone update
            MagicMock(data={}),
        ]

        milestone = await engine.record_milestone(
            user_id="user-1",
            milestone_type=MilestoneType.DEAL_CLOSED.value,
            description="Closed major deal with Acme Corp",
            related_entity_type="deal",
            related_entity_id="deal-123",
            significance=0.9,
        )

        assert milestone.type == "deal_closed"
        assert milestone.description == "Closed major deal with Acme Corp"
        assert milestone.significance == 0.9

    @pytest.mark.asyncio
    async def test_milestone_updates_trust_score(self, engine, mock_db):
        """Test that recording certain milestones updates trust score."""
        # Mock the narrative state and updates
        mock_db.execute.side_effect = [
            # First get_narrative_state query
            MagicMock(
                data={
                    "user_id": "user-2",
                    "relationship_start": datetime.now(UTC).isoformat(),
                    "total_interactions": 10,
                    "trust_score": 0.5,
                    "shared_victories": [],
                    "shared_challenges": [],
                    "inside_references": [],
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ),
            # update_trust_score update
            MagicMock(data={}),
        ]

        # Call update_trust_score directly
        new_score = await engine.update_trust_score(
            user_id="user-2",
            event_type="pushback_accepted",
        )

        # Should increase by 0.05
        assert new_score == 0.55

    @pytest.mark.asyncio
    async def test_contextual_reference_relevant(self, engine, mock_db, mock_llm):
        """Test getting contextual references when relevant history exists."""
        mock_db.execute.side_effect = [
            # get_narrative_state
            MagicMock(
                data={
                    "user_id": "user-3",
                    "relationship_start": datetime.now(UTC).isoformat(),
                    "total_interactions": 20,
                    "trust_score": 0.6,
                    "shared_victories": [
                        {"description": "Won the Catalent account"}
                    ],
                    "shared_challenges": [
                        {"description": "Struggled with Lonza pricing"}
                    ],
                    "inside_references": ["remember Catalent"],
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ),
            # _get_recent_milestones
            MagicMock(data=[]),
        ]

        mock_llm.generate_response.return_value = '''
        {"relevant": ["Victory: Won the Catalent account"]}
        '''

        references = await engine.get_contextual_references(
            user_id="user-3",
            current_topic="preparing for Catalent meeting",
        )

        assert len(references) >= 1
        assert "Catalent" in references[0]

    @pytest.mark.asyncio
    async def test_contextual_reference_irrelevant_returns_empty(
        self, engine, mock_db, mock_llm
    ):
        """Test that irrelevant topics return empty references."""
        mock_db.execute.side_effect = [
            # get_narrative_state
            MagicMock(
                data={
                    "user_id": "user-4",
                    "relationship_start": datetime.now(UTC).isoformat(),
                    "total_interactions": 5,
                    "trust_score": 0.5,
                    "shared_victories": [
                        {"description": "Won fishing competition"}
                    ],
                    "shared_challenges": [],
                    "inside_references": [],
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ),
            # _get_recent_milestones
            MagicMock(data=[]),
        ]

        mock_llm.generate_response.return_value = '{"relevant": []}'

        references = await engine.get_contextual_references(
            user_id="user-4",
            current_topic="quarterly financial reports",
        )

        assert references == []

    @pytest.mark.asyncio
    async def test_contextual_reference_max_two(self, engine, mock_db, mock_llm):
        """Test that at most 2 references are returned."""
        mock_db.execute.side_effect = [
            # get_narrative_state
            MagicMock(
                data={
                    "user_id": "user-5",
                    "relationship_start": datetime.now(UTC).isoformat(),
                    "total_interactions": 50,
                    "trust_score": 0.8,
                    "shared_victories": [
                        {"description": "Deal 1"},
                        {"description": "Deal 2"},
                        {"description": "Deal 3"},
                    ],
                    "shared_challenges": [],
                    "inside_references": [],
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ),
            # _get_recent_milestones
            MagicMock(data=[]),
        ]

        mock_llm.generate_response.return_value = '''
        {"relevant": ["Victory: Deal 1", "Victory: Deal 2", "Victory: Deal 3"]}
        '''

        references = await engine.get_contextual_references(
            user_id="user-5",
            current_topic="sales strategy",
        )

        # Should cap at 2
        assert len(references) <= 2

    @pytest.mark.asyncio
    async def test_anniversary_detection(self, engine, mock_db):
        """Test detecting relationship anniversaries."""
        # Create a date exactly 1 year ago
        one_year_ago = datetime.now(UTC) - timedelta(days=365)

        mock_db.execute.side_effect = [
            # get_narrative_state
            MagicMock(
                data={
                    "user_id": "user-6",
                    "relationship_start": one_year_ago.isoformat(),
                    "total_interactions": 100,
                    "trust_score": 0.9,
                    "shared_victories": [],
                    "shared_challenges": [],
                    "inside_references": [],
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ),
            # milestone query
            MagicMock(data=[]),
        ]

        anniversaries = await engine.check_anniversaries("user-6")

        # Should detect the work anniversary
        assert len(anniversaries) >= 1
        assert anniversaries[0]["type"] == "work_anniversary"
        assert anniversaries[0]["years"] == 1

    @pytest.mark.asyncio
    async def test_anniversary_no_match(self, engine, mock_db):
        """Test no anniversary when dates don't align."""
        # Create a date that won't match today
        not_today = datetime(2025, 6, 15, tzinfo=UTC)

        mock_db.execute.side_effect = [
            # get_narrative_state
            MagicMock(
                data={
                    "user_id": "user-7",
                    "relationship_start": not_today.isoformat(),
                    "total_interactions": 50,
                    "trust_score": 0.7,
                    "shared_victories": [],
                    "shared_challenges": [],
                    "inside_references": [],
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ),
            # milestone query
            MagicMock(data=[]),
        ]

        anniversaries = await engine.check_anniversaries("user-7")

        # Should not detect any anniversary
        assert anniversaries == []

    @pytest.mark.asyncio
    async def test_trust_score_increases(self, engine, mock_db):
        """Test that trust score increases with positive events."""
        mock_db.execute.side_effect = [
            # get_narrative_state
            MagicMock(
                data={
                    "user_id": "user-8",
                    "relationship_start": datetime.now(UTC).isoformat(),
                    "total_interactions": 10,
                    "trust_score": 0.5,
                    "shared_victories": [],
                    "shared_challenges": [],
                    "inside_references": [],
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ),
            # update
            MagicMock(data={}),
        ]

        new_score = await engine.update_trust_score(
            user_id="user-8",
            event_type="goal_completed",
        )

        # Should increase by 0.03
        assert new_score == 0.53

    @pytest.mark.asyncio
    async def test_increment_interactions(self, engine, mock_db):
        """Test incrementing interaction count."""
        mock_db.execute.side_effect = [
            # get_narrative_state
            MagicMock(
                data={
                    "user_id": "user-9",
                    "relationship_start": datetime.now(UTC).isoformat(),
                    "total_interactions": 10,
                    "trust_score": 0.5,
                    "shared_victories": [],
                    "shared_challenges": [],
                    "inside_references": [],
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ),
            # update
            MagicMock(data={}),
        ]

        new_count = await engine.increment_interactions("user-9")

        assert new_count == 11
