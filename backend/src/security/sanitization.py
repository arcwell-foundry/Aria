"""Data sanitization pipeline for ARIA skill security.

Tokenizes, redacts, and validates data based on skill trust levels
before any data reaches external skills.
"""

import re
from dataclasses import dataclass, field
from typing import Any

from src.security.data_classification import ClassifiedData, DataClass, DataClassifier
from src.security.trust_levels import SkillTrustLevel, can_access_data


@dataclass
class TokenMap:
    """Maps token strings to their original values.

    Tokens use format [DATA_TYPE_NNN] e.g. [FINANCIAL_001], [CONTACT_002].
    Maintains bidirectional mapping for tokenization and detokenization.

    Attributes:
        tokens: Dict mapping token strings to original values.
    """

    tokens: dict[str, Any] = field(default_factory=dict)
    _counters: dict[str, int] = field(default_factory=dict)

    def add_token(self, data_type: str, value: Any) -> str:
        """Add a value to the token map and return its token string.

        Args:
            data_type: Category of data (e.g., "financial", "contact").
            value: The original value to tokenize.

        Returns:
            Token string in format [DATA_TYPE_NNN].
        """
        normalized_type = data_type.upper()
        self._counters[normalized_type] = self._counters.get(normalized_type, 0) + 1
        counter = self._counters[normalized_type]
        token = f"[{normalized_type}_{counter:03d}]"
        self.tokens[token] = value
        return token

    def get_original(self, token: str) -> Any | None:
        """Get the original value for a token.

        Args:
            token: The token string to look up.

        Returns:
            The original value, or None if token not found.
        """
        return self.tokens.get(token)


@dataclass
class LeakageReport:
    """Report of potential data leakage in skill output.

    Attributes:
        leaked: Whether any sensitive data was found in output.
        leaked_values: List of leaked values that were detected.
        severity: Severity level - "none", "low", "medium", "high", "critical".
    """

    leaked: bool
    leaked_values: list[Any]
    severity: str


