"""Tests for social media models and LinkedIn capability."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestSocialModels:
    """Tests for social media Pydantic models."""

    def test_post_variation_creation(self) -> None:
        """Create a PostVariation with all fields."""
        from src.models.social import PostVariation, PostVariationType

        variation = PostVariation(
            variation_type=PostVariationType.INSIGHT,
            text="Exciting developments in oncology research.",
            hashtags=["#oncology", "#lifesciences"],
            voice_match_confidence=0.85,
        )
        assert variation.variation_type == PostVariationType.INSIGHT
        assert variation.text == "Exciting developments in oncology research."
        assert variation.hashtags == ["#oncology", "#lifesciences"]
        assert variation.voice_match_confidence == 0.85

    def test_post_variation_defaults(self) -> None:
        """Verify PostVariation defaults for optional fields."""
        from src.models.social import PostVariation, PostVariationType

        variation = PostVariation(
            variation_type=PostVariationType.EDUCATIONAL,
            text="Some text",
        )
        assert variation.hashtags == []
        assert variation.voice_match_confidence == 0.0

    def test_post_variation_confidence_bounds(self) -> None:
        """Verify voice_match_confidence is constrained to 0.0-1.0."""
        from src.models.social import PostVariation, PostVariationType

        with pytest.raises(ValidationError):
            PostVariation(
                variation_type=PostVariationType.INSIGHT,
                text="text",
                voice_match_confidence=1.5,
            )

        with pytest.raises(ValidationError):
            PostVariation(
                variation_type=PostVariationType.INSIGHT,
                text="text",
                voice_match_confidence=-0.1,
            )

    def test_draft_approve_request_defaults(self) -> None:
        """Verify DraftApproveRequest default selected_variation_index=0."""
        from src.models.social import DraftApproveRequest

        request = DraftApproveRequest()
        assert request.selected_variation_index == 0
        assert request.edited_text is None
        assert request.edited_hashtags is None

    def test_draft_approve_request_with_edits(self) -> None:
        """Verify DraftApproveRequest accepts edited content."""
        from src.models.social import DraftApproveRequest

        request = DraftApproveRequest(
            selected_variation_index=2,
            edited_text="My edited post text.",
            edited_hashtags=["#edited"],
        )
        assert request.selected_variation_index == 2
        assert request.edited_text == "My edited post text."
        assert request.edited_hashtags == ["#edited"]

    def test_draft_approve_request_rejects_negative_index(self) -> None:
        """Verify DraftApproveRequest rejects negative index."""
        from src.models.social import DraftApproveRequest

        with pytest.raises(ValidationError):
            DraftApproveRequest(selected_variation_index=-1)

    def test_draft_reject_requires_reason(self) -> None:
        """Verify DraftRejectRequest requires a non-empty reason."""
        from src.models.social import DraftRejectRequest

        with pytest.raises(ValidationError):
            DraftRejectRequest()  # type: ignore[call-arg]

        with pytest.raises(ValidationError):
            DraftRejectRequest(reason="")

        valid = DraftRejectRequest(reason="Not relevant to my audience")
        assert valid.reason == "Not relevant to my audience"

    def test_engagement_stats_defaults(self) -> None:
        """Verify EngagementStats defaults to zeros."""
        from src.models.social import EngagementStats

        stats = EngagementStats()
        assert stats.likes == 0
        assert stats.comments == 0
        assert stats.shares == 0
        assert stats.impressions == 0

    def test_engagement_stats_with_values(self) -> None:
        """Verify EngagementStats accepts custom values."""
        from src.models.social import EngagementStats

        stats = EngagementStats(likes=42, comments=7, shares=3, impressions=1200)
        assert stats.likes == 42
        assert stats.comments == 7
        assert stats.shares == 3
        assert stats.impressions == 1200

    def test_social_stats_response(self) -> None:
        """Create SocialStatsResponse with all fields."""
        from src.models.social import SocialStatsResponse

        response = SocialStatsResponse(
            total_posts=15,
            posts_this_week=3,
            avg_likes=24.5,
            avg_comments=4.2,
            avg_shares=1.8,
            avg_impressions=850.0,
            best_post_id="post-abc-123",
            best_post_impressions=3200,
            posting_goal=2,
            posting_goal_met=True,
        )
        assert response.total_posts == 15
        assert response.posts_this_week == 3
        assert response.avg_likes == 24.5
        assert response.avg_comments == 4.2
        assert response.avg_shares == 1.8
        assert response.avg_impressions == 850.0
        assert response.best_post_id == "post-abc-123"
        assert response.best_post_impressions == 3200
        assert response.posting_goal == 2
        assert response.posting_goal_met is True

    def test_social_stats_response_defaults(self) -> None:
        """Verify SocialStatsResponse defaults."""
        from src.models.social import SocialStatsResponse

        response = SocialStatsResponse()
        assert response.total_posts == 0
        assert response.posts_this_week == 0
        assert response.avg_likes == 0.0
        assert response.avg_comments == 0.0
        assert response.avg_shares == 0.0
        assert response.avg_impressions == 0.0
        assert response.best_post_id is None
        assert response.best_post_impressions == 0
        assert response.posting_goal == 2
        assert response.posting_goal_met is False

    def test_trigger_type_enum(self) -> None:
        """Verify TriggerType enum values."""
        from src.models.social import TriggerType

        assert TriggerType.SIGNAL == "signal"
        assert TriggerType.MEETING == "meeting"
        assert TriggerType.CURATION == "curation"
        assert TriggerType.MILESTONE == "milestone"
        assert TriggerType.CADENCE == "cadence"

        expected = {"signal", "meeting", "curation", "milestone", "cadence"}
        actual = {t.value for t in TriggerType}
        assert actual == expected

    def test_post_variation_type_enum(self) -> None:
        """Verify PostVariationType enum values."""
        from src.models.social import PostVariationType

        assert PostVariationType.INSIGHT == "insight"
        assert PostVariationType.EDUCATIONAL == "educational"
        assert PostVariationType.ENGAGEMENT == "engagement"

    def test_post_draft_creation(self) -> None:
        """Create a PostDraft with all fields."""
        from src.models.social import (
            PostDraft,
            PostVariation,
            PostVariationType,
            TriggerType,
        )

        variation = PostVariation(
            variation_type=PostVariationType.INSIGHT,
            text="Post text",
            hashtags=["#test"],
            voice_match_confidence=0.9,
        )
        draft = PostDraft(
            action_id="action-123",
            trigger_type=TriggerType.SIGNAL,
            trigger_source="FDA approval news",
            variations=[variation],
            suggested_time="2026-02-10T09:00:00Z",
            suggested_time_reasoning="Morning posts get higher engagement",
            created_at="2026-02-10T08:00:00Z",
        )
        assert draft.action_id == "action-123"
        assert draft.trigger_type == TriggerType.SIGNAL
        assert draft.trigger_source == "FDA approval news"
        assert len(draft.variations) == 1
        assert draft.suggested_time == "2026-02-10T09:00:00Z"
        assert draft.suggested_time_reasoning == "Morning posts get higher engagement"
        assert draft.created_at == "2026-02-10T08:00:00Z"

    def test_publish_result(self) -> None:
        """Verify PublishResult model."""
        from src.models.social import PublishResult

        success = PublishResult(success=True, post_urn="urn:li:share:123456")
        assert success.success is True
        assert success.post_urn == "urn:li:share:123456"
        assert success.error is None

        failure = PublishResult(success=False, error="Token expired")
        assert failure.success is False
        assert failure.post_urn is None
        assert failure.error == "Token expired"

    def test_draft_schedule_request(self) -> None:
        """Verify DraftScheduleRequest requires scheduled_time."""
        from src.models.social import DraftScheduleRequest

        with pytest.raises(ValidationError):
            DraftScheduleRequest()  # type: ignore[call-arg]

        req = DraftScheduleRequest(scheduled_time="2026-02-10T14:00:00Z")
        assert req.selected_variation_index == 0
        assert req.scheduled_time == "2026-02-10T14:00:00Z"

    def test_engager_info(self) -> None:
        """Verify EngagerInfo model."""
        from src.models.social import EngagerInfo

        engager = EngagerInfo(
            name="Dr. Smith",
            linkedin_url="https://linkedin.com/in/drsmith",
            relationship="known_stakeholder",
            lead_id="lead-789",
        )
        assert engager.name == "Dr. Smith"
        assert engager.linkedin_url == "https://linkedin.com/in/drsmith"
        assert engager.relationship == "known_stakeholder"
        assert engager.lead_id == "lead-789"

    def test_engager_info_defaults(self) -> None:
        """Verify EngagerInfo defaults."""
        from src.models.social import EngagerInfo

        engager = EngagerInfo(name="Unknown User")
        assert engager.linkedin_url is None
        assert engager.relationship == ""
        assert engager.lead_id is None

    def test_engagement_report(self) -> None:
        """Verify EngagementReport model."""
        from src.models.social import EngagementReport, EngagementStats

        report = EngagementReport(
            stats=EngagementStats(likes=10, comments=2),
        )
        assert report.stats.likes == 10
        assert report.notable_engagers == []
        assert report.reply_drafts == []


# ---------------------------------------------------------------------------
# LinkedIn capability tests
# ---------------------------------------------------------------------------


class TestLinkedInDraftPost:
    """Tests for LinkedInIntelligenceCapability.draft_post method."""

    def _make_capability(self) -> "LinkedInIntelligenceCapability":  # noqa: F821
        """Create a LinkedInIntelligenceCapability with mocked dependencies."""
        from src.agents.capabilities.base import UserContext
        from src.agents.capabilities.linkedin import LinkedInIntelligenceCapability

        mock_supabase = MagicMock()
        mock_memory = MagicMock()
        mock_kg = MagicMock()
        user_ctx = UserContext(user_id="user-test-123")

        cap = LinkedInIntelligenceCapability(
            supabase_client=mock_supabase,
            memory_service=mock_memory,
            knowledge_graph=mock_kg,
            user_context=user_ctx,
        )
        return cap

    @pytest.mark.asyncio
    @patch("src.agents.capabilities.linkedin.SupabaseClient")
    @patch("src.agents.capabilities.linkedin.LLMClient")
    async def test_draft_post_returns_empty_on_llm_failure(
        self,
        mock_llm_cls: MagicMock,
        mock_supabase_cls: MagicMock,
    ) -> None:
        """Mock LLM to raise exception, verify empty list returned."""
        # Set up the mocked Supabase client chain
        mock_db = MagicMock()
        mock_supabase_cls.get_client.return_value = mock_db
        mock_db.table.return_value.select.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )

        # Set up the mocked LLM to raise an exception
        mock_llm_instance = MagicMock()
        mock_llm_instance.generate_response = AsyncMock(
            side_effect=RuntimeError("LLM service unavailable"),
        )
        mock_llm_cls.return_value = mock_llm_instance

        cap = self._make_capability()
        result = await cap.draft_post(
            user_id="user-test-123",
            trigger_context={
                "trigger_type": "signal",
                "trigger_source": "FDA news",
                "content": "New drug approved",
            },
        )

        assert result == []
        assert isinstance(result, list)
