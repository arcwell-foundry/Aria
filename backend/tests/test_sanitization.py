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

    @pytest.mark.asyncio
    async def test_sanitize_list_processes_all_items(self) -> None:
        """Test sanitize processes all items in a list."""
        from src.security.sanitization import DataSanitizer
        from src.security.data_classification import DataClassifier
        from src.security.trust_levels import SkillTrustLevel

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        data = ["john@example.com", "jane@example.com", "public info"]

        sanitized, token_map = await sanitizer.sanitize(data, SkillTrustLevel.CORE)

        assert isinstance(sanitized, list)
        assert len(sanitized) == 3
        assert "[CONTACT_" in sanitized[0]
        assert "[CONTACT_" in sanitized[1]
        assert sanitized[2] == "public info"

    @pytest.mark.asyncio
    async def test_sanitize_list_of_dicts(self) -> None:
        """Test sanitize handles list of dictionaries."""
        from src.security.sanitization import DataSanitizer
        from src.security.data_classification import DataClassifier
        from src.security.trust_levels import SkillTrustLevel

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        data = [
            {"name": "John", "email": "john@example.com"},
            {"name": "Jane", "email": "jane@example.com"},
        ]

        sanitized, token_map = await sanitizer.sanitize(data, SkillTrustLevel.CORE)

        assert isinstance(sanitized, list)
        assert len(sanitized) == 2
        assert sanitized[0]["name"] == "John"
        assert "[CONTACT_" in sanitized[0]["email"]

    def test_detokenize_string_restores_values(self) -> None:
        """Test detokenize restores tokenized values in string."""
        from src.security.sanitization import DataSanitizer, TokenMap
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        token_map = TokenMap()
        token_map.add_token("financial", "$4.2M")
        token_map.add_token("contact", "john@example.com")

        output = "The deal is [FINANCIAL_001] and contact [CONTACT_001]"

        restored = sanitizer.detokenize(output, token_map)

        assert restored == "The deal is $4.2M and contact john@example.com"

    def test_detokenize_preserves_redaction_markers(self) -> None:
        """Test detokenize does not affect redaction markers."""
        from src.security.sanitization import DataSanitizer, TokenMap
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)
        token_map = TokenMap()

        output = "SSN is [REDACTED: ssn] and name is John"

        restored = sanitizer.detokenize(output, token_map)

        assert restored == "SSN is [REDACTED: ssn] and name is John"

    def test_detokenize_handles_dict(self) -> None:
        """Test detokenize restores values in dict."""
        from src.security.sanitization import DataSanitizer, TokenMap
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        token_map = TokenMap()
        token_map.add_token("contact", "john@example.com")

        output = {"result": "Contact is [CONTACT_001]", "status": "ok"}

        restored = sanitizer.detokenize(output, token_map)

        assert restored["result"] == "Contact is john@example.com"
        assert restored["status"] == "ok"

    def test_detokenize_handles_list(self) -> None:
        """Test detokenize restores values in list."""
        from src.security.sanitization import DataSanitizer, TokenMap
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        token_map = TokenMap()
        token_map.add_token("financial", "$4.2M")

        output = ["Revenue is [FINANCIAL_001]", "Target achieved"]

        restored = sanitizer.detokenize(output, token_map)

        assert restored[0] == "Revenue is $4.2M"
        assert restored[1] == "Target achieved"

    def test_validate_output_detects_leaked_values(self) -> None:
        """Test validate_output detects leaked original values."""
        from src.security.sanitization import DataSanitizer, TokenMap
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        token_map = TokenMap()
        token_map.add_token("financial", "$4.2M")
        token_map.add_token("contact", "john@example.com")

        output = "The revenue is $4.2M and target is [FINANCIAL_002]"

        report = sanitizer.validate_output(output, token_map)

        assert report.leaked is True
        assert "$4.2M" in report.leaked_values
        assert report.severity == "high"

    def test_validate_output_clean_output(self) -> None:
        """Test validate_output reports clean for safe output."""
        from src.security.sanitization import DataSanitizer, TokenMap
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        token_map = TokenMap()
        token_map.add_token("financial", "$4.2M")

        output = "The revenue is [FINANCIAL_001] as expected"

        report = sanitizer.validate_output(output, token_map)

        assert report.leaked is False
        assert report.leaked_values == []
        assert report.severity == "none"

    def test_validate_output_checks_nested_structures(self) -> None:
        """Test validate_output checks nested dicts and lists."""
        from src.security.sanitization import DataSanitizer, TokenMap
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        token_map = TokenMap()
        token_map.add_token("contact", "john@example.com")

        output = {
            "summary": "Contact info",
            "details": {
                "email": "john@example.com",
            },
        }

        report = sanitizer.validate_output(output, token_map)

        assert report.leaked is True
        assert "john@example.com" in report.leaked_values

    def test_validate_output_severity_levels(self) -> None:
        """Test validate_output assigns correct severity levels."""
        from src.security.sanitization import DataSanitizer, TokenMap
        from src.security.data_classification import DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        # Single leak - high severity
        token_map = TokenMap()
        token_map.add_token("financial", "$4.2M")
        report = sanitizer.validate_output("Revenue: $4.2M", token_map)
        assert report.severity == "high"

        # Multiple leaks - critical severity
        token_map2 = TokenMap()
        token_map2.add_token("financial", "$4.2M")
        token_map2.add_token("contact", "john@example.com")
        report2 = sanitizer.validate_output("$4.2M and john@example.com", token_map2)
        assert report2.severity == "critical"


