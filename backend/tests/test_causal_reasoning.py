"""Tests for SalesCausalReasoningEngine."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestSalesAction:
    """Tests for SalesAction dataclass."""

    def test_sales_action_has_all_fields(self) -> None:
        """SalesAction should have all required fields."""
        from src.intelligence.causal_reasoning import SalesAction

        action = SalesAction(
            signal="VP Procurement resigned at BioGenix",
            causal_narrative="Resignation → procurement delays → opportunity to re-engage",
            recommended_action="Schedule intro meeting with interim procurement lead",
            timing="Within 48 hours",
            confidence=0.75,
            urgency="immediate",
            affected_lead_ids=["lead-1", "lead-2"],
            affected_goal_ids=["goal-1"],
            implication_type="opportunity",
        )

        assert action.signal == "VP Procurement resigned at BioGenix"
        assert action.confidence == 0.75
        assert action.urgency == "immediate"
        assert len(action.affected_lead_ids) == 2
        assert action.implication_type == "opportunity"

    def test_sales_action_defaults(self) -> None:
        """SalesAction should have sensible defaults."""
        from src.intelligence.causal_reasoning import SalesAction

        action = SalesAction(
            signal="test",
            causal_narrative="test",
            recommended_action="test",
            timing="test",
            confidence=0.5,
            urgency="monitor",
        )

        assert action.affected_lead_ids == []
        assert action.affected_goal_ids == []
        assert action.implication_type == "neutral"


class TestCausalReasoningResult:
    """Tests for CausalReasoningResult dataclass."""

    def test_result_fields(self) -> None:
        """CausalReasoningResult should capture actions and metadata."""
        from src.intelligence.causal_reasoning import CausalReasoningResult, SalesAction

        result = CausalReasoningResult(
            actions=[
                SalesAction(
                    signal="test",
                    causal_narrative="test",
                    recommended_action="test",
                    timing="now",
                    confidence=0.8,
                    urgency="immediate",
                ),
            ],
            signals_analyzed=1,
            processing_time_ms=150.5,
        )

        assert len(result.actions) == 1
        assert result.signals_analyzed == 1
        assert result.processing_time_ms == 150.5


class TestEngineInit:
    """Tests for SalesCausalReasoningEngine initialization."""

    def test_init_with_defaults(self) -> None:
        """Engine should initialize with default dependencies."""
        from src.intelligence.causal_reasoning import SalesCausalReasoningEngine

        db = MagicMock()
        llm = MagicMock()
        engine = SalesCausalReasoningEngine(db_client=db, llm_client=llm)

        assert engine._db is db
        assert engine._llm is llm
        assert engine._implication_engine is None
        assert engine._cache == {}


class TestUrgencyConversion:
    """Tests for urgency score to category conversion."""

    def test_immediate_urgency(self) -> None:
        """Score >= 0.8 should map to 'immediate'."""
        from src.intelligence.causal_reasoning import SalesCausalReasoningEngine

        assert SalesCausalReasoningEngine._urgency_from_score(0.9) == "immediate"
        assert SalesCausalReasoningEngine._urgency_from_score(0.8) == "immediate"

    def test_this_week_urgency(self) -> None:
        """Score >= 0.6 and < 0.8 should map to 'this_week'."""
        from src.intelligence.causal_reasoning import SalesCausalReasoningEngine

        assert SalesCausalReasoningEngine._urgency_from_score(0.7) == "this_week"
        assert SalesCausalReasoningEngine._urgency_from_score(0.6) == "this_week"

    def test_this_month_urgency(self) -> None:
        """Score >= 0.4 and < 0.6 should map to 'this_month'."""
        from src.intelligence.causal_reasoning import SalesCausalReasoningEngine

        assert SalesCausalReasoningEngine._urgency_from_score(0.5) == "this_month"
        assert SalesCausalReasoningEngine._urgency_from_score(0.4) == "this_month"

    def test_monitor_urgency(self) -> None:
        """Score < 0.4 should map to 'monitor'."""
        from src.intelligence.causal_reasoning import SalesCausalReasoningEngine

        assert SalesCausalReasoningEngine._urgency_from_score(0.3) == "monitor"
        assert SalesCausalReasoningEngine._urgency_from_score(0.0) == "monitor"


class TestFallbackActions:
    """Tests for fallback action generation (no LLM)."""

    def test_fallback_creates_actions_from_implications(self) -> None:
        """Fallback should create SalesAction objects from raw implications."""
        from src.intelligence.causal_reasoning import SalesCausalReasoningEngine

        db = MagicMock()
        llm = MagicMock()
        engine = SalesCausalReasoningEngine(db_client=db, llm_client=llm)

        # Create mock implications
        mock_impl = MagicMock()
        mock_impl.type.value = "opportunity"
        mock_impl.combined_score = 0.7
        mock_impl.confidence = 0.8
        mock_impl.urgency = 0.9
        mock_impl.content = "This creates an opportunity for engagement."
        mock_impl.recommended_actions = ["Schedule meeting with procurement"]
        mock_impl.affected_goals = ["goal-1"]
        mock_impl.time_to_impact = "Within 2 weeks"
        mock_impl.causal_chain = [
            {
                "source_entity": "BioGenix",
                "target_entity": "Procurement",
                "relationship": "threatens",
            }
        ]

        actions = engine._fallback_actions("VP resigned", [mock_impl])
        assert len(actions) == 1
        assert actions[0].signal == "VP resigned"
        assert actions[0].recommended_action == "Schedule meeting with procurement"
        assert actions[0].urgency == "immediate"
        assert actions[0].confidence == 0.8

    def test_fallback_with_empty_implications(self) -> None:
        """Fallback should return empty list for no implications."""
        from src.intelligence.causal_reasoning import SalesCausalReasoningEngine

        db = MagicMock()
        llm = MagicMock()
        engine = SalesCausalReasoningEngine(db_client=db, llm_client=llm)

        actions = engine._fallback_actions("test signal", [])
        assert actions == []

    def test_fallback_limits_to_3_actions(self) -> None:
        """Fallback should create at most 3 actions."""
        from src.intelligence.causal_reasoning import SalesCausalReasoningEngine

        db = MagicMock()
        llm = MagicMock()
        engine = SalesCausalReasoningEngine(db_client=db, llm_client=llm)

        impls = []
        for _ in range(5):
            mock_impl = MagicMock()
            mock_impl.type.value = "opportunity"
            mock_impl.combined_score = 0.5
            mock_impl.confidence = 0.6
            mock_impl.urgency = 0.5
            mock_impl.content = "Test"
            mock_impl.recommended_actions = ["Do something"]
            mock_impl.affected_goals = []
            mock_impl.time_to_impact = "1 week"
            mock_impl.causal_chain = [
                {"source_entity": "A", "target_entity": "B", "relationship": "causes"}
            ]
            impls.append(mock_impl)

        actions = engine._fallback_actions("test", impls)
        assert len(actions) == 3


class TestAnalyzeSignal:
    """Tests for analyze_signal method."""

    @pytest.mark.asyncio
    async def test_returns_empty_on_budget_exceeded(self) -> None:
        """Should return empty when CostGovernor says budget exceeded."""
        from src.intelligence.causal_reasoning import SalesCausalReasoningEngine

        db = MagicMock()
        llm = MagicMock()
        engine = SalesCausalReasoningEngine(db_client=db, llm_client=llm)

        mock_budget = MagicMock()
        mock_budget.can_proceed = False
        mock_governor = AsyncMock()
        mock_governor.check_budget = AsyncMock(return_value=mock_budget)
        engine._cost_governor = mock_governor

        result = await engine.analyze_signal("user-1", "VP resigned")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_implication_engine(self) -> None:
        """Should return empty when ImplicationEngine can't be initialized."""
        from src.intelligence.causal_reasoning import SalesCausalReasoningEngine

        db = MagicMock()
        llm = MagicMock()
        engine = SalesCausalReasoningEngine(db_client=db, llm_client=llm)

        # Mock cost governor to allow proceed
        mock_budget = MagicMock()
        mock_budget.can_proceed = True
        mock_governor = AsyncMock()
        mock_governor.check_budget = AsyncMock(return_value=mock_budget)
        engine._cost_governor = mock_governor

        # Force implication engine init to fail
        with patch.object(engine, "_get_implication_engine", return_value=None):
            result = await engine.analyze_signal("user-1", "VP resigned")
            assert result == []

    @pytest.mark.asyncio
    async def test_returns_cached_result(self) -> None:
        """Should return cached actions within TTL."""
        import time as time_module

        from src.intelligence.causal_reasoning import SalesAction, SalesCausalReasoningEngine

        db = MagicMock()
        llm = MagicMock()
        engine = SalesCausalReasoningEngine(db_client=db, llm_client=llm)

        cached_action = SalesAction(
            signal="test",
            causal_narrative="cached",
            recommended_action="cached action",
            timing="now",
            confidence=0.9,
            urgency="immediate",
        )
        cache_key = f"user-1:{hash('test signal')}"
        engine._cache[cache_key] = ([cached_action], time_module.monotonic())

        result = await engine.analyze_signal("user-1", "test signal")
        assert len(result) == 1
        assert result[0].recommended_action == "cached action"


