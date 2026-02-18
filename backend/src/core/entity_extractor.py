"""Extract entity names from OODA observations for graph traversal.

Uses regex-based extraction to identify company and person names
from structured observation data without LLM calls.
"""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# Company name suffixes (used to anchor multi-word company names)
_COMPANY_SUFFIXES = (
    "Inc",
    "Corp",
    "Ltd",
    "Co",
    "Pharma",
    "Bio",
    "Labs",
    "Med",
    "Therapeutics",
    "Sciences",
    "Diagnostics",
    "Healthcare",
)
# Pattern 1: Multi-word name ending with a known company suffix
# e.g., "Meridian Pharma", "GenMark Diagnostics", "Alpha Corp"
_SUFFIXES_RE = "|".join(re.escape(s) for s in _COMPANY_SUFFIXES)
_COMPANY_WITH_SUFFIX = re.compile(
    rf"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+){{0,2}}\s+(?:{_SUFFIXES_RE}))\b"
)

# Pattern 2: CamelCase / internal-cap words (BioGenix, WuXi, GenMark)
# Must have at least one lowercase-to-uppercase transition after the first char
_CAMEL_CASE = re.compile(r"\b([A-Z][a-z]+[A-Z][a-zA-Z]*)\b")

# Pattern 3: Standalone capitalized words that are 6+ characters
# Catches "Novartis", "Roche", etc. — filtered by stop words
_CAPITALIZED_WORD = re.compile(r"\b([A-Z][a-zA-Z]{5,})\b")

# Words to exclude (common English words that match capitalized patterns)
_STOP_WORDS = frozenset(
    {
        "The",
        "This",
        "That",
        "These",
        "Those",
        "With",
        "From",
        "Into",
        "About",
        "After",
        "Before",
        "Between",
        "Under",
        "Over",
        "Through",
        "During",
        "Without",
        "Within",
        "Along",
        "Among",
        "Upon",
        "Since",
        "Until",
        "Against",
        "Toward",
        "Active",
        "Goal",
        "User",
        "Status",
        "Type",
        "Data",
        "Source",
        "None",
        "True",
        "False",
        "Note",
        "Update",
        "Recent",
        "Current",
        "New",
        "Other",
        "First",
        "Last",
        "Next",
        "Meeting",
        "Email",
        "Call",
        "Task",
        "Plan",
        "Report",
        "Summary",
        "Description",
        "Title",
        "Priority",
        "High",
        "Medium",
        "Low",
        "Unknown",
        "Analyzed",
        "Gathered",
        "Focus",
        "Observations",
        "Output",
        "JSON",
        "ARIA",
        "Claude",
        "Close",
        "Companies",
        "Active Goal",
        "VP Sales",
    }
)


def extract_entities_from_observations(
    observations: list[dict[str, Any]],
    max_entities: int = 5,
) -> list[str]:
    """Extract entity names from OODA observations.

    Scans observation text for company and person names using
    regex patterns. No LLM calls -- purely pattern-based.

    Args:
        observations: List of observation dicts from OODA Observe phase.
        max_entities: Maximum entities to return (bounds graph queries).

    Returns:
        Deduplicated list of entity name strings, most-mentioned first.
    """
    if not observations:
        return []

    # Collect all text from observations
    text_parts: list[str] = []
    for obs in observations:
        _collect_text(obs.get("data"), text_parts)

    if not text_parts:
        return []

    combined_text = " ".join(text_parts)

    # Extract candidates with priority scoring
    # Higher score = more likely a real entity
    candidates: dict[str, int] = {}

    # Pass 1: Company names with known suffixes (highest confidence)
    for match in _COMPANY_WITH_SUFFIX.finditer(combined_text):
        name = match.group(1).strip()
        if not _is_stop(name):
            candidates[name] = candidates.get(name, 0) + 3

    # Pass 2: CamelCase words (high confidence — BioGenix, WuXi)
    for match in _CAMEL_CASE.finditer(combined_text):
        name = match.group(1).strip()
        if not _is_stop(name):
            candidates[name] = candidates.get(name, 0) + 3

    # Pass 3: Standalone capitalized long words (medium confidence — Novartis)
    for match in _CAPITALIZED_WORD.finditer(combined_text):
        name = match.group(1).strip()
        if not _is_stop(name):
            candidates[name] = candidates.get(name, 0) + 1

    # Sort by score (highest first), then alphabetically for ties
    sorted_entities = sorted(candidates.keys(), key=lambda e: (-candidates[e], e))

    return sorted_entities[:max_entities]


def _is_stop(name: str) -> bool:
    """Check if a name is a stop word or composed entirely of stop words."""
    if name in _STOP_WORDS:
        return True
    # Check each word in multi-word names
    words = name.split()
    return bool(all(w in _STOP_WORDS for w in words))


def _collect_text(data: Any, parts: list[str]) -> None:
    """Recursively extract text strings from observation data."""
    if data is None:
        return
    if isinstance(data, str):
        parts.append(data)
    elif isinstance(data, dict):
        for value in data.values():
            _collect_text(value, parts)
    elif isinstance(data, list):
        for item in data:
            _collect_text(item, parts)
