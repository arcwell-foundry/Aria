"""Models package for ARIA backend."""

from src.models.email_draft import (
    EmailDraftCreate,
    EmailDraftListResponse,
    EmailDraftPurpose,
    EmailDraftResponse,
    EmailDraftStatus,
    EmailDraftTone,
    EmailDraftUpdate,
    EmailRegenerateRequest,
    EmailSendResponse,
)
from src.models.meeting_brief import (
    AttendeeProfileResponse,
    BriefStatus,
    CompanyResearchResponse,
    GenerateBriefRequest,
    MeetingBriefContent,
    MeetingBriefResponse,
    UpcomingMeetingResponse,
)
from src.models.preferences import (
    DefaultTone,
    MeetingBriefLeadHours,
    PreferenceCreate,
    PreferenceResponse,
    PreferenceUpdate,
)

__all__ = [
    "AttendeeProfileResponse",
    "BriefStatus",
    "CompanyResearchResponse",
    "DefaultTone",
    "EmailDraftCreate",
    "EmailDraftListResponse",
    "EmailDraftPurpose",
    "EmailDraftResponse",
    "EmailDraftStatus",
    "EmailDraftTone",
    "EmailDraftUpdate",
    "EmailRegenerateRequest",
    "EmailSendResponse",
    "GenerateBriefRequest",
    "MeetingBriefContent",
    "MeetingBriefLeadHours",
    "MeetingBriefResponse",
    "PreferenceCreate",
    "PreferenceResponse",
    "PreferenceUpdate",
    "UpcomingMeetingResponse",
]
