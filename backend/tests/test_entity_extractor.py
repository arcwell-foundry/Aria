"""Tests for entity extraction from OODA observations."""

from src.core.entity_extractor import extract_entities_from_observations


class TestExtractEntities:
    """Tests for extract_entities_from_observations."""

    def test_extracts_company_from_hot_context(self) -> None:
        observations = [
            {
                "source": "hot_context",
                "type": "hot",
                "data": "User: Sarah Chen, VP Sales at Meridian Pharma\nActive Goal: Close BioGenix deal",
            }
        ]
        entities = extract_entities_from_observations(observations)
        assert "BioGenix" in entities
        assert "Meridian Pharma" in entities

    def test_extracts_company_from_cold_memory(self) -> None:
        observations = [
            {
                "source": "semantic",
                "type": "cold",
                "data": {
                    "content": "Novartis acquired GenMark Diagnostics for $1.8B",
                    "relevance_score": 0.85,
                },
            }
        ]
        entities = extract_entities_from_observations(observations)
        assert "Novartis" in entities

    def test_extracts_from_goal_text(self) -> None:
        observations = [
            {
                "source": "working",
                "type": "conversation",
                "data": {"messages": [{"content": "Update on the WuXi proposal"}]},
            }
        ]
        entities = extract_entities_from_observations(observations)
        assert "WuXi" in entities

    def test_deduplicates_entities(self) -> None:
        observations = [
            {"source": "hot_context", "type": "hot", "data": "BioGenix deal update"},
            {"source": "semantic", "type": "cold", "data": {"content": "BioGenix pipeline review"}},
        ]
        entities = extract_entities_from_observations(observations)
        assert entities.count("BioGenix") == 1

    def test_limits_to_max_entities(self) -> None:
        observations = [
            {
                "source": "hot_context",
                "type": "hot",
                "data": "Companies: Alpha Corp, Beta Inc, Gamma Ltd, Delta Co, Epsilon Pharma, Zeta Bio, Eta Labs, Theta Med",
            }
        ]
        entities = extract_entities_from_observations(observations, max_entities=5)
        assert len(entities) <= 5

    def test_returns_empty_for_no_observations(self) -> None:
        assert extract_entities_from_observations([]) == []

    def test_handles_malformed_observations(self) -> None:
        observations = [
            {"source": "hot_context", "type": "hot", "data": None},
            {"source": "cold", "type": "cold", "data": 42},
        ]
        # Should not raise
        entities = extract_entities_from_observations(observations)
        assert isinstance(entities, list)
