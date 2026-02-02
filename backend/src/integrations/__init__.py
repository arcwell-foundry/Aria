"""Integrations with external services.

This package contains clients for integrating with third-party APIs and services.
"""

from src.integrations.tavus import TavusClient, get_tavus_client

__all__ = ["TavusClient", "get_tavus_client"]