class TestAnalyzeRecentSignals:
    """Tests for analyze_recent_signals method."""

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_signals(self) -> None:
        """Should return empty result when no signals exist."""
        from src.intelligence.causal_reasoning import SalesCausalReasoningEngine

        db = MagicMock()
        llm = MagicMock()
        engine = SalesCausalReasoningEngine(db_client=db, llm_client=llm)

        mock_result = MagicMock()
        mock_result.data = []
        db.table.return_value.select.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = mock_result

        result = await engine.analyze_recent_signals("user-1")
        assert result.actions == []
        assert result.signals_analyzed == 0
        assert result.processing_time_ms > 0

    @pytest.mark.asyncio
    async def test_handles_db_error_gracefully(self) -> None:
        """Should return empty result on database error."""
        from src.intelligence.causal_reasoning import SalesCausalReasoningEngine

        db = MagicMock()
        llm = MagicMock()
        engine = SalesCausalReasoningEngine(db_client=db, llm_client=llm)

        db.table.side_effect = Exception("DB connection failed")

        result = await engine.analyze_recent_signals("user-1")
        assert result.actions == []


class TestPersistAction:
    """Tests for action persistence to jarvis_insights."""

    @pytest.mark.asyncio
    async def test_persist_inserts_to_jarvis_insights(self) -> None:
        """Should insert action data into jarvis_insights table."""
        from src.intelligence.causal_reasoning import SalesAction, SalesCausalReasoningEngine

        db = MagicMock()
        llm = MagicMock()
        engine = SalesCausalReasoningEngine(db_client=db, llm_client=llm)

        action = SalesAction(
            signal="VP resigned",
            causal_narrative="Chain of events",
            recommended_action="Contact interim lead",
            timing="48 hours",
            confidence=0.8,
            urgency="immediate",
            affected_goal_ids=["goal-1"],
            implication_type="opportunity",
        )

        await engine._persist_action("user-1", action)

        db.table.assert_called_with("jarvis_insights")
        insert_call = db.table.return_value.insert
        assert insert_call.called
        inserted_data = insert_call.call_args[0][0]
        assert inserted_data["user_id"] == "user-1"
        assert inserted_data["insight_type"] == "causal_sales_action"
        assert inserted_data["content"] == "Contact interim lead"

    @pytest.mark.asyncio
    async def test_persist_handles_error_gracefully(self) -> None:
        """Should log warning on persistence error, not raise."""
        from src.intelligence.causal_reasoning import SalesAction, SalesCausalReasoningEngine

        db = MagicMock()
        db.table.side_effect = Exception("Insert failed")
        llm = MagicMock()
        engine = SalesCausalReasoningEngine(db_client=db, llm_client=llm)

        action = SalesAction(
            signal="test",
            causal_narrative="test",
            recommended_action="test",
            timing="now",
            confidence=0.5,
            urgency="monitor",
        )

        # Should not raise
        await engine._persist_action("user-1", action)


