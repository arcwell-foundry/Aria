"""Company alias mapping utility for reliable cross-table joins.

This module provides canonical company name normalization to ensure
market_signals.company_name matches battle_cards.company_name.

Data Quality Issues This Solves:
1. People stored as company_name (e.g., "Olivier Loeillot" should be "Repligen")
2. Company name inconsistencies (e.g., "Repligen Corporation" vs "Repligen")
3. Subsidiary/parent confusion (e.g., "Pall Danaher" vs "Pall Corporation")

Usage:
    from src.utils.company_aliases import normalize_company_name

    canonical_name = normalize_company_name("Thermo Fisher Scientific")
    # Returns: "Thermo Fisher"
"""

from typing import Literal

# Maps variant names to the canonical name used in battle_cards
COMPANY_CANONICAL_NAMES: dict[str, str] = {
    # Repligen variants
    "Repligen Corporation": "Repligen",
    "Repligen Corp": "Repligen",
    # Pall variants
    "Pall Danaher": "Pall Corporation",
    "Pall Corp": "Pall Corporation",
    # Thermo Fisher variants
    "Thermo Fisher Scientific": "Thermo Fisher",
    "Thermo Fisher Scientific Inc": "Thermo Fisher",
    "ThermoFisher": "Thermo Fisher",
    # MilliporeSigma variants
    "MilliporeSigma (Merck KGaA)": "MilliporeSigma",
    "Merck KGaA": "MilliporeSigma",
    # Sartorius variants
    "Sartorius AG": "Sartorius",
    "Sartorius Stedim": "Sartorius",
    "Sartorius Stedim Biotech": "Sartorius",
    # Cytiva variants (formerly GE Healthcare Life Sciences)
    "Cytiva (Danaher)": "Cytiva",
    "GE Healthcare Life Sciences": "Cytiva",
    # Danaher variants
    "Danaher Corporation": "Danaher",
    # Add more as discovered
}

# People who should be mapped to their company
# This catches cases where signal extraction incorrectly puts a person's name
# in the company_name field
PERSON_TO_COMPANY: dict[str, str] = {
    # Repligen executives
    "Olivier Loeillot": "Repligen",
    "Tony J. Hunt": "Repligen",
    # Add more as discovered
}


def normalize_company_name(name: str | None) -> str:
    """Returns the canonical company name, handling aliases and known people.

    This function should be called before inserting any company_name into
    market_signals or other tables to ensure consistency with battle_cards.

    Args:
        name: The company name to normalize (may be None or empty).

    Returns:
        The canonical company name, or the original name if no mapping exists.

    Examples:
        >>> normalize_company_name("Thermo Fisher Scientific")
        "Thermo Fisher"
        >>> normalize_company_name("Olivier Loeillot")
        "Repligen"
        >>> normalize_company_name("Unknown Company")
        "Unknown Company"
    """
    if not name:
        return name or ""

    # Check person mapping first (higher priority)
    if name in PERSON_TO_COMPANY:
        return PERSON_TO_COMPANY[name]

    # Check alias mapping (exact match)
    if name in COMPANY_CANONICAL_NAMES:
        return COMPANY_CANONICAL_NAMES[name]

    # Check case-insensitive match
    name_lower = name.lower().strip()
    for variant, canonical in COMPANY_CANONICAL_NAMES.items():
        if variant.lower() == name_lower:
            return canonical

    # Check case-insensitive person match
    for person, company in PERSON_TO_COMPANY.items():
        if person.lower() == name_lower:
            return company

    # No mapping found, return original
    return name


def get_signal_company_names_for_battle_card(battle_card_name: str) -> list[str]:
    """Returns all company_name variants that map to this battle card name.

    Useful when querying market_signals for signals related to a specific
    battle card, since historical signals may use variant names.

    Args:
        battle_card_name: The canonical company name from battle_cards.

    Returns:
        List of all variant names (including the canonical name) that map
        to this battle card.

    Examples:
        >>> get_signal_company_names_for_battle_card("Thermo Fisher")
        ["Thermo Fisher", "Thermo Fisher Scientific", "Thermo Fisher Scientific Inc", "ThermoFisher"]
    """
    names = [battle_card_name]

    # Add all aliases that map to this canonical name
    for variant, canonical in COMPANY_CANONICAL_NAMES.items():
        if canonical == battle_card_name:
            names.append(variant)

    # Add all people that map to this company
    for person, company in PERSON_TO_COMPANY.items():
        if company == battle_card_name:
            names.append(person)

    return names


def is_known_person(name: str) -> bool:
    """Check if a name is a known person who should be mapped to a company.

    Args:
        name: The name to check.

    Returns:
        True if the name is in the PERSON_TO_COMPANY mapping.
    """
    if not name:
        return False
    return name in PERSON_TO_COMPANY or name.lower() in {
        p.lower() for p in PERSON_TO_COMPANY
    }


def get_company_for_person(person_name: str) -> str | None:
    """Get the company that a person should be mapped to.

    Args:
        person_name: The person's name.

    Returns:
        The canonical company name, or None if the person is not in the mapping.
    """
    if not person_name:
        return None

    # Try exact match first
    if person_name in PERSON_TO_COMPANY:
        return PERSON_TO_COMPANY[person_name]

    # Try case-insensitive match
    person_lower = person_name.lower()
    for person, company in PERSON_TO_COMPANY.items():
        if person.lower() == person_lower:
            return company

    return None
