"""Seed dynamic intelligence for lead gen into memory_semantic.

Populates SubIndustryContext, search vocabulary, target examples, buyer
personas, trigger relevance, signal sources, and quality principles based
on the user's ICP and company classification from onboarding enrichment.

Called:
  1. After CompanyEnrichmentEngine completes (onboarding flow)
  2. Manually via seed_lead_gen_intelligence.py script for existing users
"""

import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


async def seed_lead_gen_intelligence(
    user_id: str,
    *,
    company_type: str | None = None,
    modality: str | None = None,
    posture: str | None = None,
) -> int:
    """Populate memory_semantic with lead-gen-specific intelligence.

    Uses the user's ICP from lead_icp_profiles and company classification
    from onboarding enrichment to generate contextual search vocabulary,
    target examples, and scoring context for Hunter.

    Args:
        user_id: The user to seed intelligence for.
        company_type: Optional override (e.g. 'equipment_manufacturer').
        modality: Optional override (e.g. 'bioprocessing').
        posture: Optional override (e.g. 'seller').

    Returns:
        Number of memory_semantic entries created.
    """
    from src.db.supabase import SupabaseClient

    db = SupabaseClient.get_client()

    # Load ICP if available
    icp: dict[str, Any] = {}
    try:
        icp_result = (
            db.table("lead_icp_profiles")
            .select("criteria")
            .eq("user_id", user_id)
            .eq("is_active", True)
            .limit(1)
            .execute()
        )
        if icp_result.data:
            icp = icp_result.data[0].get("criteria", {}) or {}
    except Exception as e:
        logger.warning("Failed to load ICP for intelligence seeding: %s", e)

    # Load company classification from enrichment if not provided
    if not company_type:
        try:
            company_result = (
                db.table("companies")
                .select("settings")
                .eq("user_id", user_id)
                .limit(1)
                .execute()
            )
            if company_result.data:
                settings = company_result.data[0].get("settings", {}) or {}
                classification = settings.get("classification", {})
                company_type = classification.get("company_type", "")
                modality = modality or classification.get("primary_modality", "")
                posture = posture or classification.get("company_posture", "")
        except Exception as e:
            logger.warning("Failed to load company classification: %s", e)

    # Build intelligence entries based on ICP and classification
    industry_list = icp.get("industry", [])
    industry_str = ", ".join(industry_list) if isinstance(industry_list, list) else str(industry_list)
    modalities = icp.get("modalities", [])
    modality_str = ", ".join(modalities) if isinstance(modalities, list) else str(modalities)
    geographies = icp.get("geographies", [])
    geo_str = ", ".join(geographies) if isinstance(geographies, list) else str(geographies)
    company_size = icp.get("company_size", {})
    size_min = company_size.get("min", 50) if isinstance(company_size, dict) else 50
    size_max = company_size.get("max", 500) if isinstance(company_size, dict) else 500
    therapeutic_areas = icp.get("therapeutic_areas", [])
    therapy_str = ", ".join(therapeutic_areas) if isinstance(therapeutic_areas, list) else str(therapeutic_areas)
    signals = icp.get("signals", [])
    exclusions = icp.get("exclusions", [])
    exclusion_str = ", ".join(exclusions) if isinstance(exclusions, list) else str(exclusions)

    now = datetime.now(UTC).isoformat()

    entries: list[dict[str, Any]] = []

    # 1. SubIndustryContext
    if industry_str or modality:
        entries.append({
            "user_id": user_id,
            "fact": (
                f"User company ({exclusion_str or 'N/A'}) is a {company_type or 'life sciences'} "
                f"company. Sells {modality_str or modality or 'solutions'} to "
                f"{industry_str or 'life sciences'} companies. Targets: mid-market "
                f"({size_min}-{size_max} employees) in {geo_str or 'US'} "
                f"focused on {therapy_str or 'biologics'}."
            ),
            "confidence": 0.95,
            "source": "skill_lead_gen_context",
            "metadata": {
                "entity_type": "sub_industry_context",
                "company_type": company_type or "unknown",
                "modality": modality or "unknown",
                "posture": posture or "unknown",
            },
            "created_at": now,
            "updated_at": now,
        })

    # 2. Trigger relevance weights
    if signals:
        signal_str = ", ".join(signals) if isinstance(signals, list) else str(signals)
        entries.append({
            "user_id": user_id,
            "fact": (
                f"Trigger event relevance for {modality_str or modality or 'life sciences'} "
                f"sales: CRITICAL: {signal_str}. HIGH: new funding round (Series B+), "
                f"FDA approval (creates manufacturing need), Phase III advancement. "
                f"MEDIUM: new CTO/VP hire, M&A activity. LOW: Phase I/II activity, "
                f"clinical trial failures."
            ),
            "confidence": 0.7,
            "source": "skill_lead_gen_triggers",
            "metadata": {
                "entity_type": "trigger_relevance",
                "user_company_type": company_type or "unknown",
            },
            "created_at": now,
            "updated_at": now,
        })

    # 3. Buyer personas
    entries.append({
        "user_id": user_id,
        "fact": (
            f"Typical buying committee for {modality_str or modality or 'life sciences'} "
            f"equipment at mid-market {industry_str or 'biotech'}: "
            f"VP/Director Process Development (technical evaluator), "
            f"VP Manufacturing/Operations (economic buyer), "
            f"Head of Procurement (price negotiations), "
            f"VP Quality (compliance gate), Lab Manager (end user champion)."
        ),
        "confidence": 0.65,
        "source": "skill_lead_gen_personas",
        "metadata": {
            "entity_type": "buyer_persona",
            "sub_industry": f"{modality or 'life_sciences'}_equipment",
            "roles": [
                "VP Process Development",
                "VP Manufacturing",
                "Head of Procurement",
                "VP Quality",
                "Lab Manager",
            ],
        },
        "created_at": now,
        "updated_at": now,
    })

    # 4. Search vocabulary (CRITICAL for Hunter)
    search_terms = _build_search_terms(industry_str, modality_str, therapy_str)
    entries.append({
        "user_id": user_id,
        "fact": (
            f"When searching for leads, use these SPECIFIC terms: "
            f"{', '.join(f'"{t}"' for t in search_terms)}. "
            f"NEVER search generic terms like \"{industry_str} companies\" or "
            f"\"life sciences companies\" - these return consulting firms."
        ),
        "confidence": 0.9,
        "source": "skill_lead_gen_search_terms",
        "metadata": {
            "entity_type": "search_vocabulary",
            "purpose": "hunter_exa_queries",
        },
        "created_at": now,
        "updated_at": now,
    })

    # 5. Signal sources
    entries.append({
        "user_id": user_id,
        "fact": (
            f"Best signal sources for {modality_str or modality or 'life sciences'} "
            f"leads: (1) Job postings for process development and manufacturing roles. "
            f"(2) FDA filings in relevant therapeutic areas. "
            f"(3) Facility expansion press releases. "
            f"(4) Earnings call language mentioning manufacturing investment or capacity. "
            f"(5) Conference exhibitor lists at industry events."
        ),
        "confidence": 0.7,
        "source": "skill_lead_gen_signals",
        "metadata": {
            "entity_type": "signal_sources",
            "sub_industry": f"{modality or 'life_sciences'}_equipment",
        },
        "created_at": now,
        "updated_at": now,
    })

    # 6. Quality principle
    entries.append({
        "user_id": user_id,
        "fact": (
            "Lead quality principle: Signal-enriched leads are 3-5x more likely to "
            "convert than cold ICP matches. Every lead should have at least one "
            "real-world signal before outreach. ICP-only leads without signals should "
            "be monitored but not actively pursued."
        ),
        "confidence": 0.8,
        "source": "skill_lead_gen_quality",
        "metadata": {
            "entity_type": "quality_principle",
            "rule": "signal_required_for_outreach",
        },
        "created_at": now,
        "updated_at": now,
    })

    # 7. Target company examples
    examples = _build_target_examples(industry_str, modality_str)
    entries.append({
        "user_id": user_id,
        "fact": (
            f"Examples of companies that match our ICP: {examples}. "
            f"These are the TYPES of companies Hunter should find - "
            f"manufacturers and CDMOs, NOT consulting firms or advisory companies."
        ),
        "confidence": 0.85,
        "source": "skill_lead_gen_examples",
        "metadata": {
            "entity_type": "target_examples",
            "purpose": "hunter_calibration",
        },
        "created_at": now,
        "updated_at": now,
    })

    # Upsert: delete old skill_lead_gen entries first, then insert fresh
    try:
        db.table("memory_semantic").delete().eq(
            "user_id", user_id
        ).like("source", "skill_lead_gen%").execute()
    except Exception as e:
        logger.warning("Failed to clean old lead gen intelligence: %s", e)

    inserted = 0
    for entry in entries:
        try:
            db.table("memory_semantic").insert(entry).execute()
            inserted += 1
        except Exception as e:
            logger.warning("Failed to insert lead gen intelligence entry: %s", e)

    logger.info(
        "Seeded %d lead gen intelligence entries for user %s",
        inserted,
        user_id,
    )
    return inserted


