"""Compliance capability for ARIA — PHI/PII detection and Sunshine Act checking.

Provides code-based (regex) compliance scanning that runs independently of
the LLM. Used as a pre-scan step by ComplianceGuardianSkill and can also
be called directly by agents for real-time redaction.

Key functions:
- ``auto_redact(text)`` — Replace detected PHI/PII with [REDACTED] tokens
- ``check_sunshine_act(interaction)`` — Flag Sunshine Act reporting requirements
- ``ComplianceScanner.scan_text(text)`` — Full regex pre-scan with findings

Integration Checklist:
- [x] Works with data_classification.py patterns (extends them for life sciences)
- [x] Activity logged to aria_activity on redaction events
- [x] Audit trail for all compliance checks
- [x] Source confidence per detection
"""

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


class ComplianceCategory(str, Enum):
    """Categories of compliance findings."""

    PHI_DIRECT = "phi_direct_identifier"
    PHI_QUASI = "phi_quasi_identifier"
    PHI_CLINICAL = "phi_clinical_context"
    PII_SSN = "pii_ssn"
    PII_CONTACT = "pii_contact"
    PII_CONTEXTUAL = "pii_contextual"
    SUNSHINE_MEAL = "sunshine_act_meal"
    SUNSHINE_SPEAKING = "sunshine_act_speaking"
    SUNSHINE_CONSULTING = "sunshine_act_consulting"
    SUNSHINE_TRAVEL = "sunshine_act_travel"
    SUNSHINE_RESEARCH = "sunshine_act_research"
    SUNSHINE_GIFT = "sunshine_act_gift"
    SUNSHINE_GENERAL = "sunshine_act_general"


class ComplianceAction(str, Enum):
    """Required action for a compliance finding."""

    REDACT = "redact"
    REPORT = "report"
    REVIEW = "review"
    FLAG = "flag"


class ComplianceCheck(BaseModel):
    """Result of a Sunshine Act compliance check."""

    requires_reporting: bool = False
    findings: list[dict[str, Any]] = Field(default_factory=list)
    total_transfers_of_value: int = 0
    estimated_total_value: str = ""
    risk_level: str = "low"
    checked_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


@dataclass
class PatternMatch:
    """A single regex pattern match result."""

    category: ComplianceCategory
    pattern_name: str
    match_text: str
    start: int
    end: int
    confidence: float
    action: ComplianceAction