class TestModuleExports:
    """Tests for sanitization module exports."""

    def test_security_module_exports_token_map(self) -> None:
        """Test TokenMap is exported from security module."""
        from src.security import TokenMap

        token_map = TokenMap()
        assert token_map.tokens == {}

    def test_security_module_exports_leakage_report(self) -> None:
        """Test LeakageReport is exported from security module."""
        from src.security import LeakageReport

        report = LeakageReport(leaked=False, leaked_values=[], severity="none")
        assert report.leaked is False

    def test_security_module_exports_data_sanitizer(self) -> None:
        """Test DataSanitizer is exported from security module."""
        from src.security import DataSanitizer, DataClassifier

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)
        assert sanitizer.classifier is classifier


class TestIntegrationScenarios:
    """Integration tests with real-world scenarios."""

    @pytest.mark.asyncio
    async def test_financial_report_scenario(self) -> None:
        """Test sanitizing a financial report with revenue figures."""
        from src.security import DataSanitizer, DataClassifier
        from src.security.trust_levels import SkillTrustLevel

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        financial_report = {
            "company": "Acme Corp",
            "quarter": "Q4 2025",
            "summary": "Strong quarter with revenue of $4.2M and profit margin of 35%.",
            "metrics": {
                "revenue": "$4.2M",
                "profit": "$1.47M",
                "growth": "15% YoY",
            },
            "notes": "Confidential: Do not share externally.",
        }

        # Scenario 1: COMMUNITY skill (only PUBLIC access)
        sanitized, token_map = await sanitizer.sanitize(
            financial_report,
            SkillTrustLevel.COMMUNITY,
        )

        # Company and quarter are PUBLIC - unchanged
        assert sanitized["company"] == "Acme Corp"
        assert sanitized["quarter"] == "Q4 2025"

        # Financial data should be REDACTED (not tokenized)
        assert "[REDACTED:" in sanitized["summary"]
        assert "[REDACTED:" in str(sanitized["metrics"]["revenue"])
        assert "[REDACTED:" in str(sanitized["metrics"]["profit"])

        # "Confidential" marker triggers RESTRICTED classification
        assert "[REDACTED:" in sanitized["notes"]

        # Scenario 2: CORE skill (can access RESTRICTED)
        sanitized_core, token_map_core = await sanitizer.sanitize(
            financial_report,
            SkillTrustLevel.CORE,
        )

        # Financial data should be TOKENIZED (not redacted)
        assert "[FINANCIAL_" in sanitized_core["summary"]
        assert "[FINANCIAL_" in str(sanitized_core["metrics"]["revenue"])

        # Verify detokenization works
        restored = sanitizer.detokenize(sanitized_core, token_map_core)
        assert "$4.2M" in str(restored["summary"])

    @pytest.mark.asyncio
    async def test_contact_list_scenario(self) -> None:
        """Test sanitizing a contact list with emails and phones."""
        from src.security import DataSanitizer, DataClassifier
        from src.security.trust_levels import SkillTrustLevel

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        contact_list = [
            {
                "name": "John Smith",
                "title": "VP of Sales",
                "email": "john.smith@acmecorp.com",
                "phone": "555-123-4567",
                "notes": "Key decision maker",
            },
            {
                "name": "Jane Doe",
                "title": "Director of Procurement",
                "email": "jane.doe@acmecorp.com",
                "phone": "555-987-6543",
                "notes": "Budget holder, prefers email",
            },
        ]

        # VERIFIED skill can access INTERNAL but not CONFIDENTIAL
        sanitized, token_map = await sanitizer.sanitize(
            contact_list,
            SkillTrustLevel.VERIFIED,
        )

        # Names and titles are INTERNAL - accessible
        assert sanitized[0]["name"] == "John Smith"
        assert sanitized[1]["title"] == "Director of Procurement"

        # Emails and phones are CONFIDENTIAL - should be REDACTED
        assert "[REDACTED:" in sanitized[0]["email"]
        assert "[REDACTED:" in sanitized[0]["phone"]
        assert "[REDACTED:" in sanitized[1]["email"]

        # Notes don't contain sensitive patterns - unchanged
        assert sanitized[0]["notes"] == "Key decision maker"

        # Verify no leakage
        report = sanitizer.validate_output(sanitized, token_map)
        assert report.leaked is False

    @pytest.mark.asyncio
    async def test_deal_memo_scenario(self) -> None:
        """Test sanitizing a deal memo with pricing and terms."""
        from src.security import DataSanitizer, DataClassifier
        from src.security.trust_levels import SkillTrustLevel

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        deal_memo = """
        DEAL MEMO - CONFIDENTIAL

        Customer: Acme Healthcare
        Contact: Sarah Johnson (sarah.johnson@acmehc.com)
        Phone: 555-234-5678

        Deal Summary:
        - Contract value: $2.5M over 3 years
        - Our pricing: $850K/year with 10% discount
        - Competitor pricing: BioTech offers at $750K/year
        - Expected revenue impact: +15% margin improvement

        Key Terms:
        - Net 60 payment terms
        - Annual price escalator of 3%
        - Exclusivity clause for 2 years

        Notes: Customer SSN for verification: 123-45-6789
        """

        # COMMUNITY skill - only PUBLIC access
        sanitized, token_map = await sanitizer.sanitize(
            deal_memo,
            SkillTrustLevel.COMMUNITY,
        )

        # All sensitive data should be redacted
        assert "sarah.johnson@acmehc.com" not in sanitized
        assert "555-234-5678" not in sanitized
        assert "$2.5M" not in sanitized
        assert "$850K" not in sanitized
        assert "123-45-6789" not in sanitized

        # SSN should be redacted (not tokenized)
        assert "[REDACTED:" in sanitized

        # CORE skill - full access except REGULATED
        sanitized_core, token_map_core = await sanitizer.sanitize(
            deal_memo,
            SkillTrustLevel.CORE,
        )

        # Financial data should be tokenized
        assert "[FINANCIAL_" in sanitized_core
        assert "[CONTACT_" in sanitized_core

        # SSN (REGULATED) should still be redacted for CORE
        assert "123-45-6789" not in sanitized_core
        assert "[REDACTED:" in sanitized_core  # SSN redaction

        # Verify detokenization restores financial and contact but not SSN
        restored = sanitizer.detokenize(sanitized_core, token_map_core)
        assert "$2.5M" in restored or "2.5M" in restored  # Financial restored
        assert "123-45-6789" not in restored  # SSN stays redacted

    @pytest.mark.asyncio
    async def test_mixed_classification_levels(self) -> None:
        """Test data with multiple classification levels."""
        from src.security import DataSanitizer, DataClassifier
        from src.security.trust_levels import SkillTrustLevel

        classifier = DataClassifier()
        sanitizer = DataSanitizer(classifier)

        mixed_data = {
            "public": {
                "company_name": "BioPharm Inc",
                "industry": "Life Sciences",
                "website": "https://biopharm.com",
            },
            "internal": {
                "strategy": "Focus on oncology market",
                "goals": "Increase market share by 20%",
            },
            "confidential": {
                "key_contact": "Dr. Smith (dr.smith@biopharm.com)",
                "phone": "555-111-2222",
            },
            "restricted": {
                "revenue": "$45M annually",
                "deal_pipeline": "$12M in active deals",
                "proprietary": "Novel drug delivery mechanism",
            },
            "regulated": {
                "patient_data": "Patient ID: 12345, diagnosis: stage 2",
                "ssn": "987-65-4321",
            },
        }

        # Test each trust level
        trust_levels = [
            (SkillTrustLevel.COMMUNITY, {"public"}),
            (SkillTrustLevel.USER, {"public", "internal"}),
            (SkillTrustLevel.VERIFIED, {"public", "internal"}),
            (SkillTrustLevel.CORE, {"public", "internal", "confidential", "restricted"}),
        ]

        for trust_level, accessible_categories in trust_levels:
            sanitized, token_map = await sanitizer.sanitize(mixed_data, trust_level)

            # Public data always accessible
            assert sanitized["public"]["company_name"] == "BioPharm Inc"

            # Check confidential
            if "confidential" in accessible_categories:
                assert "[CONTACT_" in sanitized["confidential"]["key_contact"]
            else:
                assert "[REDACTED:" in sanitized["confidential"]["key_contact"]

            # Check restricted
            if "restricted" in accessible_categories:
                assert "[FINANCIAL_" in str(sanitized["restricted"]["revenue"])
            else:
                assert "[REDACTED:" in str(sanitized["restricted"]["revenue"])

            # Regulated never accessible to any trust level
            assert "[REDACTED:" in sanitized["regulated"]["ssn"]
            assert "987-65-4321" not in str(sanitized)
