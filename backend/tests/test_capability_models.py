"""Tests for capability provisioning Pydantic models."""

import pytest
from src.models.capability import (
    CapabilityGap,
    CapabilityProvider,
    ResolutionStrategy,
)


class TestCapabilityProvider:
    def test_native_provider_construction(self):
        provider = CapabilityProvider(
            id="test-id",
            capability_name="research_person",
            capability_category="research",
            provider_name="exa_people_search",
            provider_type="native",
            quality_score=0.80,
        )
        assert provider.capability_name == "research_person"
        assert provider.provider_type == "native"
        assert provider.quality_score == 0.80
        assert provider.composio_app_name is None
        assert provider.is_active is True

    def test_composio_provider_construction(self):
        provider = CapabilityProvider(
            id="test-id",
            capability_name="read_email",
            capability_category="data_access",
            provider_name="composio_outlook",
            provider_type="composio_oauth",
            quality_score=0.95,
            composio_app_name="OUTLOOK365",
            composio_action_name="OUTLOOK365_READ_EMAILS",
        )
        assert provider.composio_app_name == "OUTLOOK365"
        assert provider.composio_action_name == "OUTLOOK365_READ_EMAILS"

    def test_composite_provider_construction(self):
        provider = CapabilityProvider(
            id="test-id",
            capability_name="read_crm_pipeline",
            capability_category="data_access",
            provider_name="email_deal_inference",
            provider_type="composite",
            quality_score=0.65,
            required_capabilities=["read_email"],
        )
        assert provider.required_capabilities == ["read_email"]


class TestResolutionStrategy:
    def test_direct_integration_strategy(self):
        strategy = ResolutionStrategy(
            strategy_type="direct_integration",
            provider_name="composio_outlook",
            quality=0.95,
            composio_app="OUTLOOK365",
            description="Connect Outlook",
            action_label="Connect OUTLOOK365",
        )
        assert strategy.strategy_type == "direct_integration"
        assert strategy.auto_usable is False

    def test_composite_auto_usable(self):
        strategy = ResolutionStrategy(
            strategy_type="composite",
            provider_name="email_deal_inference",
            quality=0.65,
            auto_usable=True,
        )
        assert strategy.auto_usable is True


class TestCapabilityGap:
    def test_blocking_gap(self):
        gap = CapabilityGap(
            capability="read_crm_pipeline",
            step={"description": "Check pipeline"},
            severity="blocking",
        )
        assert gap.severity == "blocking"
        assert gap.can_proceed is False
        assert gap.current_quality == 0

    def test_degraded_gap_with_resolutions(self):
        strategy = ResolutionStrategy(
            strategy_type="direct_integration",
            provider_name="composio_salesforce",
            quality=0.95,
            composio_app="SALESFORCE",
        )
        gap = CapabilityGap(
            capability="read_crm_pipeline",
            step={"description": "Check pipeline"},
            severity="degraded",
            current_provider="user_stated",
            current_quality=0.50,
            can_proceed=True,
            resolutions=[strategy],
        )
        assert gap.can_proceed is True
        assert len(gap.resolutions) == 1

    def test_gap_to_dict(self):
        gap = CapabilityGap(
            capability="read_email",
            step={"description": "Read inbox"},
            severity="blocking",
        )
        d = gap.model_dump()
        assert d["capability"] == "read_email"
        assert d["severity"] == "blocking"
