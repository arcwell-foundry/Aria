"""
Therapeutic Area Signal Mapping for Life Sciences.
Detects cross-company patterns within therapeutic areas and drug modalities.
Maps signals to therapeutic trends that affect the user's market position.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Therapeutic area keywords for signal classification
THERAPEUTIC_AREAS: dict[str, list[str]] = {
    "oncology": [
        "oncology",
        "cancer",
        "tumor",
        "immuno-oncology",
        "checkpoint inhibitor",
        "CAR-T",
        "lymphoma",
        "leukemia",
        "solid tumor",
    ],
    "immunology": [
        "immunology",
        "autoimmune",
        "rheumatoid",
        "lupus",
        "psoriasis",
        "crohn",
        "inflammatory bowel",
        "multiple sclerosis",
    ],
    "neurology": [
        "neurology",
        "alzheimer",
        "parkinson",
        "neurodegeneration",
        "CNS",
        "brain",
        "multiple sclerosis",
    ],
    "rare_disease": [
        "rare disease",
        "orphan drug",
        "orphan designation",
        "ultra-rare",
        "genetic disease",
        "gene therapy",
    ],
    "infectious_disease": [
        "infectious disease",
        "vaccine",
        "antiviral",
        "antibacterial",
        "pandemic",
        "COVID",
        "RSV",
        "influenza",
    ],
    "cardiovascular": [
        "cardiovascular",
        "heart failure",
        "hypertension",
        "atherosclerosis",
        "cardiac",
    ],
    "metabolic": [
        "metabolic",
        "diabetes",
        "obesity",
        "GLP-1",
        "NASH",
        "NAFLD",
        "weight loss",
    ],
    "cell_gene_therapy": [
        "cell therapy",
        "gene therapy",
        "CAR-T",
        "CAR T",
        "AAV",
        "viral vector",
        "CRISPR",
        "gene editing",
    ],
    "biosimilars": [
        "biosimilar",
        "interchangeable",
        "reference product",
        "abbreviated pathway",
    ],
}

# Manufacturing modality keywords
MANUFACTURING_MODALITIES: dict[str, list[str]] = {
    "mAb_manufacturing": [
        "monoclonal antibody",
        "mAb",
        "antibody manufacturing",
        "CHO cell",
        "fed-batch",
        "perfusion",
    ],
    "viral_vector": [
        "viral vector",
        "AAV",
        "lentiviral",
        "adenoviral",
        "vector production",
    ],
    "cell_processing": [
        "cell processing",
        "cell expansion",
        "T-cell",
        "autologous",
        "allogeneic",
    ],
    "mrna_manufacturing": [
        "mRNA",
        "lipid nanoparticle",
        "LNP",
        "in vitro transcription",
    ],
    "cdmo_expansion": [
        "CDMO",
        "contract manufacturing",
        "manufacturing capacity",
        "facility expansion",
        "new facility",
    ],
    "single_use": [
        "single-use",
        "disposable",
        "single use",
        "bioreactor bag",
    ],
    "continuous_processing": [
        "continuous processing",
        "continuous manufacturing",
        "continuous bioprocessing",
    ],
    "downstream": [
        "downstream",
        "purification",
        "chromatography",
        "filtration",
        "TFF",
        "UF/DF",
    ],
}


def detect_therapeutic_area(event_text: str) -> list[str]:
    """Detect therapeutic areas mentioned in a signal.

    Args:
        event_text: The text to analyze for therapeutic area keywords.

    Returns:
        List of detected therapeutic area keys.
    """
    text_lower = event_text.lower()
    detected: list[str] = []
    for area, keywords in THERAPEUTIC_AREAS.items():
        if any(kw.lower() in text_lower for kw in keywords):
            detected.append(area)
    return detected


def detect_manufacturing_modality(event_text: str) -> list[str]:
    """Detect manufacturing modalities mentioned in a signal.

    Args:
        event_text: The text to analyze for manufacturing modality keywords.

    Returns:
        List of detected manufacturing modality keys.
    """
    text_lower = event_text.lower()
    detected: list[str] = []
    for modality, keywords in MANUFACTURING_MODALITIES.items():
        if any(kw.lower() in text_lower for kw in keywords):
            detected.append(modality)
    return detected


async def detect_therapeutic_trends(
    supabase_client: Any,
    user_id: str,
    days: int = 30,
    min_signals: int = 3,
) -> list[dict[str, Any]]:
    """Analyze recent signals for therapeutic area trends.

    Returns trends where multiple signals point to the same therapeutic
    area or manufacturing modality.

    Args:
        supabase_client: Supabase client for database queries.
        user_id: User ID to filter signals.
        days: Number of days to look back (unused, kept for API compatibility).
        min_signals: Minimum signals required to form a trend.

    Returns:
        List of trend dictionaries with signal counts and company involvement.
    """
    try:
        result = (
            supabase_client.table("market_signals")
            .select("company_name, headline, signal_type, detected_at, summary")
            .eq("user_id", user_id)
            .order("detected_at", desc=True)
            .limit(100)
            .execute()
        )

        if not result.data:
            return []

        # Classify each signal by therapeutic area and modality
        area_signals: dict[str, list[dict]] = {}
        modality_signals: dict[str, list[dict]] = {}

        for signal in result.data:
            text = f"{signal.get('headline', '')} {signal.get('summary', '')}"

            areas = detect_therapeutic_area(text)
            for area in areas:
                if area not in area_signals:
                    area_signals[area] = []
                area_signals[area].append(signal)

            modalities = detect_manufacturing_modality(text)
            for mod in modalities:
                if mod not in modality_signals:
                    modality_signals[mod] = []
                modality_signals[mod].append(signal)

        trends: list[dict[str, Any]] = []

        # Find therapeutic area trends (min_signals+ signals)
        for area, signals in area_signals.items():
            if len(signals) >= min_signals:
                companies = list({s["company_name"] for s in signals})
                trends.append({
                    "trend_type": "therapeutic_area",
                    "name": area.replace("_", " ").title(),
                    "signal_count": len(signals),
                    "companies_involved": companies,
                    "company_count": len(companies),
                    "recent_signals": signals[:3],
                    "description": (
                        f"{area.replace('_', ' ').title()} activity across "
                        f"{len(companies)} companies with {len(signals)} signals "
                        f"in the last {days} days."
                    ),
                })

        # Find manufacturing modality trends (min_signals+ signals)
        for mod, signals in modality_signals.items():
            if len(signals) >= min_signals:
                companies = list({s["company_name"] for s in signals})
                trends.append({
                    "trend_type": "manufacturing_modality",
                    "name": mod.replace("_", " ").title(),
                    "signal_count": len(signals),
                    "companies_involved": companies,
                    "company_count": len(companies),
                    "recent_signals": signals[:3],
                    "description": (
                        f"{mod.replace('_', ' ').title()} trend across "
                        f"{len(companies)} companies with {len(signals)} signals."
                    ),
                })

        # Sort by signal count
        trends.sort(key=lambda t: t["signal_count"], reverse=True)

        # Generate LLM narratives for top trends
        for trend in trends[:10]:
            try:
                narrative = await generate_trend_narrative(trend)
                trend["narrative"] = narrative
            except Exception:
                trend["narrative"] = ""

        return trends[:10]  # Top 10 trends

    except Exception as e:
        logger.error("[TherapeuticArea] Failed to detect trends: %s", e)
        return []


async def generate_trend_narrative(
    trend: dict[str, Any],
    user_goals: list[dict[str, Any]] | None = None,
) -> str:
    """Generate a strategic 'so what?' narrative for a trend.

    Uses LLM to create a 2-3 sentence narrative explaining what this trend
    means for a bioprocessing sales professional.

    Args:
        trend: Trend dict with area, signal_count, company_count, companies, etc.
        user_goals: Optional list of user's active goals.

    Returns:
        Narrative string, or empty string if generation fails.
    """
    try:
        from src.core.llm import LLMClient
        from src.core.task_types import TaskType

        companies = trend.get("companies_involved", [])
        signal_types_raw = [
            s.get("signal_type", "")
            for s in trend.get("recent_signals", [])
        ]
        signal_types = list(set(t for t in signal_types_raw if t))

        goal_text = ""
        if user_goals:
            goal_titles = [g.get("title", "") for g in user_goals[:3] if g.get("title")]
            if goal_titles:
                goal_text = f"\nUser's active goals: {', '.join(goal_titles)}"

        prompt = (
            f"Trend: {trend.get('name', '')} — "
            f"{trend.get('signal_count', 0)} signals from "
            f"{trend.get('company_count', 0)} companies.\n"
            f"Companies involved: {', '.join(companies[:5])}\n"
            f"Signal types: {', '.join(signal_types[:3])}"
            f"{goal_text}\n\n"
            "In 2 sentences, explain what this trend means for a "
            "bioprocessing sales professional. Be specific. Connect to "
            "their goals if relevant. Don't say 'this creates an "
            "opportunity' — say WHAT opportunity."
        )

        llm = LLMClient()
        response = await llm.generate_response(
            task_type=TaskType.ANALYST_RESEARCH,
            messages=[{"role": "user", "content": prompt}],
            system_prompt=(
                "You are a life sciences market intelligence analyst. "
                "Write concise, actionable trend narratives. No fluff."
            ),
        )

        return response.text.strip() if hasattr(response, "text") else str(response).strip()

    except Exception as e:
        logger.warning("[TherapeuticArea] Narrative generation failed: %s", e)
        return ""


def format_therapeutic_context(
    areas: list[str],
    modalities: list[str],
) -> str | None:
    """Format therapeutic area context for a single signal's LLM prompt.

    Args:
        areas: List of detected therapeutic area keys.
        modalities: List of detected manufacturing modality keys.

    Returns:
        Formatted context string for LLM, or None if no areas/modalities.
    """
    if not areas and not modalities:
        return None

    parts = ["\n🧪 THERAPEUTIC/MANUFACTURING CLASSIFICATION"]
    if areas:
        parts.append(
            f"Therapeutic areas: {', '.join(a.replace('_', ' ').title() for a in areas)}"
        )
    if modalities:
        parts.append(
            f"Manufacturing modalities: {', '.join(m.replace('_', ' ').title() for m in modalities)}"
        )
    parts.append(
        "ANALYZE: Consider how this signal fits into broader therapeutic area trends. "
        "What does it mean for bioprocessing equipment demand in this therapeutic area?"
    )

    return "\n".join(parts)
