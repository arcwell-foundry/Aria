"""Integration tests for the meeting brief end-to-end flow.

Tests the complete flow:
1. Create a pending brief
2. Generate content with Scout agent and LLM
3. Verify attendee and company data is included in the result
"""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


@pytest.mark.integration
class TestMeetingBriefFlow:
    """Integration tests for the complete meeting brief generation flow."""

    @pytest.fixture
    def mock_db_client(self) -> MagicMock:
        """Create mock database client with in-memory storage simulation."""
        mock = MagicMock()
        self._storage: dict[str, list[dict[str, Any]]] = {
            "meeting_briefs": [],
            "attendee_profiles": [],
        }
        return mock

    @pytest.fixture
    def mock_anthropic_response(self) -> MagicMock:
        """Create mock Anthropic API response."""
        mock_response = MagicMock()
        mock_content_block = MagicMock()
        mock_content_block.text = """{
            "summary": "This is a discovery call with Acme Corp to discuss their needs.",
            "suggested_agenda": [
                "Introduction and rapport building",
                "Discuss current challenges",
                "Product demonstration",
                "Next steps and follow-up"
            ],
            "risks_opportunities": [
                "Opportunity: Recent funding round - may have budget",
                "Risk: VP Sales is new - may not have decision authority"
            ]
        }"""
        mock_response.content = [mock_content_block]
        return mock_response

    @pytest.fixture
    def mock_attendee_profiles(self) -> dict[str, dict[str, Any]]:
        """Create mock attendee profile data."""
        return {
            "john.smith@acme.com": {
                "email": "john.smith@acme.com",
                "name": "John Smith",
                "title": "VP Sales",
                "company": "Acme Corp",
                "linkedin_url": "https://linkedin.com/in/johnsmith",
                "profile_data": {
                    "experience": "10 years in enterprise sales",
                    "recent_activity": ["Posted about digital transformation"],
                },
            },
            "jane.doe@acme.com": {
                "email": "jane.doe@acme.com",
                "name": "Jane Doe",
                "title": "Director of Operations",
                "company": "Acme Corp",
                "linkedin_url": "https://linkedin.com/in/janedoe",
                "profile_data": {"experience": "15 years in operations management"},
            },
        }

    @pytest.fixture
    def mock_scout_signals(self) -> list[dict[str, Any]]:
        """Create mock Scout agent signals."""
        return [
            {
                "company_name": "Acme Corp",
                "headline": "Acme Corp raises $50M Series C funding",
                "signal_type": "funding",
                "relevance": 0.95,
            },
            {
                "company_name": "Acme Corp",
                "headline": "Acme Corp announces expansion into European markets",
                "signal_type": "expansion",
                "relevance": 0.85,
            },
        ]

    @pytest.mark.asyncio
    async def test_complete_meeting_brief_flow(
        self,
        mock_db_client: MagicMock,
        mock_anthropic_response: MagicMock,
        mock_attendee_profiles: dict[str, dict[str, Any]],
        mock_scout_signals: list[dict[str, Any]],
    ) -> None:
        """Test complete flow: create brief -> generate content -> verify result."""
        from src.services.meeting_brief import MeetingBriefService

        user_id = "integration-test-user"
        calendar_event_id = "evt-integration-test-123"
        brief_id = "brief-integration-123"
        now = datetime.now(UTC)

        # Initial pending brief data
        pending_brief: dict[str, Any] = {
            "id": brief_id,
            "user_id": user_id,
            "calendar_event_id": calendar_event_id,
            "meeting_title": "Discovery Call - Acme Corp",
            "meeting_time": (now.replace(day=now.day + 1)).isoformat(),
            "attendees": ["john.smith@acme.com", "jane.doe@acme.com"],
            "status": "pending",
            "brief_content": {},
            "created_at": now.isoformat(),
            "generated_at": None,
            "error_message": None,
        }

        with (
            patch("src.services.meeting_brief.SupabaseClient") as mock_db_class,
            patch("src.services.meeting_brief.anthropic.Anthropic") as mock_anthropic_class,
            patch("src.services.meeting_brief.AttendeeProfileService") as mock_profile_class,
            patch("src.services.meeting_brief.ScoutAgent") as mock_scout_class,
            patch("src.services.meeting_brief.LLMClient") as mock_llm_class,
        ):
            mock_db_class.get_client.return_value = mock_db_client

            # === STEP 1: Create the brief ===
            mock_db_client.table.return_value.insert.return_value.execute.return_value = (
                MagicMock(data=[pending_brief])
            )

            service = MeetingBriefService()

            # Create the brief
            result = await service.create_brief(
                user_id=user_id,
                calendar_event_id=calendar_event_id,
                meeting_title="Discovery Call - Acme Corp",
                meeting_time=now.replace(day=now.day + 1),
                attendees=["john.smith@acme.com", "jane.doe@acme.com"],
            )

            # Verify brief was created with pending status
            assert result["id"] == brief_id
            assert result["status"] == "pending"
            assert result["meeting_title"] == "Discovery Call - Acme Corp"
            assert len(result["attendees"]) == 2

            # === STEP 2: Generate brief content ===

            # Setup mock for get_brief_by_id
            mock_db_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=pending_brief
            )

            # Setup mock for update_brief_status
            generating_brief = pending_brief.copy()
            generating_brief["status"] = "generating"
            completed_brief = pending_brief.copy()
            completed_brief["status"] = "completed"
            completed_brief["generated_at"] = now.isoformat()
            completed_brief["brief_content"] = {
                "summary": "This is a discovery call with Acme Corp to discuss their needs.",
                "suggested_agenda": ["Introduction and rapport building"],
                "risks_opportunities": ["Opportunity: Recent funding round"],
                "attendee_profiles": mock_attendee_profiles,
                "company_signals": mock_scout_signals,
            }

            # Track update calls
            update_calls: list[dict[str, Any]] = []

            def track_update(data: dict[str, Any]) -> MagicMock:
                update_calls.append(data)
                mock_chain = MagicMock()
                # Return appropriate data based on status
                if data.get("status") == "completed":
                    mock_chain.eq.return_value.eq.return_value.execute.return_value = (
                        MagicMock(data=[completed_brief])
                    )
                else:
                    mock_chain.eq.return_value.eq.return_value.execute.return_value = (
                        MagicMock(data=[generating_brief])
                    )
                return mock_chain

            mock_db_client.table.return_value.update = track_update

            # Setup AttendeeProfileService mock
            mock_profile_service = MagicMock()

            async def mock_get_profiles_batch(
                emails: list[str],
            ) -> dict[str, dict[str, Any]]:
                return {
                    email: mock_attendee_profiles[email]
                    for email in emails
                    if email in mock_attendee_profiles
                }

            mock_profile_service.get_profiles_batch = mock_get_profiles_batch
            mock_profile_class.return_value = mock_profile_service

            # Setup ScoutAgent mock
            mock_scout = MagicMock()

            async def mock_scout_execute(_task: dict[str, Any]) -> MagicMock:
                result = MagicMock()
                result.success = True
                result.data = mock_scout_signals
                return result

            mock_scout.execute = mock_scout_execute
            mock_scout.validate_input.return_value = True
            mock_scout_class.return_value = mock_scout

            # Setup LLMClient mock (used for Scout initialization)
            mock_llm_class.return_value = MagicMock()

            # Setup Anthropic mock
            mock_anthropic_class.return_value.messages.create.return_value = (
                mock_anthropic_response
            )

            # Generate the brief content
            content = await service.generate_brief_content(
                user_id=user_id,
                brief_id=brief_id,
            )

            # === STEP 3: Verify the result ===
            assert content is not None

            # Verify summary is present
            assert "summary" in content
            assert "Acme Corp" in content["summary"]

            # Verify suggested agenda
            assert "suggested_agenda" in content
            assert len(content["suggested_agenda"]) > 0

            # Verify risks and opportunities
            assert "risks_opportunities" in content

            # Verify attendee profiles were included
            assert "attendee_profiles" in content
            assert len(content["attendee_profiles"]) == 2

            # Verify John Smith's profile is in the result
            assert "john.smith@acme.com" in content["attendee_profiles"]
            john_profile = content["attendee_profiles"]["john.smith@acme.com"]
            assert john_profile["name"] == "John Smith"
            assert john_profile["company"] == "Acme Corp"
            assert john_profile["title"] == "VP Sales"

            # Verify Jane Doe's profile is in the result
            assert "jane.doe@acme.com" in content["attendee_profiles"]
            jane_profile = content["attendee_profiles"]["jane.doe@acme.com"]
            assert jane_profile["name"] == "Jane Doe"
            assert jane_profile["company"] == "Acme Corp"

            # Verify company signals were included
            assert "company_signals" in content
            assert len(content["company_signals"]) > 0

            # Verify signal content
            signal_headlines = [s.get("headline", "") for s in content["company_signals"]]
            assert any("funding" in h.lower() for h in signal_headlines)

            # Verify status was updated to generating then completed
            assert len(update_calls) >= 2
            statuses = [call.get("status") for call in update_calls]
            assert "generating" in statuses
            assert "completed" in statuses

    @pytest.mark.asyncio
    async def test_brief_flow_handles_missing_attendee_profiles(
        self,
        mock_db_client: MagicMock,
        mock_anthropic_response: MagicMock,
    ) -> None:
        """Test flow handles case where attendee profiles are not found."""
        from src.services.meeting_brief import MeetingBriefService

        user_id = "test-user"
        brief_id = "brief-no-profiles"
        now = datetime.now(UTC)

        pending_brief = {
            "id": brief_id,
            "user_id": user_id,
            "calendar_event_id": "evt-456",
            "meeting_title": "Quick Chat",
            "meeting_time": now.isoformat(),
            "attendees": ["unknown@external.com"],
            "status": "pending",
            "brief_content": {},
        }

        with (
            patch("src.services.meeting_brief.SupabaseClient") as mock_db_class,
            patch("src.services.meeting_brief.anthropic.Anthropic") as mock_anthropic_class,
            patch("src.services.meeting_brief.AttendeeProfileService") as mock_profile_class,
            patch("src.services.meeting_brief.ScoutAgent") as mock_scout_class,
            patch("src.services.meeting_brief.LLMClient") as mock_llm_class,
        ):
            mock_db_class.get_client.return_value = mock_db_client

            # Setup get_brief_by_id
            mock_db_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=pending_brief
            )

            # Setup update mock
            mock_db_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{**pending_brief, "status": "completed"}]
            )

            # No attendee profiles found (empty dict)
            mock_profile_service = MagicMock()

            async def mock_get_profiles_empty(
                _emails: list[str],
            ) -> dict[str, dict[str, Any]]:
                return {}

            mock_profile_service.get_profiles_batch = mock_get_profiles_empty
            mock_profile_class.return_value = mock_profile_service

            # No scout signals (no companies to research)
            mock_scout = MagicMock()
            mock_scout.validate_input.return_value = False
            mock_scout_class.return_value = mock_scout

            mock_llm_class.return_value = MagicMock()
            mock_anthropic_class.return_value.messages.create.return_value = (
                mock_anthropic_response
            )

            service = MeetingBriefService()
            content = await service.generate_brief_content(
                user_id=user_id,
                brief_id=brief_id,
            )

            # Should still succeed with empty profiles
            assert content is not None
            assert "attendee_profiles" in content
            assert content["attendee_profiles"] == {}
            assert content["company_signals"] == []

    @pytest.mark.asyncio
    async def test_brief_flow_handles_scout_agent_failure(
        self,
        mock_db_client: MagicMock,
        mock_anthropic_response: MagicMock,
        mock_attendee_profiles: dict[str, dict[str, Any]],
    ) -> None:
        """Test flow continues even when Scout agent fails."""
        from src.services.meeting_brief import MeetingBriefService

        user_id = "test-user"
        brief_id = "brief-scout-fail"
        now = datetime.now(UTC)

        pending_brief = {
            "id": brief_id,
            "user_id": user_id,
            "calendar_event_id": "evt-789",
            "meeting_title": "Review Meeting",
            "meeting_time": now.isoformat(),
            "attendees": ["john.smith@acme.com"],
            "status": "pending",
            "brief_content": {},
        }

        with (
            patch("src.services.meeting_brief.SupabaseClient") as mock_db_class,
            patch("src.services.meeting_brief.anthropic.Anthropic") as mock_anthropic_class,
            patch("src.services.meeting_brief.AttendeeProfileService") as mock_profile_class,
            patch("src.services.meeting_brief.ScoutAgent") as mock_scout_class,
            patch("src.services.meeting_brief.LLMClient") as mock_llm_class,
        ):
            mock_db_class.get_client.return_value = mock_db_client

            mock_db_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=pending_brief
            )

            mock_db_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{**pending_brief, "status": "completed"}]
            )

            # Setup profile service
            mock_profile_service = MagicMock()

            async def mock_get_profiles(
                emails: list[str],
            ) -> dict[str, dict[str, Any]]:
                return {
                    email: mock_attendee_profiles[email]
                    for email in emails
                    if email in mock_attendee_profiles
                }

            mock_profile_service.get_profiles_batch = mock_get_profiles
            mock_profile_class.return_value = mock_profile_service

            # Scout agent returns failure
            mock_scout = MagicMock()

            async def mock_scout_execute_fail(_task: dict[str, Any]) -> MagicMock:
                result = MagicMock()
                result.success = False
                result.data = []
                return result

            mock_scout.execute = mock_scout_execute_fail
            mock_scout.validate_input.return_value = True
            mock_scout_class.return_value = mock_scout

            mock_llm_class.return_value = MagicMock()
            mock_anthropic_class.return_value.messages.create.return_value = (
                mock_anthropic_response
            )

            service = MeetingBriefService()
            content = await service.generate_brief_content(
                user_id=user_id,
                brief_id=brief_id,
            )

            # Should still succeed with attendee profiles but no signals
            assert content is not None
            assert len(content["attendee_profiles"]) == 1
            assert content["company_signals"] == []

    @pytest.mark.asyncio
    async def test_brief_flow_handles_llm_failure(
        self,
        mock_db_client: MagicMock,
        mock_attendee_profiles: dict[str, dict[str, Any]],
    ) -> None:
        """Test flow marks brief as failed when LLM call fails."""
        from src.services.meeting_brief import MeetingBriefService

        user_id = "test-user"
        brief_id = "brief-llm-fail"
        now = datetime.now(UTC)

        pending_brief = {
            "id": brief_id,
            "user_id": user_id,
            "calendar_event_id": "evt-fail",
            "meeting_title": "Failed Meeting",
            "meeting_time": now.isoformat(),
            "attendees": ["john.smith@acme.com"],
            "status": "pending",
            "brief_content": {},
        }

        with (
            patch("src.services.meeting_brief.SupabaseClient") as mock_db_class,
            patch("src.services.meeting_brief.anthropic.Anthropic") as mock_anthropic_class,
            patch("src.services.meeting_brief.AttendeeProfileService") as mock_profile_class,
            patch("src.services.meeting_brief.ScoutAgent") as mock_scout_class,
            patch("src.services.meeting_brief.LLMClient") as mock_llm_class,
        ):
            mock_db_class.get_client.return_value = mock_db_client

            mock_db_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=pending_brief
            )

            # Track status updates
            status_updates: list[str] = []

            def track_status_update(data: dict[str, Any]) -> MagicMock:
                if "status" in data:
                    status_updates.append(data["status"])
                mock_chain = MagicMock()
                mock_chain.eq.return_value.eq.return_value.execute.return_value = (
                    MagicMock(data=[{**pending_brief, **data}])
                )
                return mock_chain

            mock_db_client.table.return_value.update = track_status_update

            # Setup profile service
            mock_profile_service = MagicMock()

            async def mock_get_profiles(
                emails: list[str],
            ) -> dict[str, dict[str, Any]]:
                return {
                    email: mock_attendee_profiles[email]
                    for email in emails
                    if email in mock_attendee_profiles
                }

            mock_profile_service.get_profiles_batch = mock_get_profiles
            mock_profile_class.return_value = mock_profile_service

            mock_scout = MagicMock()
            mock_scout.validate_input.return_value = False
            mock_scout_class.return_value = mock_scout

            mock_llm_class.return_value = MagicMock()

            # LLM raises an exception
            mock_anthropic_class.return_value.messages.create.side_effect = Exception(
                "API rate limit exceeded"
            )

            service = MeetingBriefService()
            content = await service.generate_brief_content(
                user_id=user_id,
                brief_id=brief_id,
            )

            # Should return None on failure
            assert content is None

            # Should have updated status to generating, then failed
            assert "generating" in status_updates
            assert "failed" in status_updates

    @pytest.mark.asyncio
    async def test_brief_flow_extracts_unique_companies_from_attendees(
        self,
        mock_db_client: MagicMock,
        mock_anthropic_response: MagicMock,
    ) -> None:
        """Test that unique companies are extracted from attendee profiles for research."""
        from src.services.meeting_brief import MeetingBriefService

        user_id = "test-user"
        brief_id = "brief-companies"
        now = datetime.now(UTC)

        pending_brief = {
            "id": brief_id,
            "user_id": user_id,
            "calendar_event_id": "evt-companies",
            "meeting_title": "Multi-Company Meeting",
            "meeting_time": now.isoformat(),
            "attendees": [
                "person1@acme.com",
                "person2@acme.com",
                "person3@bigcorp.com",
            ],
            "status": "pending",
            "brief_content": {},
        }

        # Profiles with two from same company
        profiles = {
            "person1@acme.com": {
                "email": "person1@acme.com",
                "name": "Person One",
                "title": "Manager",
                "company": "Acme Corp",
            },
            "person2@acme.com": {
                "email": "person2@acme.com",
                "name": "Person Two",
                "title": "Director",
                "company": "Acme Corp",
            },
            "person3@bigcorp.com": {
                "email": "person3@bigcorp.com",
                "name": "Person Three",
                "title": "CEO",
                "company": "BigCorp Inc",
            },
        }

        with (
            patch("src.services.meeting_brief.SupabaseClient") as mock_db_class,
            patch("src.services.meeting_brief.anthropic.Anthropic") as mock_anthropic_class,
            patch("src.services.meeting_brief.AttendeeProfileService") as mock_profile_class,
            patch("src.services.meeting_brief.ScoutAgent") as mock_scout_class,
            patch("src.services.meeting_brief.LLMClient") as mock_llm_class,
        ):
            mock_db_class.get_client.return_value = mock_db_client

            mock_db_client.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
                data=pending_brief
            )

            mock_db_client.table.return_value.update.return_value.eq.return_value.eq.return_value.execute.return_value = MagicMock(
                data=[{**pending_brief, "status": "completed"}]
            )

            mock_profile_service = MagicMock()

            async def mock_get_profiles(
                emails: list[str],
            ) -> dict[str, dict[str, Any]]:
                return {email: profiles[email] for email in emails if email in profiles}

            mock_profile_service.get_profiles_batch = mock_get_profiles
            mock_profile_class.return_value = mock_profile_service

            # Capture what entities are passed to Scout
            captured_entities: list[str] = []

            mock_scout = MagicMock()

            async def mock_scout_execute(task: dict[str, Any]) -> MagicMock:
                captured_entities.extend(task.get("entities", []))
                result = MagicMock()
                result.success = True
                result.data = []
                return result

            mock_scout.execute = mock_scout_execute
            mock_scout.validate_input.return_value = True
            mock_scout_class.return_value = mock_scout

            mock_llm_class.return_value = MagicMock()
            mock_anthropic_class.return_value.messages.create.return_value = (
                mock_anthropic_response
            )

            service = MeetingBriefService()
            await service.generate_brief_content(
                user_id=user_id,
                brief_id=brief_id,
            )

            # Should have unique companies only
            assert len(captured_entities) == 2
            assert "Acme Corp" in captured_entities
            assert "BigCorp Inc" in captured_entities
