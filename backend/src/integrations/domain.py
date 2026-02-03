"""Domain models for OAuth integrations."""

from dataclasses import dataclass
from enum import Enum
from datetime import datetime


class IntegrationType(str, Enum):
    """Supported integration types."""

    GOOGLE_CALENDAR = "google_calendar"
    GMAIL = "gmail"
    OUTLOOK = "outlook"
    SALESFORCE = "salesforce"
    HUBSPOT = "hubspot"


class IntegrationStatus(str, Enum):
    """Status of an integration connection."""

    ACTIVE = "active"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    PENDING = "pending"


class SyncStatus(str, Enum):
    """Status of the last sync operation."""

    SUCCESS = "success"
    PENDING = "pending"
    FAILED = "failed"


@dataclass
class Integration:
    """User integration connection."""

    id: str
    user_id: str
    integration_type: IntegrationType
    composio_connection_id: str
    composio_account_id: str | None = None
    display_name: str | None = None
    status: IntegrationStatus = IntegrationStatus.ACTIVE
    last_sync_at: datetime | None = None
    sync_status: SyncStatus = SyncStatus.SUCCESS
    error_message: str | None = None
    metadata: dict = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


@dataclass
class IntegrationConfig:
    """Configuration for an integration type."""

    integration_type: IntegrationType
    display_name: str
    description: str
    composio_app_id: str
    icon: str
    scopes: list[str]
    auth_type: str = "oauth2"


# Integration configurations
INTEGRATION_CONFIGS: dict[IntegrationType, IntegrationConfig] = {
    IntegrationType.GOOGLE_CALENDAR: IntegrationConfig(
        integration_type=IntegrationType.GOOGLE_CALENDAR,
        display_name="Google Calendar",
        description="Sync your calendar for meeting briefs and scheduling",
        composio_app_id="google_calendar",
        icon="calendar",
        scopes=["https://www.googleapis.com/auth/calendar.readonly"],
    ),
    IntegrationType.GMAIL: IntegrationConfig(
        integration_type=IntegrationType.GMAIL,
        display_name="Gmail",
        description="Connect Gmail for email drafting and analysis",
        composio_app_id="gmail",
        icon="mail",
        scopes=["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/gmail.send"],
    ),
    IntegrationType.OUTLOOK: IntegrationConfig(
        integration_type=IntegrationType.OUTLOOK,
        display_name="Microsoft Outlook",
        description="Connect Outlook for calendar and email integration",
        composio_app_id="outlook_calendar",
        icon="calendar",
        scopes=["Calendars.ReadWrite", "Mail.ReadWrite", "User.Read"],
    ),
    IntegrationType.SALESFORCE: IntegrationConfig(
        integration_type=IntegrationType.SALESFORCE,
        display_name="Salesforce",
        description="Sync leads and opportunities from Salesforce",
        composio_app_id="salesforce",
        icon="crm",
        scopes=["api", "refresh_token", "full"],
    ),
    IntegrationType.HUBSPOT: IntegrationConfig(
        integration_type=IntegrationType.HUBSPOT,
        display_name="HubSpot",
        description="Connect HubSpot CRM for lead management",
        composio_app_id="hubspot",
        icon="crm",
        scopes=["crm.objects.contacts.read", "crm.objects.companies.read", "crm.objects.deals.read"],
    ),
}
