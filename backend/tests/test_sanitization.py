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

    def test_tokenize_value_returns_token_and_updates_map(self) -> None:
        """Test tokenize_value returns token and updates token map."""
        from src.security.sanitization import DataSanitizer, TokenMap
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)
        token_map = TokenMap()

        token = sanitizer.tokenize_value("$4.2M", "financial", token_map)

        assert token == "[FINANCIAL_001]"
        assert token_map.get_original("[FINANCIAL_001]") == "$4.2M"

    def test_tokenize_value_handles_multiple_values(self) -> None:
        """Test tokenize_value handles multiple values of same type."""
        from src.security.sanitization import DataSanitizer, TokenMap
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)
        token_map = TokenMap()

        token1 = sanitizer.tokenize_value("john@example.com", "contact", token_map)
        token2 = sanitizer.tokenize_value("jane@example.com", "contact", token_map)

        assert token1 == "[CONTACT_001]"
        assert token2 == "[CONTACT_002]"

    def test_redact_value_returns_redaction_marker(self) -> None:
        """Test redact_value returns [REDACTED: type] marker."""
        from src.security.sanitization import DataSanitizer
        from src.security.data_classification import ClassifiedData, DataClass, DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)
        classified = ClassifiedData(
            data="123-45-6789",
            classification=DataClass.REGULATED,
            data_type="ssn",
            source="user_input",
        )

        result = sanitizer.redact_value(classified)

        assert result == "[REDACTED: ssn]"

    def test_redact_value_uses_data_type(self) -> None:
        """Test redact_value uses data_type in marker."""
        from src.security.sanitization import DataSanitizer
        from src.security.data_classification import ClassifiedData, DataClass, DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)
        classified = ClassifiedData(
            data="john@example.com",
            classification=DataClass.CONFIDENTIAL,
            data_type="contact",
            source="crm",
        )

        result = sanitizer.redact_value(classified)

        assert result == "[REDACTED: contact]"

    @pytest.mark.asyncio
    async def test_sanitize_string_returns_tuple(self) -> None:
        """Test sanitize returns (sanitized_data, TokenMap) tuple."""
        from src.security.sanitization import DataSanitizer, TokenMap
        from src.security.data_classification import DataClassifier
        from src.security.trust_levels import SkillTrustLevel

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        result = await sanitizer.sanitize("Hello world", SkillTrustLevel.COMMUNITY)

        assert isinstance(result, tuple)
        assert len(result) == 2
        sanitized, token_map = result
        assert isinstance(token_map, TokenMap)

    @pytest.mark.asyncio
    async def test_sanitize_string_tokenizes_for_allowed_access(self) -> None:
        """Test sanitize tokenizes data when skill has access."""
        from src.security.sanitization import DataSanitizer
        from src.security.data_classification import DataClassifier
        from src.security.trust_levels import SkillTrustLevel

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        # CORE can access RESTRICTED (financial) data
        sanitized, token_map = await sanitizer.sanitize(
            "Revenue: $4.2M",
            SkillTrustLevel.CORE,
        )

        # Should tokenize the financial value
        assert "[FINANCIAL_001]" in sanitized
        assert token_map.get_original("[FINANCIAL_001]") is not None

    @pytest.mark.asyncio
    async def test_sanitize_string_redacts_for_no_access(self) -> None:
        """Test sanitize redacts data when skill lacks access."""
        from src.security.sanitization import DataSanitizer
        from src.security.data_classification import DataClassifier
        from src.security.trust_levels import SkillTrustLevel

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        # COMMUNITY cannot access RESTRICTED (financial) data
        sanitized, token_map = await sanitizer.sanitize(
            "Revenue: $4.2M",
            SkillTrustLevel.COMMUNITY,
        )

        assert "[REDACTED:" in sanitized
        assert len(token_map.tokens) == 0

    @pytest.mark.asyncio
    async def test_sanitize_string_redacts_non_tokenizable(self) -> None:
        """Test sanitize redacts data that cannot be tokenized."""
        from src.security.sanitization import DataSanitizer
        from src.security.data_classification import DataClassifier
        from src.security.trust_levels import SkillTrustLevel

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        # SSN cannot be tokenized even for CORE
        sanitized, token_map = await sanitizer.sanitize(
            "SSN: 123-45-6789",
            SkillTrustLevel.CORE,
        )

        assert "[REDACTED:" in sanitized
        assert "123-45-6789" not in sanitized

    @pytest.mark.asyncio
    async def test_sanitize_dict_processes_all_values(self) -> None:
        """Test sanitize processes all values in a dict."""
        from src.security.sanitization import DataSanitizer
        from src.security.data_classification import DataClassifier
        from src.security.trust_levels import SkillTrustLevel

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        data = {
            "name": "Acme Corp",
            "revenue": "$4.2M",
            "contact": "john@example.com",
        }

        sanitized, token_map = await sanitizer.sanitize(data, SkillTrustLevel.CORE)

        assert isinstance(sanitized, dict)
        assert "name" in sanitized
        assert "[FINANCIAL_" in str(sanitized.get("revenue"))
        assert "[CONTACT_" in str(sanitized.get("contact"))

    @pytest.mark.asyncio
    async def test_sanitize_dict_handles_nested_dicts(self) -> None:
        """Test sanitize handles nested dictionaries."""
        from src.security.sanitization import DataSanitizer
        from src.security.data_classification import DataClassifier
        from src.security.trust_levels import SkillTrustLevel

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        data = {
            "company": "Acme",
            "financials": {
                "revenue": "$4.2M",
                "profit": "$1.5M",
            },
        }

        sanitized, token_map = await sanitizer.sanitize(data, SkillTrustLevel.COMMUNITY)

        assert isinstance(sanitized["financials"], dict)
        assert "[REDACTED:" in str(sanitized["financials"]["revenue"])
