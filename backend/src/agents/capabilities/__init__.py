"""Agent capabilities module for ARIA.

Provides the BaseCapability abstract class that defines
how agents expose discrete, composable units of functionality.
"""

from src.agents.capabilities.base import BaseCapability, CapabilityResult
from src.agents.capabilities.calendar_intel import CalendarIntelligenceCapability
from src.agents.capabilities.compliance import ComplianceScanner, auto_redact, check_sunshine_act
from src.agents.capabilities.contact_enricher import ContactEnricherCapability
from src.agents.capabilities.crm_sync import CRMDeepSyncCapability
from src.agents.capabilities.email_intel import EmailIntelligenceCapability
from src.agents.capabilities.meeting_intel import MeetingIntelligenceCapability
from src.agents.capabilities.messenger import TeamMessengerCapability
from src.agents.capabilities.signal_radar import SignalRadarCapability
from src.agents.capabilities.web_intel import WebIntelligenceCapability

__all__ = [
    "BaseCapability",
    "CalendarIntelligenceCapability",
    "CapabilityResult",
    "ComplianceScanner",
    "ContactEnricherCapability",
    "CRMDeepSyncCapability",
    "EmailIntelligenceCapability",
    "MeetingIntelligenceCapability",
    "SignalRadarCapability",
    "TeamMessengerCapability",
    "WebIntelligenceCapability",
    "auto_redact",
    "check_sunshine_act",
]