def _build_search_terms(
    industry: str, modality: str, therapy: str
) -> list[str]:
    """Build domain-specific search terms from ICP data."""
    terms: list[str] = []

    # Map common modalities to search terms
    modality_lower = modality.lower() if modality else ""
    if "bioprocessing" in modality_lower or "filtration" in modality_lower:
        terms.extend([
            "CDMO bioprocessing",
            "contract manufacturing biologics",
            "biomanufacturing facility",
            "bioprocessing equipment",
            "GMP manufacturing biologics",
        ])
    if "cell" in modality_lower or "gene" in modality_lower:
        terms.extend([
            "cell therapy manufacturing",
            "gene therapy CDMO",
        ])
    if "mrna" in modality_lower or "mRNA" in modality:
        terms.append("mRNA manufacturing")
    if "chromatography" in modality_lower:
        terms.append("chromatography systems biotech")
    if "filtration" in modality_lower or "tff" in modality_lower:
        terms.append("filtration systems pharma manufacturing")

    # Always include scale-up
    if "bioprocess" in modality_lower:
        terms.append("bioprocess scale-up facility")

    # If no specific terms generated, use industry
    if not terms and industry:
        terms.extend([
            f"{industry} manufacturing",
            f"{industry} CDMO",
            f"{industry} equipment supplier",
        ])

    return terms or ["life sciences manufacturing", "CDMO biologics"]


def _build_target_examples(industry: str, modality: str) -> str:
    """Build target company examples based on industry/modality."""
    modality_lower = modality.lower() if modality else ""

    if "bioprocessing" in modality_lower or "filtration" in modality_lower:
        return (
            "Lonza (CDMO, biologics), Catalent (CDMO, drug delivery), "
            "Samsung Biologics (CDMO, large molecule), Fujifilm Diosynth (CDMO, cell culture), "
            "AGC Biologics (CDMO, gene therapy), WuXi Biologics (CRO/CDMO), "
            "Cytiva (equipment, bioprocessing), Sartorius (equipment, bioprocessing), "
            "Pall Corporation (filtration)"
        )

    # Generic life sciences examples
    return (
        "Lonza (CDMO), Catalent (CDMO), Samsung Biologics (CDMO), "
        "Fujifilm Diosynth (CDMO), AGC Biologics (CDMO), WuXi Biologics (CRO/CDMO)"
    )
