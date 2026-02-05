"""Tests for data sanitization pipeline."""

import pytest


class TestTokenMap:
    """Tests for TokenMap class."""

    def test_token_map_initializes_empty(self) -> None:
        """Test TokenMap starts with empty tokens dict."""
        from src.security.sanitization import TokenMap

        token_map = TokenMap()

        assert token_map.tokens == {}
