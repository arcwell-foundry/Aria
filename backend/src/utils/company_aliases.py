"""
Dynamic company name normalization.

Builds alias mappings from the user's battle_cards table rather than
hardcoded dictionaries. Falls back to basic suffix-stripping when
no DB context is available.

Usage:
    from src.utils.company_aliases import normalize_company_name

    # Basic mode (no DB):
    canonical = normalize_company_name("Sartorius AG")  # -> "Sartorius"

    # Dynamic mode (with DB):
    canonical = normalize_company_name(
        "Thermo Fisher Scientific",
        company_id="...",
        supabase_client=db,
    )
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

# In-process cache (per company_id). Cleared on restart or explicit clear_cache().
_alias_cache: dict[str, dict[str, str]] = {}
_person_cache: dict[str, dict[str, str]] = {}

# Common corporate suffixes to strip in basic mode
_CORPORATE_SUFFIXES = (
    " Inc", " Inc.", " Corp", " Corp.", " Corporation",
    " Ltd", " Ltd.", " AG", " SE", " GmbH", " S.A.",
    " PLC", " plc", " N.V.", " S.p.A.",
)


def normalize_company_name(
    name: str | None,
    company_id: str | None = None,
    supabase_client: Any | None = None,
) -> str:
    """Return the canonical company name, handling aliases and known people.

    If company_id and supabase_client are provided, dynamically builds an
    alias mapping from the battle_cards table. Otherwise falls back to
    basic normalization (strip corporate suffixes).

    Args:
        name: The company name to normalize (may be None or empty).
        company_id: UUID of the user's company (enables dynamic aliases).
        supabase_client: Supabase client instance for DB queries.

    Returns:
        The canonical company name, or the cleaned original if no mapping exists.
    """
    if not name:
        return name or ""

    # Dynamic mode: look up aliases from battle_cards
    if company_id and supabase_client:
        person_map = _get_or_build_person_map(company_id, supabase_client)
        aliases = _get_or_build_aliases(company_id, supabase_client)

        # Check person mapping first (higher priority)
        if name in person_map:
            return person_map[name]

        # Check alias mapping (exact match)
        if name in aliases:
            return aliases[name]

        # Case-insensitive fallback
        name_lower = name.lower().strip()
        for person, company in person_map.items():
            if person.lower() == name_lower:
                return company
        for variant, canonical in aliases.items():
            if variant.lower() == name_lower:
                return canonical

    # Basic mode: strip common corporate suffixes
    cleaned = name.strip()
    for suffix in _CORPORATE_SUFFIXES:
        if cleaned.endswith(suffix):
            cleaned = cleaned[: -len(suffix)].strip()
            break

    return cleaned


def get_signal_company_names_for_battle_card(
    battle_card_name: str,
    company_id: str | None = None,
    db: Any | None = None,
) -> list[str]:
    """Return all company_name variants that map to this battle card.

    Useful when querying market_signals for signals related to a specific
    battle card, since historical signals may use variant names.

    Args:
        battle_card_name: The canonical competitor name from battle_cards.
        company_id: UUID of the user's company (enables dynamic aliases).
        db: Supabase client instance.

    Returns:
        List of all variant names (including the canonical name).
    """
    names = [battle_card_name]

    if company_id and db:
        aliases = _get_or_build_aliases(company_id, db)
        for variant, canonical in aliases.items():
            if canonical == battle_card_name and variant != battle_card_name:
                names.append(variant)

        person_map = _get_or_build_person_map(company_id, db)
        for person, company in person_map.items():
            if company == battle_card_name:
                names.append(person)

    return names


def is_known_person(
    name: str,
    company_id: str | None = None,
    supabase_client: Any | None = None,
) -> bool:
    """Check if a name is a known person mapped to a company."""
    if not name:
        return False
    if company_id and supabase_client:
        person_map = _get_or_build_person_map(company_id, supabase_client)
        return name in person_map or name.lower() in {p.lower() for p in person_map}
    return False


def get_company_for_person(
    person_name: str,
    company_id: str | None = None,
    supabase_client: Any | None = None,
) -> str | None:
    """Get the company a person should map to."""
    if not person_name:
        return None
    if company_id and supabase_client:
        person_map = _get_or_build_person_map(company_id, supabase_client)
        if person_name in person_map:
            return person_map[person_name]
        person_lower = person_name.lower()
        for person, company in person_map.items():
            if person.lower() == person_lower:
                return company
    return None


def clear_cache() -> None:
    """Clear alias caches. Call when battle_cards are updated."""
    global _alias_cache, _person_cache
    _alias_cache = {}
    _person_cache = {}


# ---------------------------------------------------------------------------
# Internal cache builders
# ---------------------------------------------------------------------------

def _get_or_build_aliases(company_id: str, db: Any) -> dict[str, str]:
    """Build or retrieve cached alias mapping from battle_cards."""
    if company_id in _alias_cache:
        return _alias_cache[company_id]

    try:
        result = (
            db.table("battle_cards")
            .select("competitor_name, competitor_domain")
            .eq("company_id", company_id)
            .execute()
        )

        aliases: dict[str, str] = {}
        if result.data:
            for card in result.data:
                canonical = card["competitor_name"]
                domain = card.get("competitor_domain", "")

                # Canonical name maps to itself
                aliases[canonical] = canonical

                # Auto-generate common variants from multi-word names
                if " " in canonical:
                    parts = canonical.split()
                    last_word = parts[-1]
                    if last_word in (
                        "Corporation", "Corp", "Inc", "AG", "Ltd",
                        "GmbH", "SE", "PLC", "plc",
                    ):
                        # "Pall Corporation" -> also match "Pall"
                        short_name = " ".join(parts[:-1])
                        aliases[short_name] = canonical
                        # Generate suffix variants: "Pall Corp", "Pall Corp.", etc.
                        for suffix in ("Corp", "Corp.", "Corporation", "Inc", "Inc.", "AG", "Ltd"):
                            aliases[f"{short_name} {suffix}"] = canonical

                # Domain-based variant (e.g., "cytiva" from "cytiva.com")
                if domain:
                    domain_name = (
                        domain.replace("https://", "")
                        .replace("http://", "")
                        .replace("www.", "")
                        .replace(".com", "")
                        .replace(".org", "")
                        .replace(".io", "")
                        .strip("/")
                        .strip()
                    )
                    if domain_name and domain_name != canonical.lower():
                        aliases[domain_name] = canonical
                        aliases[domain_name.capitalize()] = canonical

        _alias_cache[company_id] = aliases
        return aliases
    except Exception as e:
        logger.warning("Failed to build aliases for company %s: %s", company_id, e)
        return {}


def _get_or_build_person_map(company_id: str, db: Any) -> dict[str, str]:
    """Build person-to-company mapping. Currently returns empty; future:
    mine semantic memory for 'X is CEO of Y' patterns."""
    if company_id in _person_cache:
        return _person_cache[company_id]

    # Placeholder: will be populated by enrichment pipeline later
    _person_cache[company_id] = {}
    return {}
