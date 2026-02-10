"""Pydantic models for LinkedIn posting and social media features."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TriggerType(str, Enum):
    SIGNAL = "signal"
    MEETING = "meeting"
    CURATION = "curation"
    MILESTONE = "milestone"
    CADENCE = "cadence"


class PostVariationType(str, Enum):
    INSIGHT = "insight"
    EDUCATIONAL = "educational"
    ENGAGEMENT = "engagement"


class PostVariation(BaseModel):
    variation_type: PostVariationType
    text: str
    hashtags: list[str] = Field(default_factory=list)
    voice_match_confidence: float = Field(0.0, ge=0.0, le=1.0)


class PostDraft(BaseModel):
    action_id: str
    trigger_type: TriggerType
    trigger_source: str = ""
    variations: list[PostVariation] = Field(default_factory=list)
    suggested_time: str | None = None
    suggested_time_reasoning: str = ""
    created_at: str = ""


class DraftApproveRequest(BaseModel):
    selected_variation_index: int = Field(0, ge=0)
    edited_text: str | None = None
    edited_hashtags: list[str] | None = None


class DraftRejectRequest(BaseModel):
    reason: str = Field(..., min_length=1)


class DraftScheduleRequest(BaseModel):
    selected_variation_index: int = Field(0, ge=0)
    edited_text: str | None = None
    edited_hashtags: list[str] | None = None
    scheduled_time: str = Field(...)


class ReplyApproveRequest(BaseModel):
    edited_text: str | None = None


class PublishResult(BaseModel):
    success: bool
    post_urn: str | None = None
    error: str | None = None


class EngagementStats(BaseModel):
    likes: int = 0
    comments: int = 0
    shares: int = 0
    impressions: int = 0


class EngagerInfo(BaseModel):
    name: str
    linkedin_url: str | None = None
    relationship: str = ""
    lead_id: str | None = None


class EngagementReport(BaseModel):
    stats: EngagementStats
    notable_engagers: list[EngagerInfo] = Field(default_factory=list)
    reply_drafts: list[dict[str, Any]] = Field(default_factory=list)


class SocialStatsResponse(BaseModel):
    total_posts: int = 0
    posts_this_week: int = 0
    avg_likes: float = 0.0
    avg_comments: float = 0.0
    avg_shares: float = 0.0
    avg_impressions: float = 0.0
    best_post_id: str | None = None
    best_post_impressions: int = 0
    posting_goal: int = 2
    posting_goal_met: bool = False