class TestLinkAffectedLeads:
    """Tests for lead linking."""

    @pytest.mark.asyncio
    async def test_finds_leads_by_entity_name(self) -> None:
        """Should query leads table with entity names from causal chain."""
        from src.intelligence.causal_reasoning import SalesCausalReasoningEngine

        db = MagicMock()
        llm = MagicMock()
        engine = SalesCausalReasoningEngine(db_client=db, llm_client=llm)

        mock_result = MagicMock()
        mock_result.data = [{"id": "lead-1"}]
        db.table.return_value.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = mock_result

        mock_impl = MagicMock()
        mock_impl.causal_chain = [
            {"source_entity": "BioGenix", "target_entity": "Procurement"},
        ]

        result = await engine._link_affected_leads("user-1", "test", [mock_impl])
        assert "lead-1" in result

    @pytest.mark.asyncio
    async def test_returns_empty_on_no_entities(self) -> None:
        """Should return empty when causal chain has no entities."""
        from src.intelligence.causal_reasoning import SalesCausalReasoningEngine

        db = MagicMock()
        llm = MagicMock()
        engine = SalesCausalReasoningEngine(db_client=db, llm_client=llm)

        mock_impl = MagicMock()
        mock_impl.causal_chain = []

        result = await engine._link_affected_leads("user-1", "test", [mock_impl])
        assert result == []
