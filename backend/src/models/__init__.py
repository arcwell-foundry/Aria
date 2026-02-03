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

__all__ = [
    "AttendeeProfileResponse",
    "BriefStatus",
    "CompanyResearchResponse",
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
    "MeetingBriefResponse",
    "UpcomingMeetingResponse",
]