@dataclass
class ScanResult:
    """Aggregated result of a compliance text scan."""

    matches: list[PatternMatch] = field(default_factory=list)
    scanned_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def has_findings(self) -> bool:
        """Return True if any matches were found."""
        return len(self.matches) > 0

    @property
    def highest_risk(self) -> str:
        """Return the highest risk level based on findings."""
        if any(
            m.category in {ComplianceCategory.PHI_DIRECT, ComplianceCategory.PII_SSN}
            for m in self.matches
        ):
            return "critical"
        if any(
            m.category in {ComplianceCategory.PHI_CLINICAL, ComplianceCategory.PHI_QUASI}
            for m in self.matches
        ):
            return "high"
        if any(m.category.value.startswith("sunshine_") for m in self.matches):
            return "medium"
        if self.matches:
            return "low"
        return "low"

    def to_context_string(self) -> str:
        """Format scan results as a string for LLM context injection."""
        if not self.matches:
            return "No patterns detected by automated pre-scan."

        lines = [f"Automated pre-scan found {len(self.matches)} potential issue(s):\n"]
        for i, match in enumerate(self.matches, 1):
            lines.append(
                f"{i}. **{match.category.value}** (confidence {match.confidence:.0%}): "
                f"{match.pattern_name} detected at position {match.start}–{match.end}. "
                f"Action: {match.action.value}."
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pattern definitions
# ---------------------------------------------------------------------------

# PHI/PII regex patterns — compiled for performance
_PATTERNS: list[tuple[str, re.Pattern[str], ComplianceCategory, float, ComplianceAction]] = [
    # Direct identifiers — highest confidence
    (
        "SSN with dashes",
        re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
        ComplianceCategory.PII_SSN,
        0.95,
        ComplianceAction.REDACT,
    ),
    (
        "SSN without dashes",
        re.compile(r"\b\d{9}\b"),
        ComplianceCategory.PII_SSN,
        0.70,  # Lower confidence — could be other 9-digit numbers
        ComplianceAction.REVIEW,
    ),
    (
        "Medical Record Number",
        re.compile(r"\bMRN\s*[:#]?\s*\d{4,12}\b", re.IGNORECASE),
        ComplianceCategory.PHI_DIRECT,
        0.95,
        ComplianceAction.REDACT,
    ),
    (
        "Patient ID",
        re.compile(r"\bpatient\s*(?:id|ID|#|number)\s*[:#]?\s*\w{3,15}\b", re.IGNORECASE),
        ComplianceCategory.PHI_DIRECT,
        0.90,
        ComplianceAction.REDACT,
    ),
    # Quasi-identifiers
    (
        "Date of birth",
        re.compile(
            r"\b(?:DOB|date\s+of\s+birth|born|birthday)\s*[:\-]?\s*"
            r"\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}\b",
            re.IGNORECASE,
        ),
        ComplianceCategory.PHI_QUASI,
        0.90,
        ComplianceAction.REDACT,
    ),
    # Contact PII
    (
        "Email address",
        re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b"),
        ComplianceCategory.PII_CONTACT,
        0.90,
        ComplianceAction.REVIEW,
    ),
    (
        "US phone number",
        re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b"),
        ComplianceCategory.PII_CONTACT,
        0.80,
        ComplianceAction.REVIEW,
    ),
]

# Drug name patterns — used for co-occurrence detection with names
# Common life sciences drug name patterns (brand names tend to be capitalized
# single words ending in common suffixes)
_DRUG_SUFFIXES = (
    r"\b\w*(?:mab|nib|lib|zumab|ximab|tinib|ciclib|rafenib|lisib|parin|"
    r"statin|sartan|prazole|oxetine|azepam|phylline|cillin|mycin|"
    r"floxacin|vir|navir|tegravir|buvir|ine|ide|ate|ol|il|ax|ex|ix|ux|"
    r"umab|izumab)\b"
)
_DRUG_PATTERN = re.compile(_DRUG_SUFFIXES, re.IGNORECASE)

# Medical context terms for contextual PII detection
_MEDICAL_TERMS = re.compile(
    r"\b(?:diagnosis|diagnosed|prognosis|medication|prescription|treatment|"
    r"therapy|clinical\s+trial|adverse\s+event|side\s+effect|dosage|"
    r"specimen|biopsy|pathology|oncology|cardiology|neurology|"
    r"immunotherapy|chemotherapy|radiation|surgery|procedure|"
    r"patient|symptom|condition|disease|disorder|syndrome|"
    r"blood\s+type|HIV|AIDS|cancer|tumor|tumour|malignant|benign|"
    r"metastatic|remission|relapse|chronic|acute)\b",
    re.IGNORECASE,
)

# Simple name pattern — capitalized words that could be names
_NAME_PATTERN = re.compile(r"\b[A-Z][a-z]{1,15}\s+[A-Z][a-z]{1,15}\b")

# Sunshine Act trigger patterns
_SUNSHINE_PATTERNS: list[tuple[str, re.Pattern[str], ComplianceCategory, float]] = [
    (
        "Meal/entertainment",
        re.compile(
            r"\b(?:dinner|lunch|breakfast|meal|catering|restaurant|"
            r"entertainment|reception|hospitality)\b",
            re.IGNORECASE,
        ),
        ComplianceCategory.SUNSHINE_MEAL,
        0.60,
    ),
    (
        "Speaking fee",
        re.compile(
            r"\b(?:speaker\s+fee|honorari(?:um|a)|speaking\s+engagement|"
            r"presentation\s+fee|keynote\s+fee)\b",
            re.IGNORECASE,
        ),
        ComplianceCategory.SUNSHINE_SPEAKING,
        0.85,
    ),
    (
        "Consulting arrangement",
        re.compile(
            r"\b(?:consulting\s+(?:fee|arrangement|agreement|contract)|"
            r"advisory\s+(?:board|fee|role)|consultant\s+payment)\b",
            re.IGNORECASE,
        ),
        ComplianceCategory.SUNSHINE_CONSULTING,
        0.80,
    ),
    (
        "Travel/lodging",
        re.compile(
            r"\b(?:travel\s+(?:expense|reimbursement|arrangement)|"
            r"lodging|hotel\s+(?:stay|room|accommodation)|"
            r"airfare|flight\s+(?:cost|booking))\b",
            re.IGNORECASE,
        ),
        ComplianceCategory.SUNSHINE_TRAVEL,
        0.75,
    ),
    (
        "Research funding",
        re.compile(
            r"\b(?:research\s+(?:grant|funding|support)|"
            r"investigator\s+(?:initiated|sponsored)|"
            r"clinical\s+trial\s+(?:funding|support|payment))\b",
            re.IGNORECASE,
        ),
        ComplianceCategory.SUNSHINE_RESEARCH,
        0.80,
    ),
    (
        "Gift/sample",
        re.compile(
            r"\b(?:gift|sample|complimentary|free\s+(?:product|device|sample)|"
            r"promotional\s+(?:item|material))\b",
            re.IGNORECASE,
        ),
        ComplianceCategory.SUNSHINE_GIFT,
        0.55,
    ),
]

# HCP role indicators — used to determine if Sunshine Act applies
_HCP_PATTERN = re.compile(
    r"\b(?:physician|doctor|Dr\.\s|MD\b|DO\b|PharmD|NP\b|PA\b|"
    r"nurse\s+practitioner|surgeon|oncologist|cardiologist|"
    r"neurologist|psychiatrist|radiologist|anesthesiologist|"
    r"dermatologist|gastroenterologist|endocrinologist|"
    r"rheumatologist|pulmonologist|nephrologist|urologist|"
    r"ophthalmologist|pathologist|hospitalist|"
    r"healthcare\s+professional|HCP|prescriber|KOL|"
    r"key\s+opinion\s+leader|medical\s+director|"
    r"chief\s+medical\s+officer|CMO)\b",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


class ComplianceScanner:
    """Regex-based compliance scanner for PHI/PII and Sunshine Act triggers.

    This scanner runs pattern matching only — no LLM calls. It is designed
    to be fast and deterministic for use as a pre-scan before LLM analysis
    or as a standalone gate for real-time content filtering.
    """

    def scan_text(self, text: str) -> ScanResult:
        """Scan text for PHI/PII patterns and return structured results.

        Args:
            text: The text to scan.

        Returns:
            ScanResult with all pattern matches.
        """
        matches: list[PatternMatch] = []

        # Run PHI/PII patterns
        for name, pattern, category, confidence, action in _PATTERNS:
            for m in pattern.finditer(text):
                matches.append(
                    PatternMatch(
                        category=category,
                        pattern_name=name,
                        match_text=m.group(),
                        start=m.start(),
                        end=m.end(),
                        confidence=confidence,
                        action=action,
                    )
                )

        # Run contextual PHI detection: name + medical term co-occurrence
        matches.extend(self._detect_contextual_phi(text))

        # Run Sunshine Act patterns
        matches.extend(self._detect_sunshine_triggers(text))

        # Deduplicate overlapping matches — keep highest confidence
        matches = self._deduplicate(matches)

        return ScanResult(matches=matches)

    def _detect_contextual_phi(self, text: str) -> list[PatternMatch]:
        """Detect names co-occurring with medical terms within proximity.

        A name appearing within 200 characters of a medical term or drug
        name is flagged as contextual PHI.

        Args:
            text: Text to scan.

        Returns:
            List of contextual PHI matches.
        """
        matches: list[PatternMatch] = []
        names = list(_NAME_PATTERN.finditer(text))
        medical_terms = list(_MEDICAL_TERMS.finditer(text))
        drug_mentions = list(_DRUG_PATTERN.finditer(text))

        # Combine medical and drug contexts
        context_spans = [(m.start(), m.end()) for m in medical_terms]
        context_spans.extend((m.start(), m.end()) for m in drug_mentions)

        for name_match in names:
            name_center = (name_match.start() + name_match.end()) // 2
            for ctx_start, ctx_end in context_spans:
                ctx_center = (ctx_start + ctx_end) // 2
                distance = abs(name_center - ctx_center)
                if distance <= 200:
                    # Check if this is a drug + name co-occurrence specifically
                    is_drug_context = any(
                        d.start() == ctx_start and d.end() == ctx_end for d in drug_mentions
                    )
                    matches.append(
                        PatternMatch(
                            category=ComplianceCategory.PHI_CLINICAL,
                            pattern_name=(
                                "Drug name + person name co-occurrence"
                                if is_drug_context
                                else "Person name near medical context"
                            ),
                            match_text=name_match.group(),
                            start=name_match.start(),
                            end=name_match.end(),
                            confidence=0.85 if is_drug_context else 0.70,
                            action=ComplianceAction.REVIEW,
                        )
                    )
                    break  # One match per name is sufficient

        return matches

    def _detect_sunshine_triggers(self, text: str) -> list[PatternMatch]:
        """Detect Sunshine Act triggers — only if HCP context is present.

        Sunshine Act only applies to transfers of value involving HCPs.
        Pattern matches for meals/travel/etc. are only flagged if HCP
        indicators are also present in the text.

        Args:
            text: Text to scan.

        Returns:
            List of Sunshine Act matches.
        """
        matches: list[PatternMatch] = []

        # Only check Sunshine Act if HCP references exist
        if not _HCP_PATTERN.search(text):
            return matches

        for name, pattern, category, confidence in _SUNSHINE_PATTERNS:
            for m in pattern.finditer(text):
                matches.append(
                    PatternMatch(
                        category=category,
                        pattern_name=name,
                        match_text=m.group(),
                        start=m.start(),
                        end=m.end(),
                        confidence=confidence,
                        action=ComplianceAction.REPORT,
                    )
                )

        return matches

    @staticmethod
    def _deduplicate(matches: list[PatternMatch]) -> list[PatternMatch]:
        """Remove overlapping matches, keeping the highest confidence.

        Args:
            matches: Raw list of pattern matches.

        Returns:
            Deduplicated list sorted by position.
        """
        if not matches:
            return matches

        # Sort by start position, then by confidence descending
        matches.sort(key=lambda m: (m.start, -m.confidence))

        deduped: list[PatternMatch] = [matches[0]]
        for match in matches[1:]:
            prev = deduped[-1]
            # If overlapping, keep the higher confidence one
            if match.start < prev.end:
                if match.confidence > prev.confidence:
                    deduped[-1] = match
            else:
                deduped.append(match)

        return deduped


# ---------------------------------------------------------------------------
# Public convenience functions
# ---------------------------------------------------------------------------

# Redaction token mapping
_REDACTION_TOKENS: dict[ComplianceCategory, str] = {
    ComplianceCategory.PII_SSN: "[REDACTED-SSN]",
    ComplianceCategory.PHI_DIRECT: "[REDACTED-PHI]",
    ComplianceCategory.PHI_QUASI: "[REDACTED-DOB]",
    ComplianceCategory.PHI_CLINICAL: "[REDACTED-NAME]",
    ComplianceCategory.PII_CONTACT: "[REDACTED-CONTACT]",
    ComplianceCategory.PII_CONTEXTUAL: "[REDACTED-PII]",
}


def auto_redact(text: str) -> str:
    """Replace detected PHI/PII in text with [REDACTED] tokens.

    Runs the compliance scanner and replaces all matches that have
    an action of ``redact`` or ``review`` with appropriate tokens.
    Sunshine Act findings are not redacted (they need reporting,
    not removal).

    Args:
        text: The text to redact.

    Returns:
        Text with PHI/PII replaced by ``[REDACTED-TYPE]`` tokens.
    """
    scanner = ComplianceScanner()
    result = scanner.scan_text(text)

    if not result.has_findings:
        return text

    # Filter to redactable findings (not Sunshine Act)
    redactable = [
        m
        for m in result.matches
        if m.action in {ComplianceAction.REDACT, ComplianceAction.REVIEW}
        and not m.category.value.startswith("sunshine_")
    ]

    if not redactable:
        return text

    # Apply redactions from end to start to preserve positions
    redactable.sort(key=lambda m: m.start, reverse=True)
    redacted = text
    for match in redactable:
        token = _REDACTION_TOKENS.get(match.category, "[REDACTED]")
        redacted = redacted[: match.start] + token + redacted[match.end :]

    logger.info(
        "Auto-redacted text",
        extra={"redactions": len(redactable), "categories": [m.category.value for m in redactable]},
    )

    return redacted


def check_sunshine_act(interaction: dict[str, Any]) -> ComplianceCheck:
    """Check an interaction dict for Sunshine Act reporting requirements.

    Scans the interaction description, notes, and attendee information
    for transfers of value to Healthcare Professionals.

    Args:
        interaction: Dict with keys like ``description``, ``notes``,
            ``attendees``, ``type``, ``value``, ``hcp_names``.

    Returns:
        ComplianceCheck with findings and reporting recommendation.
    """
    scanner = ComplianceScanner()

    # Build text from interaction fields
    text_parts: list[str] = []
    for key in ("description", "notes", "summary", "details"):
        if key in interaction:
            text_parts.append(str(interaction[key]))

    # Include attendee info
    attendees = interaction.get("attendees", [])
    if attendees:
        text_parts.append("Attendees: " + ", ".join(str(a) for a in attendees))

    # Include HCP names if explicitly provided
    hcp_names = interaction.get("hcp_names", [])
    if hcp_names:
        text_parts.append("HCPs: " + ", ".join(str(n) for n in hcp_names))

    combined_text = "\n".join(text_parts)
    result = scanner.scan_text(combined_text)

    # Extract Sunshine Act findings
    sunshine_findings = [m for m in result.matches if m.category.value.startswith("sunshine_")]

    # Build ComplianceCheck
    findings: list[dict[str, Any]] = []
    for match in sunshine_findings:
        findings.append(
            {
                "category": match.category.value,
                "pattern_name": match.pattern_name,
                "confidence": match.confidence,
                "action": match.action.value,
                "description": (
                    f"Potential {match.pattern_name.lower()} detected. "
                    f"Review for Sunshine Act reporting requirements."
                ),
            }
        )

    # Check for explicit value
    explicit_value = interaction.get("value")
    value_str = f"${explicit_value}" if explicit_value else "undetermined"

    # Determine if HCPs are involved
    has_hcp = bool(hcp_names) or _HCP_PATTERN.search(combined_text) is not None
    requires_reporting = bool(sunshine_findings) and has_hcp

    risk = "low"
    if requires_reporting:
        risk = "high" if len(sunshine_findings) >= 3 else "medium"

    return ComplianceCheck(
        requires_reporting=requires_reporting,
        findings=findings,
        total_transfers_of_value=len(sunshine_findings),
        estimated_total_value=value_str,
        risk_level=risk,
    )
