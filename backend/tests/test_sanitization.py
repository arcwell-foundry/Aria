"""Tests for data sanitization pipeline."""

import pytest


class TestTokenMap:
    """Tests for TokenMap class."""

    def test_token_map_initializes_empty(self) -> None:
        """Test TokenMap starts with empty tokens dict."""
        from src.security.sanitization import TokenMap

        token_map = TokenMap()

        assert token_map.tokens == {}

    def test_add_token_returns_token_string(self) -> None:
        """Test add_token returns formatted token string."""
        from src.security.sanitization import TokenMap

        token_map = TokenMap()

        token = token_map.add_token("financial", "$4.2M")

        assert token == "[FINANCIAL_001]"

    def test_add_token_stores_mapping(self) -> None:
        """Test add_token stores token to value mapping."""
        from src.security.sanitization import TokenMap

        token_map = TokenMap()

        token = token_map.add_token("contact", "john@example.com")

        assert token_map.tokens[token] == "john@example.com"

    def test_add_token_increments_counter(self) -> None:
        """Test add_token increments counter for same data type."""
        from src.security.sanitization import TokenMap

        token_map = TokenMap()

        token1 = token_map.add_token("contact", "john@example.com")
        token2 = token_map.add_token("contact", "jane@example.com")
        token3 = token_map.add_token("financial", "$1M")

        assert token1 == "[CONTACT_001]"
        assert token2 == "[CONTACT_002]"
        assert token3 == "[FINANCIAL_001]"

    def test_add_token_uppercases_data_type(self) -> None:
        """Test add_token uppercases the data type in token."""
        from src.security.sanitization import TokenMap

        token_map = TokenMap()

        token = token_map.add_token("Credit_Card", "1234-5678")

        assert token == "[CREDIT_CARD_001]"
