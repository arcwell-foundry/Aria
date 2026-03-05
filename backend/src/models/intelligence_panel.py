"""Pydantic models for the Intelligence Panel API."""

from pydantic import BaseModel


class UpcomingMeeting(BaseModel):
    """A single upcoming meeting for the intelligence panel."""

    title: str
    time: str  # e.g., "11:00 AM"
    date: str  # e.g., "Today", "Tomorrow", "Mar 10"
    attendees: list[str]


class MeetingsSection(BaseModel):
    """Meetings section of the intelligence panel."""

    upcoming: list[UpcomingMeeting]
    count: int


class RecentSignal(BaseModel):
    """A single recent market signal."""

    company: str
    headline: str
    type: str  # signal_type
    score: float  # relevance_score


class SignalsSection(BaseModel):
    """Signals section of the intelligence panel."""

    recent: list[RecentSignal]
    unread_count: int
    total_count: int


class QuickStats(BaseModel):
    """Quick stats section of the intelligence panel."""

    pending_drafts: int
    open_tasks: int
    battle_cards: int
    pipeline_count: int


class IntelligencePanelResponse(BaseModel):
    """Full intelligence panel response."""

    meetings: MeetingsSection
    signals: SignalsSection
    quick_stats: QuickStats
