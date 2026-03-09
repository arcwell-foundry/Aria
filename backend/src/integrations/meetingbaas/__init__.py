"""MeetingBaaS integration for automated meeting bot dispatch."""

from src.integrations.meetingbaas.client import MeetingBaaSClient, get_meetingbaas_client

__all__ = ["MeetingBaaSClient", "get_meetingbaas_client"]
