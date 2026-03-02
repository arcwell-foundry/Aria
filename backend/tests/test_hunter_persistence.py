"""Tests for Hunter agent output persistence to discovered_leads."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import UTC, datetime


@pytest.fixture
def goal_exec_service():
    """Create a GoalExecutionService with mocked dependencies."""
    with patch("src.services.goal_execution.SupabaseClient") as mock_supa:
        mock_client = MagicMock()
        mock_supa.get_client.return_value = mock_client

        from src.services.goal_execution import GoalExecutionService
        svc = GoalExecutionService()
        svc._db = mock_client
        return svc, mock_client


@pytest.mark.asyncio
async def test_persist_hunter_leads_from_skill_path(goal_exec_service):
    """Skill-aware path wraps leads as {"result": [...]} — should persist."""
    svc, mock_client = goal_exec_service

    content = {
        "result": [
            {
                "company": {"name": "Acme Pharma", "domain": "acme.com"},
                "contacts": [{"name": "Jane Doe", "title": "VP Sales"}],
                "fit_score": 85.0,
                "fit_reasons": ["Large pharma", "Active hiring"],
                "gaps": ["No recent funding data"],
                "source": "hunter_pro",
            }
        ]
    }

    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.insert.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[{"id": "test"}])

    await svc._persist_hunter_leads("user-1", content, "goal-1", datetime.now(UTC).isoformat())

    mock_client.table.assert_called_with("discovered_leads")
    mock_table.insert.assert_called_once()
    insert_data = mock_table.insert.call_args[0][0]
    assert insert_data["company_name"] == "Acme Pharma"
    assert insert_data["fit_score"] == 85.0


@pytest.mark.asyncio
async def test_persist_hunter_leads_from_prompt_fallback(goal_exec_service):
    """Prompt-based fallback returns different JSON schema — should still persist."""
    svc, mock_client = goal_exec_service

    content = {
        "summary": "ICP analysis for biotech companies",
        "icp_characteristics": ["Mid-size pharma", "Series B+"],
        "prospect_profiles": [
            {
                "company_type": "Contract Research Organization",
                "company_name": "BioResearch Inc",
                "why_good_fit": "Growing CRO with pharma clients",
                "approach_strategy": "Target VP of Business Development",
            },
            {
                "company_type": "Specialty Pharma",
                "company_name": "NovaTherapeutics",
                "why_good_fit": "Expanding commercial team",
                "approach_strategy": "Connect through industry events",
            },
        ],
        "search_criteria": ["CRO companies", "specialty pharma"],
        "next_steps": ["Refine ICP with user feedback"],
    }

    mock_table = MagicMock()
    mock_client.table.return_value = mock_table
    mock_table.insert.return_value = mock_table
    mock_table.execute.return_value = MagicMock(data=[{"id": "test"}])

    await svc._persist_hunter_leads("user-1", content, "goal-1", datetime.now(UTC).isoformat())

    assert mock_table.insert.call_count == 2
    first_insert = mock_table.insert.call_args_list[0][0][0]
    assert first_insert["company_name"] == "BioResearch Inc"


@pytest.mark.asyncio
async def test_persist_hunter_leads_empty_content(goal_exec_service):
    """Empty or non-lead content should not crash or insert."""
    svc, mock_client = goal_exec_service

    await svc._persist_hunter_leads("user-1", {}, "goal-1", datetime.now(UTC).isoformat())
    await svc._persist_hunter_leads("user-1", {"summary": "nothing"}, "goal-1", datetime.now(UTC).isoformat())

    mock_client.table.assert_not_called()