class DataSanitizer:
    """Sanitizes data for skill execution based on trust levels."""

    def __init__(self, classifier: DataClassifier) -> None:
        """Initialize DataSanitizer with a classifier."""
        self.classifier = classifier

    def tokenize_value(self, value: Any, data_type: str, token_map: TokenMap) -> str:
        """Replace a sensitive value with a token."""
        return token_map.add_token(data_type, value)

    def redact_value(self, classified_data: ClassifiedData) -> str:
        """Redact a classified value completely."""
        return f"[REDACTED: {classified_data.data_type}]"

    async def sanitize(
        self,
        data: Any,
        skill_trust_level: SkillTrustLevel,
        context: dict[str, Any] | None = None,
    ) -> tuple[Any, TokenMap]:
        """Sanitize data for skill execution.

        Args:
            data: The data to sanitize (string, dict, list, or other).
            skill_trust_level: The trust level of the skill that will receive this data.
            context: Optional context about the data source.

        Returns:
            Tuple of (sanitized_data, token_map) where token_map allows detokenization.
        """
        if context is None:
            context = {}

        token_map = TokenMap()
        sanitized = await self._sanitize_recursive(data, skill_trust_level, context, token_map)
        return sanitized, token_map

    async def _sanitize_recursive(
        self,
        data: Any,
        skill_trust_level: SkillTrustLevel,
        context: dict[str, Any],
        token_map: TokenMap,
    ) -> Any:
        """Recursively sanitize data structures.

        Args:
            data: The data to sanitize.
            skill_trust_level: The trust level of the skill.
            context: Context about the data source.
            token_map: The token map to store mappings in.

        Returns:
            The sanitized data.
        """
        if isinstance(data, str):
            result, _ = await self._sanitize_string(data, skill_trust_level, context, token_map)
            return result

        if isinstance(data, dict):
            return {
                key: await self._sanitize_recursive(value, skill_trust_level, context, token_map)
                for key, value in data.items()
            }

        if isinstance(data, list):
            return [
                await self._sanitize_recursive(item, skill_trust_level, context, token_map)
                for item in data
            ]

        if data is None:
            return None

        classified = await self.classifier.classify(data, context)
        result, _ = self._handle_classified_data(classified, skill_trust_level, token_map)
        return result

    async def _sanitize_string(
        self,
        text: str,
        skill_trust_level: SkillTrustLevel,
        context: dict[str, Any],
        token_map: TokenMap,
    ) -> tuple[str, TokenMap]:
        """Sanitize a string by finding and replacing sensitive patterns.

        Args:
            text: The string to sanitize.
            skill_trust_level: The trust level of the skill.
            context: Context about the data source.
            token_map: The token map to store mappings in.

        Returns:
            Tuple of (sanitized_string, token_map).
        """
        result = text

        # Check all patterns from most to least sensitive
        for classification in [DataClass.REGULATED, DataClass.RESTRICTED, DataClass.CONFIDENTIAL]:
            patterns = self.classifier.PATTERNS.get(classification, [])
            for pattern in patterns:
                matches = list(re.finditer(pattern, result, re.IGNORECASE))
                for match in reversed(matches):  # Reverse to preserve positions
                    matched_text = match.group()
                    data_type = self.classifier._infer_data_type(pattern)
                    can_tokenize = self.classifier._can_be_tokenized(pattern)

                    classified = ClassifiedData(
                        data=matched_text,
                        classification=classification,
                        data_type=data_type,
                        source=context.get("source", "unknown"),
                        can_be_tokenized=can_tokenize,
                    )

                    has_access = can_access_data(skill_trust_level, classification)

                    if has_access and can_tokenize:
                        replacement = self.tokenize_value(matched_text, data_type, token_map)
                    else:
                        replacement = self.redact_value(classified)

                    result = result[: match.start()] + replacement + result[match.end() :]

        return result, token_map

    def _handle_classified_data(
        self,
        classified: ClassifiedData,
        skill_trust_level: SkillTrustLevel,
        token_map: TokenMap,
    ) -> tuple[Any, TokenMap]:
        """Handle pre-classified data based on trust level.

        Args:
            classified: The pre-classified data.
            skill_trust_level: The trust level of the skill.
            token_map: The token map to store mappings in.

        Returns:
            Tuple of (processed_data, token_map).
        """
        has_access = can_access_data(skill_trust_level, classified.classification)

        if has_access and classified.can_be_tokenized:
            token = self.tokenize_value(classified.data, classified.data_type, token_map)
            return token, token_map
        elif not has_access or not classified.can_be_tokenized:
            return self.redact_value(classified), token_map

        return classified.data, token_map

    def detokenize(self, output: Any, token_map: TokenMap) -> Any:
        """Restore tokenized values in skill output.

        Args:
            output: The output data containing tokens to restore.
            token_map: The token map containing token-to-value mappings.

        Returns:
            The output with tokens replaced by original values.
        """
        return self._detokenize_recursive(output, token_map)

    def _detokenize_recursive(self, data: Any, token_map: TokenMap) -> Any:
        """Recursively detokenize data structures.

        Args:
            data: The data to detokenize.
            token_map: The token map containing token-to-value mappings.

        Returns:
            The data with tokens replaced by original values.
        """
        if isinstance(data, str):
            result = data
            for token, original in token_map.tokens.items():
                result = result.replace(token, str(original))
            return result

        if isinstance(data, dict):
            return {
                key: self._detokenize_recursive(value, token_map)
                for key, value in data.items()
            }

        if isinstance(data, list):
            return [
                self._detokenize_recursive(item, token_map)
                for item in data
            ]

        return data

    def validate_output(self, output: Any, token_map: TokenMap) -> LeakageReport:
        """Validate skill output for data leakage.

        Checks whether any original values that were tokenized appear in the
        skill output, which would indicate potential data leakage.

        Args:
            output: The skill output to validate.
            token_map: The token map containing original values to check for.

        Returns:
            LeakageReport indicating if any sensitive data was leaked.
        """
        leaked_values: list[Any] = []

        output_str = self._to_string_for_scan(output)

        for token, original in token_map.tokens.items():
            original_str = str(original)
            if original_str in output_str:
                leaked_values.append(original)

        if len(leaked_values) == 0:
            severity = "none"
        elif len(leaked_values) == 1:
            severity = "high"
        else:
            severity = "critical"

        return LeakageReport(
            leaked=len(leaked_values) > 0,
            leaked_values=leaked_values,
            severity=severity,
        )

    def _to_string_for_scan(self, data: Any) -> str:
        """Convert data structure to string for leakage scanning.

        Args:
            data: The data to convert.

        Returns:
            String representation suitable for substring searching.
        """
        if isinstance(data, str):
            return data

        if isinstance(data, dict):
            parts = [self._to_string_for_scan(v) for v in data.values()]
            return " ".join(parts)

        if isinstance(data, list):
            parts = [self._to_string_for_scan(item) for item in data]
            return " ".join(parts)

        return str(data) if data is not None else ""
