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

    def test_get_original_returns_value(self) -> None:
        """Test get_original returns the original value for a token."""
        from src.security.sanitization import TokenMap

        token_map = TokenMap()
        token = token_map.add_token("financial", "$4.2M")

        original = token_map.get_original(token)

        assert original == "$4.2M"

    def test_get_original_returns_none_for_unknown_token(self) -> None:
        """Test get_original returns None for unknown token."""
        from src.security.sanitization import TokenMap

        token_map = TokenMap()

        original = token_map.get_original("[UNKNOWN_001]")

        assert original is None

    def test_get_original_preserves_complex_types(self) -> None:
        """Test get_original preserves complex data types."""
        from src.security.sanitization import TokenMap

        token_map = TokenMap()
        complex_value = {"amount": 4200000, "currency": "USD"}
        token = token_map.add_token("financial", complex_value)

        original = token_map.get_original(token)

        assert original == {"amount": 4200000, "currency": "USD"}


class TestLeakageReport:
    """Tests for LeakageReport dataclass."""

    def test_leakage_report_initializes_with_required_fields(self) -> None:
        """Test LeakageReport initializes with required fields."""
        from src.security.sanitization import LeakageReport

        report = LeakageReport(
            leaked=True,
            leaked_values=["$4.2M", "john@example.com"],
            severity="high",
        )

        assert report.leaked is True
        assert report.leaked_values == ["$4.2M", "john@example.com"]
        assert report.severity == "high"

    def test_leakage_report_no_leak(self) -> None:
        """Test LeakageReport for clean output."""
        from src.security.sanitization import LeakageReport

        report = LeakageReport(
            leaked=False,
            leaked_values=[],
            severity="none",
        )

        assert report.leaked is False
        assert report.leaked_values == []
        assert report.severity == "none"


class TestDataSanitizer:
    """Tests for DataSanitizer class."""

    def test_data_sanitizer_initializes(self) -> None:
        """Test DataSanitizer initializes with classifier."""
        from src.security.sanitization import DataSanitizer
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        assert sanitizer.classifier is classifier
