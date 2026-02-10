"""Tests for SkillCreator — pattern detection, skill creation, and A/B testing."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.skills.creator import (
    AB_TEST_MIN_EXECUTIONS,
    MIN_PATTERN_FREQUENCY,
    CustomSkill,
    Outcome,
    SkillBlueprint,
    SkillCreator,
)

# ruff: noqa: ARG001


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_blueprint(
    *,
    name: str = "weekly-territory-report",
    description: str = "Generate a weekly territory performance report",
    frequency: int = 5,
) -> SkillBlueprint:
    return SkillBlueprint(
        suggested_name=name,
        description=description,
        prompt_chain=[
            "Gather territory data from CRM",
            "Calculate performance metrics",
            "Format as report",
        ],
        output_schema={
            "type": "object",
            "required": ["report"],
            "properties": {"report": {"type": "string"}},
        },
        input_requirements=["territory_id", "date_range"],
        evidence_summary="User requested territory reports 5 times in 30 days",
        pattern_frequency=frequency,
        sample_requests=[
            "Generate my territory report for this week",
            "How is my territory doing?",
            "Weekly territory numbers please",
        ],
    )


def _make_outcome(
    feedback: str = "negative",
    skill_id: str = "skill-1",
) -> Outcome:
    return Outcome(
        execution_id=str(uuid4()),
        feedback=feedback,
        skill_id=skill_id,
    )


def _mock_supabase_chain(mock_client: MagicMock, data: list) -> None:
    """Set up the Supabase method chain to return data."""
    mock_query = MagicMock()
    mock_query.select = MagicMock(return_value=mock_query)
    mock_query.insert = MagicMock(return_value=mock_query)
    mock_query.update = MagicMock(return_value=mock_query)
    mock_query.eq = MagicMock(return_value=mock_query)
    mock_query.in_ = MagicMock(return_value=mock_query)
    mock_query.gte = MagicMock(return_value=mock_query)
    mock_query.order = MagicMock(return_value=mock_query)
    mock_query.limit = MagicMock(return_value=mock_query)
    mock_query.execute = MagicMock(return_value=MagicMock(data=data))
    mock_client.table = MagicMock(return_value=mock_query)


# ---------------------------------------------------------------------------
# SkillBlueprint model tests
# ---------------------------------------------------------------------------


class TestSkillBlueprint:
    """Tests for the SkillBlueprint dataclass."""

    def test_create_blueprint(self) -> None:
        bp = _make_blueprint()
        assert bp.suggested_name == "weekly-territory-report"
        assert bp.pattern_frequency == 5
        assert len(bp.prompt_chain) == 3

    def test_default_values(self) -> None:
        bp = SkillBlueprint(
            suggested_name="test",
            description="test desc",
            prompt_chain=["step1"],
            output_schema={},
            input_requirements=[],
            evidence_summary="test",
        )
        assert bp.pattern_frequency == MIN_PATTERN_FREQUENCY
        assert bp.sample_requests == []


class TestCustomSkill:
    """Tests for the CustomSkill dataclass."""

    def test_create_custom_skill(self) -> None:
        skill = CustomSkill(
            id="abc-123",
            tenant_id="tenant-1",
            skill_name="my-skill",
            description="Does stuff",
            definition={"name": "my-skill"},
        )
        assert skill.id == "abc-123"
        assert skill.trust_level == "user"
        assert skill.version == 1


class TestOutcome:
    """Tests for the Outcome dataclass."""

    def test_create_outcome(self) -> None:
        o = _make_outcome(feedback="positive", skill_id="s1")
        assert o.feedback == "positive"
        assert o.skill_id == "s1"


# ---------------------------------------------------------------------------
# detect_creation_opportunity tests
# ---------------------------------------------------------------------------


class TestDetectCreationOpportunity:
    """Tests for SkillCreator.detect_creation_opportunity."""

    @patch("src.skills.creator.LLMClient")
    @patch("src.skills.creator.SupabaseClient")
    @pytest.mark.asyncio
    async def test_returns_blueprint_when_pattern_found(
        self, mock_sb: MagicMock, mock_llm_cls: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_sb.get_client.return_value = mock_client

        # Execution plans with multi-step DAGs
        plan_rows = [
            {
                "id": str(uuid4()),
                "task_description": "Generate territory report",
                "plan_dag": {"steps": [{"skill_id": "s1"}, {"skill_id": "s2"}]},
                "status": "completed",
                "created_at": datetime.now(UTC).isoformat(),
            }
            for _ in range(4)
        ]
        # Conversation messages
        msg_rows = [
            {
                "id": str(uuid4()),
                "content": "Can you make my territory report?",
                "conversation_id": str(uuid4()),
                "created_at": datetime.now(UTC).isoformat(),
            }
            for _ in range(3)
        ]

        # Set up table mock to return different data per table
        def table_side_effect(name: str) -> MagicMock:
            mock_query = MagicMock()
            mock_query.select = MagicMock(return_value=mock_query)
            mock_query.eq = MagicMock(return_value=mock_query)
            mock_query.in_ = MagicMock(return_value=mock_query)
            mock_query.gte = MagicMock(return_value=mock_query)
            mock_query.order = MagicMock(return_value=mock_query)
            mock_query.limit = MagicMock(return_value=mock_query)

            if name == "skill_execution_plans":
                mock_query.execute = MagicMock(return_value=MagicMock(data=plan_rows))
            elif name == "messages":
                mock_query.execute = MagicMock(return_value=MagicMock(data=msg_rows))
            else:
                mock_query.execute = MagicMock(return_value=MagicMock(data=[]))
            return mock_query

        mock_client.table = MagicMock(side_effect=table_side_effect)

        # LLM returns a blueprint
        llm_response = json.dumps(
            {
                "blueprint": {
                    "suggested_name": "territory-report",
                    "description": "Generate weekly territory reports",
                    "prompt_chain": ["Gather data", "Calculate metrics", "Format"],
                    "output_schema": {"type": "object"},
                    "input_requirements": ["territory_id"],
                    "evidence_summary": "4 similar multi-step requests",
                    "pattern_frequency": 4,
                    "sample_requests": ["territory report please"],
                }
            }
        )

        mock_llm = MagicMock()
        mock_llm.generate_response = AsyncMock(return_value=llm_response)
        mock_llm_cls.return_value = mock_llm

        creator = SkillCreator()
        creator._llm = mock_llm

        result = await creator.detect_creation_opportunity("user-1")

        assert result is not None
        assert result.suggested_name == "territory-report"
        assert result.pattern_frequency == 4
        assert len(result.prompt_chain) == 3

    @patch("src.skills.creator.LLMClient")
    @patch("src.skills.creator.SupabaseClient")
    @pytest.mark.asyncio
    async def test_returns_none_when_no_evidence(
        self, mock_sb: MagicMock, mock_llm_cls: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_sb.get_client.return_value = mock_client
        _mock_supabase_chain(mock_client, [])

        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        creator = SkillCreator()
        creator._llm = mock_llm

        result = await creator.detect_creation_opportunity("user-1")
        assert result is None

    @patch("src.skills.creator.LLMClient")
    @patch("src.skills.creator.SupabaseClient")
    @pytest.mark.asyncio
    async def test_returns_none_when_pattern_below_threshold(
        self, mock_sb: MagicMock, mock_llm_cls: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_sb.get_client.return_value = mock_client

        # Some evidence but LLM says frequency is below threshold
        plan_rows = [
            {
                "id": str(uuid4()),
                "task_description": "Random task",
                "plan_dag": {"steps": [{"skill_id": "s1"}, {"skill_id": "s2"}]},
                "status": "completed",
                "created_at": datetime.now(UTC).isoformat(),
            }
        ]

        def table_side_effect(name: str) -> MagicMock:
            mock_query = MagicMock()
            mock_query.select = MagicMock(return_value=mock_query)
            mock_query.eq = MagicMock(return_value=mock_query)
            mock_query.in_ = MagicMock(return_value=mock_query)
            mock_query.gte = MagicMock(return_value=mock_query)
            mock_query.order = MagicMock(return_value=mock_query)
            mock_query.limit = MagicMock(return_value=mock_query)
            if name == "skill_execution_plans":
                mock_query.execute = MagicMock(return_value=MagicMock(data=plan_rows))
            else:
                mock_query.execute = MagicMock(return_value=MagicMock(data=[]))
            return mock_query

        mock_client.table = MagicMock(side_effect=table_side_effect)

        llm_response = json.dumps(
            {
                "blueprint": {
                    "suggested_name": "low-freq",
                    "description": "Low frequency pattern",
                    "prompt_chain": ["step1"],
                    "output_schema": {},
                    "input_requirements": [],
                    "evidence_summary": "Only 2 occurrences",
                    "pattern_frequency": 2,
                    "sample_requests": [],
                }
            }
        )

        mock_llm = MagicMock()
        mock_llm.generate_response = AsyncMock(return_value=llm_response)
        mock_llm_cls.return_value = mock_llm

        creator = SkillCreator()
        creator._llm = mock_llm

        result = await creator.detect_creation_opportunity("user-1")
        assert result is None

    @patch("src.skills.creator.LLMClient")
    @patch("src.skills.creator.SupabaseClient")
    @pytest.mark.asyncio
    async def test_returns_none_when_llm_returns_null(
        self, mock_sb: MagicMock, mock_llm_cls: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_sb.get_client.return_value = mock_client

        plan_rows = [
            {
                "id": str(uuid4()),
                "task_description": "Task",
                "plan_dag": {"steps": [{"skill_id": "s1"}, {"skill_id": "s2"}]},
                "status": "completed",
                "created_at": datetime.now(UTC).isoformat(),
            }
        ]

        def table_side_effect(name: str) -> MagicMock:
            mock_query = MagicMock()
            mock_query.select = MagicMock(return_value=mock_query)
            mock_query.eq = MagicMock(return_value=mock_query)
            mock_query.in_ = MagicMock(return_value=mock_query)
            mock_query.gte = MagicMock(return_value=mock_query)
            mock_query.order = MagicMock(return_value=mock_query)
            mock_query.limit = MagicMock(return_value=mock_query)
            if name == "skill_execution_plans":
                mock_query.execute = MagicMock(return_value=MagicMock(data=plan_rows))
            else:
                mock_query.execute = MagicMock(return_value=MagicMock(data=[]))
            return mock_query

        mock_client.table = MagicMock(side_effect=table_side_effect)

        mock_llm = MagicMock()
        mock_llm.generate_response = AsyncMock(return_value='{"blueprint": null}')
        mock_llm_cls.return_value = mock_llm

        creator = SkillCreator()
        creator._llm = mock_llm

        result = await creator.detect_creation_opportunity("user-1")
        assert result is None

    @patch("src.skills.creator.LLMClient")
    @patch("src.skills.creator.SupabaseClient")
    @pytest.mark.asyncio
    async def test_handles_llm_json_error_gracefully(
        self, mock_sb: MagicMock, mock_llm_cls: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_sb.get_client.return_value = mock_client

        plan_rows = [
            {
                "id": str(uuid4()),
                "task_description": "Task",
                "plan_dag": {"steps": [{"skill_id": "s1"}, {"skill_id": "s2"}]},
                "status": "completed",
                "created_at": datetime.now(UTC).isoformat(),
            }
        ]

        def table_side_effect(name: str) -> MagicMock:
            mock_query = MagicMock()
            mock_query.select = MagicMock(return_value=mock_query)
            mock_query.eq = MagicMock(return_value=mock_query)
            mock_query.in_ = MagicMock(return_value=mock_query)
            mock_query.gte = MagicMock(return_value=mock_query)
            mock_query.order = MagicMock(return_value=mock_query)
            mock_query.limit = MagicMock(return_value=mock_query)
            if name == "skill_execution_plans":
                mock_query.execute = MagicMock(return_value=MagicMock(data=plan_rows))
            else:
                mock_query.execute = MagicMock(return_value=MagicMock(data=[]))
            return mock_query

        mock_client.table = MagicMock(side_effect=table_side_effect)

        mock_llm = MagicMock()
        mock_llm.generate_response = AsyncMock(return_value="not valid json")
        mock_llm_cls.return_value = mock_llm

        creator = SkillCreator()
        creator._llm = mock_llm

        result = await creator.detect_creation_opportunity("user-1")
        assert result is None

    @patch("src.skills.creator.LLMClient")
    @patch("src.skills.creator.SupabaseClient")
    @pytest.mark.asyncio
    async def test_skips_single_step_plans(
        self, mock_sb: MagicMock, mock_llm_cls: MagicMock
    ) -> None:
        """Plans with < 2 steps should not be included as evidence."""
        mock_client = MagicMock()
        mock_sb.get_client.return_value = mock_client

        # Only single-step plans
        plan_rows = [
            {
                "id": str(uuid4()),
                "task_description": "Simple task",
                "plan_dag": {"steps": [{"skill_id": "s1"}]},
                "status": "completed",
                "created_at": datetime.now(UTC).isoformat(),
            }
        ]

        def table_side_effect(name: str) -> MagicMock:
            mock_query = MagicMock()
            mock_query.select = MagicMock(return_value=mock_query)
            mock_query.eq = MagicMock(return_value=mock_query)
            mock_query.in_ = MagicMock(return_value=mock_query)
            mock_query.gte = MagicMock(return_value=mock_query)
            mock_query.order = MagicMock(return_value=mock_query)
            mock_query.limit = MagicMock(return_value=mock_query)
            mock_query.execute = MagicMock(
                return_value=MagicMock(data=plan_rows if name == "skill_execution_plans" else [])
            )
            return mock_query

        mock_client.table = MagicMock(side_effect=table_side_effect)

        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        creator = SkillCreator()
        creator._llm = mock_llm

        result = await creator.detect_creation_opportunity("user-1")
        # No multi-step evidence → no LLM call, no blueprint
        assert result is None
        mock_llm.generate_response.assert_not_called()


# ---------------------------------------------------------------------------
# create_custom_skill tests
# ---------------------------------------------------------------------------


class TestCreateCustomSkill:
    """Tests for SkillCreator.create_custom_skill."""

    @patch("src.skills.creator.LLMClient")
    @patch("src.skills.creator.SupabaseClient")
    @pytest.mark.asyncio
    async def test_creates_and_persists_skill(
        self, mock_sb: MagicMock, mock_llm_cls: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_sb.get_client.return_value = mock_client

        tenant_id = uuid4()
        skill_id = str(uuid4())

        saved_row = {
            "id": skill_id,
            "tenant_id": str(tenant_id),
            "skill_name": "territory-report",
            "description": "Generate weekly territory reports",
            "definition": {"name": "territory-report"},
            "trust_level": "user",
            "version": 1,
            "created_at": datetime.now(UTC).isoformat(),
        }

        mock_query = MagicMock()
        mock_query.insert = MagicMock(return_value=mock_query)
        mock_query.execute = MagicMock(return_value=MagicMock(data=[saved_row]))
        mock_client.table = MagicMock(return_value=mock_query)

        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        creator = SkillCreator()
        blueprint = _make_blueprint()

        with (
            patch.object(creator, "_register_with_registry", new_callable=AsyncMock),
            patch.object(creator, "_notify_skill_created", new_callable=AsyncMock),
        ):
            result = await creator.create_custom_skill(blueprint, tenant_id)

        assert isinstance(result, CustomSkill)
        assert result.id == skill_id
        assert result.skill_name == "territory-report"
        assert result.trust_level == "user"
        assert result.version == 1

    @patch("src.skills.creator.LLMClient")
    @patch("src.skills.creator.SupabaseClient")
    @pytest.mark.asyncio
    async def test_raises_on_insert_failure(
        self, mock_sb: MagicMock, mock_llm_cls: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_sb.get_client.return_value = mock_client

        mock_query = MagicMock()
        mock_query.insert = MagicMock(return_value=mock_query)
        mock_query.execute = MagicMock(return_value=MagicMock(data=[]))
        mock_client.table = MagicMock(return_value=mock_query)

        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        creator = SkillCreator()
        blueprint = _make_blueprint()

        with pytest.raises(RuntimeError, match="Failed to insert"):
            await creator.create_custom_skill(blueprint, uuid4())

    @patch("src.skills.creator.LLMClient")
    @patch("src.skills.creator.SupabaseClient")
    def test_build_definition_structure(self, mock_sb: MagicMock, mock_llm_cls: MagicMock) -> None:
        mock_sb.get_client.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()

        creator = SkillCreator()
        blueprint = _make_blueprint()
        definition = creator._build_definition(blueprint)

        assert definition["name"] == "weekly-territory-report"
        assert definition["trust_level"] == "user"
        assert "system_prompt" in definition
        assert "Step 1:" in definition["system_prompt"]
        assert "Step 3:" in definition["system_prompt"]
        assert definition["output_schema"] == blueprint.output_schema
        assert definition["input_requirements"] == blueprint.input_requirements
        assert definition["prompt_chain"] == blueprint.prompt_chain


# ---------------------------------------------------------------------------
# improve_existing_skill tests
# ---------------------------------------------------------------------------


class TestImproveExistingSkill:
    """Tests for SkillCreator.improve_existing_skill."""

    @patch("src.skills.creator.LLMClient")
    @patch("src.skills.creator.SupabaseClient")
    @pytest.mark.asyncio
    async def test_skips_when_no_negative_feedback(
        self, mock_sb: MagicMock, mock_llm_cls: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_sb.get_client.return_value = mock_client

        skill_row = {
            "id": "skill-1",
            "definition": {"system_prompt": "Original prompt", "name": "test"},
            "version": 1,
        }

        def table_side_effect(name: str) -> MagicMock:
            mock_query = MagicMock()
            mock_query.select = MagicMock(return_value=mock_query)
            mock_query.eq = MagicMock(return_value=mock_query)
            mock_query.execute = MagicMock(return_value=MagicMock(data=[skill_row]))
            return mock_query

        mock_client.table = MagicMock(side_effect=table_side_effect)

        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        creator = SkillCreator()
        creator._llm = mock_llm

        # All positive feedback — should skip
        feedback = [_make_outcome(feedback="positive") for _ in range(3)]
        await creator.improve_existing_skill("skill-1", feedback)

        # LLM should not be called for improvement
        mock_llm.generate_response.assert_not_called()

    @patch("src.skills.creator.LLMClient")
    @patch("src.skills.creator.SupabaseClient")
    @pytest.mark.asyncio
    async def test_starts_ab_test_on_negative_feedback(
        self, mock_sb: MagicMock, mock_llm_cls: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_sb.get_client.return_value = mock_client

        skill_row = {
            "id": "skill-1",
            "definition": {
                "system_prompt": "Original prompt",
                "name": "test-skill",
                "description": "Test skill",
            },
            "version": 1,
        }

        update_mock = MagicMock()
        update_mock.eq = MagicMock(return_value=update_mock)
        update_mock.execute = MagicMock(return_value=MagicMock(data=[]))

        def table_side_effect(name: str) -> MagicMock:
            mock_query = MagicMock()
            mock_query.select = MagicMock(return_value=mock_query)
            mock_query.eq = MagicMock(return_value=mock_query)
            mock_query.execute = MagicMock(return_value=MagicMock(data=[skill_row]))
            mock_query.update = MagicMock(return_value=update_mock)
            return mock_query

        mock_client.table = MagicMock(side_effect=table_side_effect)

        improved_response = json.dumps({"improved_prompt": "Better prompt with more detail"})

        mock_llm = MagicMock()
        mock_llm.generate_response = AsyncMock(return_value=improved_response)
        mock_llm_cls.return_value = mock_llm

        creator = SkillCreator()
        creator._llm = mock_llm

        feedback = [_make_outcome(feedback="negative") for _ in range(3)]
        await creator.improve_existing_skill("skill-1", feedback)

        # LLM should have been called to generate improved prompt
        mock_llm.generate_response.assert_called_once()

    @patch("src.skills.creator.LLMClient")
    @patch("src.skills.creator.SupabaseClient")
    @pytest.mark.asyncio
    async def test_skips_when_skill_not_found(
        self, mock_sb: MagicMock, mock_llm_cls: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_sb.get_client.return_value = mock_client

        def table_side_effect(name: str) -> MagicMock:
            mock_query = MagicMock()
            mock_query.select = MagicMock(return_value=mock_query)
            mock_query.eq = MagicMock(return_value=mock_query)
            mock_query.execute = MagicMock(return_value=MagicMock(data=[]))
            return mock_query

        mock_client.table = MagicMock(side_effect=table_side_effect)

        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        creator = SkillCreator()
        creator._llm = mock_llm

        feedback = [_make_outcome(feedback="negative")]
        await creator.improve_existing_skill("nonexistent", feedback)

        mock_llm.generate_response.assert_not_called()

    @patch("src.skills.creator.LLMClient")
    @patch("src.skills.creator.SupabaseClient")
    @pytest.mark.asyncio
    async def test_evaluates_existing_ab_test(
        self, mock_sb: MagicMock, mock_llm_cls: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_sb.get_client.return_value = mock_client

        # Skill already has an A/B test running
        skill_row = {
            "id": "skill-1",
            "definition": {
                "system_prompt": "Original prompt",
                "name": "test",
                "ab_test_variant": {
                    "system_prompt": "Variant prompt",
                    "executions": AB_TEST_MIN_EXECUTIONS,
                    "positive_feedback": 8,
                    "negative_feedback": 2,
                },
                "ab_test_original": {
                    "executions": AB_TEST_MIN_EXECUTIONS,
                    "positive_feedback": 5,
                    "negative_feedback": 5,
                },
            },
            "version": 2,
        }

        update_mock = MagicMock()
        update_mock.eq = MagicMock(return_value=update_mock)
        update_mock.execute = MagicMock(return_value=MagicMock(data=[]))

        def table_side_effect(name: str) -> MagicMock:
            mock_query = MagicMock()
            mock_query.select = MagicMock(return_value=mock_query)
            mock_query.eq = MagicMock(return_value=mock_query)
            mock_query.execute = MagicMock(return_value=MagicMock(data=[skill_row]))
            mock_query.update = MagicMock(return_value=update_mock)
            return mock_query

        mock_client.table = MagicMock(side_effect=table_side_effect)

        mock_llm = MagicMock()
        mock_llm_cls.return_value = mock_llm

        creator = SkillCreator()
        creator._llm = mock_llm

        # New feedback triggers evaluation
        feedback = [_make_outcome(feedback="positive")]
        await creator.improve_existing_skill("skill-1", feedback)

        # Should NOT call LLM for new prompt (evaluating existing test)
        mock_llm.generate_response.assert_not_called()

    @patch("src.skills.creator.LLMClient")
    @patch("src.skills.creator.SupabaseClient")
    @pytest.mark.asyncio
    async def test_handles_llm_improvement_failure(
        self, mock_sb: MagicMock, mock_llm_cls: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_sb.get_client.return_value = mock_client

        skill_row = {
            "id": "skill-1",
            "definition": {
                "system_prompt": "Original",
                "name": "test",
                "description": "Test",
            },
            "version": 1,
        }

        def table_side_effect(name: str) -> MagicMock:
            mock_query = MagicMock()
            mock_query.select = MagicMock(return_value=mock_query)
            mock_query.eq = MagicMock(return_value=mock_query)
            mock_query.execute = MagicMock(return_value=MagicMock(data=[skill_row]))
            return mock_query

        mock_client.table = MagicMock(side_effect=table_side_effect)

        mock_llm = MagicMock()
        mock_llm.generate_response = AsyncMock(return_value="not json")
        mock_llm_cls.return_value = mock_llm

        creator = SkillCreator()
        creator._llm = mock_llm

        feedback = [_make_outcome(feedback="negative")]
        # Should not raise — graceful degradation
        await creator.improve_existing_skill("skill-1", feedback)


# ---------------------------------------------------------------------------
# Internal method tests
# ---------------------------------------------------------------------------


class TestQueryExecutionPlans:
    """Tests for SkillCreator._query_execution_plans."""

    @patch("src.skills.creator.LLMClient")
    @patch("src.skills.creator.SupabaseClient")
    @pytest.mark.asyncio
    async def test_filters_multi_step_plans(
        self, mock_sb: MagicMock, mock_llm_cls: MagicMock
    ) -> None:
        mock_client = MagicMock()
        mock_sb.get_client.return_value = mock_client

        rows = [
            {
                "id": "plan-1",
                "task_description": "Multi-step",
                "plan_dag": {"steps": [{"skill_id": "a"}, {"skill_id": "b"}]},
                "status": "completed",
                "created_at": datetime.now(UTC).isoformat(),
            },
            {
                "id": "plan-2",
                "task_description": "Single-step",
                "plan_dag": {"steps": [{"skill_id": "a"}]},
                "status": "completed",
                "created_at": datetime.now(UTC).isoformat(),
            },
        ]
        _mock_supabase_chain(mock_client, rows)

        mock_llm_cls.return_value = MagicMock()
        creator = SkillCreator()

        result = await creator._query_execution_plans("user-1", "2026-01-01T00:00:00")

        assert len(result) == 1
        assert result[0]["plan_id"] == "plan-1"
        assert result[0]["step_count"] == 2

    @patch("src.skills.creator.LLMClient")
    @patch("src.skills.creator.SupabaseClient")
    @pytest.mark.asyncio
    async def test_handles_db_error(self, mock_sb: MagicMock, mock_llm_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_sb.get_client.return_value = mock_client

        mock_query = MagicMock()
        mock_query.select = MagicMock(return_value=mock_query)
        mock_query.eq = MagicMock(return_value=mock_query)
        mock_query.in_ = MagicMock(side_effect=Exception("DB error"))
        mock_client.table = MagicMock(return_value=mock_query)

        mock_llm_cls.return_value = MagicMock()
        creator = SkillCreator()

        result = await creator._query_execution_plans("user-1", "2026-01-01T00:00:00")
        assert result == []


class TestBuildDefinition:
    """Tests for SkillCreator._build_definition."""

    @patch("src.skills.creator.LLMClient")
    @patch("src.skills.creator.SupabaseClient")
    def test_builds_complete_definition(self, mock_sb: MagicMock, mock_llm_cls: MagicMock) -> None:
        mock_sb.get_client.return_value = MagicMock()
        mock_llm_cls.return_value = MagicMock()

        creator = SkillCreator()
        bp = _make_blueprint()
        defn = creator._build_definition(bp)

        assert defn["name"] == bp.suggested_name
        assert defn["description"] == bp.description
        assert defn["trust_level"] == "user"
        assert defn["estimated_seconds"] == 30
        assert defn["agent_assignment"] == []
        assert "prompt_chain" in defn
        assert "evidence_summary" in defn
        assert "sample_requests" in defn
        # System prompt should include all steps
        for i, step in enumerate(bp.prompt_chain):
            assert f"Step {i + 1}: {step}" in defn["system_prompt"]
