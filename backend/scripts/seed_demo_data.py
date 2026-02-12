#!/usr/bin/env python3
"""Seed script for ARIA investor demo data.

Seeds Supabase with deterministic demo data for a repeatable 3-minute
investor demonstration. All data is tagged so it can be cleanly removed.

Usage:
    cd backend && python scripts/seed_demo_data.py --user-id <uuid>
    cd backend && python scripts/seed_demo_data.py --user-id <uuid> --clean
"""

import argparse
import logging
import os
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv

from supabase import Client, create_client

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Load environment
load_dotenv()


# ---------------------------------------------------------------------------
# Supabase client
# ---------------------------------------------------------------------------


def get_supabase_client() -> Client:
    """Create Supabase client from environment variables."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

    if not url or not key:
        logger.error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
        sys.exit(1)

    return create_client(url, key)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def validate_uuid(value: str) -> UUID:
    """Validate and return a UUID from a string."""
    try:
        return UUID(value)
    except ValueError:
        logger.error(f"Invalid UUID: {value}")
        sys.exit(1)


def resolve_company_id(client: Client, user_id: UUID) -> str:
    """Look up company_id from user_profiles table."""
    result = (
        client.table("user_profiles").select("company_id").eq("id", str(user_id)).single().execute()
    )
    company_id = result.data.get("company_id") if result.data else None
    if not company_id:
        logger.error("No company_id found for user. Use --company-id flag.")
        sys.exit(1)
    return company_id


def now_iso() -> str:
    """Return current UTC time as ISO string."""
    return datetime.now(UTC).isoformat()


def ago(days: int = 0, hours: int = 0, minutes: int = 0) -> str:
    """Return an ISO timestamp for a point in the past."""
    dt = datetime.now(UTC) - timedelta(days=days, hours=hours, minutes=minutes)
    return dt.isoformat()


def future(days: int = 0) -> str:
    """Return a DATE string (YYYY-MM-DD) for a point in the future."""
    d = date.today() + timedelta(days=days)
    return d.isoformat()


def today_at(hour: int, minute: int = 0) -> str:
    """Return an ISO timestamp for a specific time today (UTC)."""
    dt = datetime.now(UTC).replace(hour=hour, minute=minute, second=0, microsecond=0)
    return dt.isoformat()


# ---------------------------------------------------------------------------
# Clean
# ---------------------------------------------------------------------------


def clean_demo_data(client: Client, user_id: str, company_id: str) -> None:
    """Delete all demo-tagged data in dependency-safe order."""
    logger.info("Cleaning existing demo data...")

    uid = str(user_id)
    cid = str(company_id)

    # 1. email_drafts
    res = (
        client.table("email_drafts")
        .delete()
        .filter("context->>demo", "eq", "true")
        .eq("user_id", uid)
        .execute()
    )
    logger.info(f"  Deleted {len(res.data)} email_drafts")

    # 2. market_signals
    res = (
        client.table("market_signals")
        .delete()
        .filter("metadata->>demo", "eq", "true")
        .eq("user_id", uid)
        .execute()
    )
    logger.info(f"  Deleted {len(res.data)} market_signals")

    # 3. aria_action_queue
    res = (
        client.table("aria_action_queue")
        .delete()
        .filter("payload->>demo", "eq", "true")
        .eq("user_id", uid)
        .execute()
    )
    logger.info(f"  Deleted {len(res.data)} aria_action_queue")

    # 4. goals (cascades goal_agents)
    res = (
        client.table("goals")
        .delete()
        .filter("config->>demo", "eq", "true")
        .eq("user_id", uid)
        .execute()
    )
    logger.info(f"  Deleted {len(res.data)} goals (+ cascaded goal_agents)")

    # 5. lead_memories (cascades lead_memory_stakeholders)
    res = (
        client.table("lead_memories")
        .delete()
        .filter("metadata->>demo", "eq", "true")
        .eq("user_id", uid)
        .execute()
    )
    logger.info(f"  Deleted {len(res.data)} lead_memories (+ cascaded stakeholders)")

    # 6. battle_cards
    res = (
        client.table("battle_cards")
        .delete()
        .eq("update_source", "demo_seed")
        .eq("company_id", cid)
        .execute()
    )
    logger.info(f"  Deleted {len(res.data)} battle_cards")

    # 7. meeting_briefs
    res = (
        client.table("meeting_briefs")
        .delete()
        .filter("brief_content->>demo", "eq", "true")
        .eq("user_id", uid)
        .execute()
    )
    logger.info(f"  Deleted {len(res.data)} meeting_briefs")

    # 8. video_sessions
    res = (
        client.table("video_sessions")
        .delete()
        .eq("tavus_conversation_id", "demo_briefing")
        .eq("user_id", uid)
        .execute()
    )
    logger.info(f"  Deleted {len(res.data)} video_sessions")

    # 9. Clean briefing_context from user_settings
    existing = client.table("user_settings").select("id, preferences").eq("user_id", uid).execute()
    if existing.data and len(existing.data) > 0:
        prefs = existing.data[0].get("preferences") or {}
        if "briefing_context" in prefs:
            del prefs["briefing_context"]
            client.table("user_settings").update({"preferences": prefs}).eq(
                "user_id", uid
            ).execute()
            logger.info("  Cleaned briefing_context from user_settings")

    logger.info("Clean complete.")


# ---------------------------------------------------------------------------
# Seed: Battle Cards
# ---------------------------------------------------------------------------


def seed_battle_cards(client: Client, company_id: str) -> int:
    """Seed 5 competitive battle cards."""
    logger.info("Seeding battle cards...")

    ts = now_iso()
    cid = str(company_id)

    cards = [
        {
            "company_id": cid,
            "competitor_name": "Lonza",
            "competitor_domain": "lonza.com",
            "overview": "Global CDMO leader with $6.2B revenue, dominant in mammalian biologics manufacturing. Operates 30+ facilities worldwide with particular strength in large-scale commercial production using stainless steel bioreactors up to 20,000L.",
            "strengths": [
                "Global manufacturing footprint with 30+ facilities",
                "Strongest regulatory track record in biologics (200+ successful FDA submissions)",
                "Unmatched scale for commercial manufacturing (up to 20,000L bioreactors)",
                "Deep expertise in CHO cell culture and mammalian expression systems",
            ],
            "weaknesses": [
                "Premium pricing — typically 25-40% above market average",
                "Long lead times for new programs (9-14 months to first GMP batch)",
                "Complex contracting process with rigid terms",
                "Key account managers frequently rotate",
            ],
            "pricing": {
                "model": "Per-batch + FTE-based",
                "range": "$800K-$3.5M per program",
                "notes": "Higher for late-stage commercial, discounts for multi-year commitments",
            },
            "differentiation": [
                {
                    "area": "Speed to IND",
                    "our_advantage": "Our dedicated suite model delivers first GMP batch 4-6 months faster than Lonza's shared facility queue",
                },
                {
                    "area": "Batch Size Flexibility",
                    "our_advantage": "We offer 50L-2000L single-use options vs Lonza's 2000L+ stainless steel minimum",
                },
                {
                    "area": "Dedicated Teams",
                    "our_advantage": "Same team from development through commercial vs Lonza's rotation model",
                },
            ],
            "objection_handlers": [
                {
                    "objection": "Lonza has more regulatory experience than you",
                    "response": "Lonza's track record is impressive, but 85% of their submissions are for large pharma with dedicated regulatory teams. For mid-size biotechs like yours, our hands-on regulatory support has achieved a 94% first-cycle approval rate — we guide you through the process rather than expecting you to lead it.",
                },
                {
                    "objection": "We need the scale that only Lonza can provide",
                    "response": "That's valid for blockbuster commercialization, but your current forecast of 50,000 doses annually fits perfectly in our single-use platform. You'd be competing for attention in Lonza's queue vs having a dedicated suite with us. If you outgrow us, we'll help you transition — that's in our contract.",
                },
            ],
            "analysis": {
                "metrics": {
                    "market_cap_gap": 12.5,
                    "win_rate": 42,
                    "pricing_delta": 8.3,
                    "last_signal_at": "2026-02-08T14:30:00Z",
                },
                "strategies": [
                    {
                        "title": "Emphasize Speed",
                        "description": "Highlight our 40% faster turnaround for small batches",
                        "icon": "zap",
                        "agent": "Hunter",
                    },
                    {
                        "title": "Target Emerging Biotech",
                        "description": "Focus on Series A-C companies underserved by Lonza's enterprise focus",
                        "icon": "target",
                        "agent": "Strategist",
                    },
                    {
                        "title": "Quick Win: Pricing",
                        "description": "Offer 15% discount on first project to dislodge incumbent",
                        "icon": "clock",
                        "agent": "Operator",
                    },
                    {
                        "title": "Defend on Quality",
                        "description": "Prepare case studies showing superior analytical capabilities",
                        "icon": "shield",
                        "agent": "Analyst",
                    },
                ],
                "feature_gaps": [
                    {"feature": "Analytical Capabilities", "aria_score": 85, "competitor_score": 75},
                    {"feature": "Small Batch Speed", "aria_score": 92, "competitor_score": 65},
                    {"feature": "Global Footprint", "aria_score": 45, "competitor_score": 88},
                    {"feature": "Regulatory Expertise", "aria_score": 78, "competitor_score": 82},
                    {"feature": "Cost Competitiveness", "aria_score": 70, "competitor_score": 72},
                    {"feature": "Technology Platform", "aria_score": 80, "competitor_score": 78},
                ],
                "critical_gaps": [
                    {"description": "Faster turnaround on small batch projects (avg. 4 weeks vs 6 weeks)", "is_advantage": True},
                    {"description": "More flexible contract terms for early-stage companies", "is_advantage": True},
                    {"description": "Dedicated project manager assigned to each client", "is_advantage": True},
                    {"description": "Competitor has larger global manufacturing footprint (6 sites vs 3)", "is_advantage": False},
                    {"description": "Competitor offers integrated supply chain services", "is_advantage": False},
                ],
            },
            "update_source": "demo_seed",
            "last_updated": ts,
            "created_at": ts,
        },
        {
            "company_id": cid,
            "competitor_name": "Catalent",
            "competitor_domain": "catalent.com",
            "overview": "Full-service CDMO with $4.8B revenue, strong in gene therapy and biologics fill-finish. Offers true end-to-end capabilities from cell line development through commercial packaging across a global network of 50+ sites.",
            "strengths": [
                "True end-to-end capabilities from cell line to commercial packaging",
                "Leading gene therapy manufacturing (AAV and lentiviral vectors)",
                "Global network with 50+ sites across 4 continents",
                "Strong analytical development and release testing capabilities",
            ],
            "weaknesses": [
                "Recent FDA warning letters at 2 facilities (Bloomington, Brussels)",
                "Integration challenges following $12B+ in acquisitions",
                "Inconsistent quality metrics across legacy vs acquired sites",
                "High employee turnover in manufacturing operations (22% annual)",
            ],
            "pricing": {
                "model": "Milestone-based + royalty options",
                "range": "$500K-$2.5M per program phase",
                "notes": "Royalty model available (1-3% of net sales) to reduce upfront costs",
            },
            "differentiation": [
                {
                    "area": "Quality Track Record",
                    "our_advantage": "Zero FDA warning letters in 8 years vs Catalent's 2 active warning letters. Our quality-first approach means fewer batch failures and faster release.",
                },
                {
                    "area": "Pricing Transparency",
                    "our_advantage": "No royalty model — you own your process and economics completely. Catalent's royalty can cost $5-15M over product lifecycle.",
                },
                {
                    "area": "Tech Transfer Speed",
                    "our_advantage": "Average 12-week tech transfer vs Catalent's 18-24 weeks due to their multi-site coordination overhead",
                },
            ],
            "objection_handlers": [
                {
                    "objection": "Catalent can handle everything from development through commercial",
                    "response": "End-to-end sounds appealing, but our clients consistently report faster timelines by choosing best-in-class partners for each phase. Three of our current clients transferred FROM Catalent after experiencing delays at their fill-finish sites. We can share anonymized case studies.",
                },
                {
                    "objection": "Catalent's gene therapy expertise is unmatched",
                    "response": "For AAV manufacturing specifically, Catalent is strong. But if you're looking at lentiviral or mRNA platforms, our yields are 2-3x higher based on recent head-to-head comparisons. Let me share our viral vector manufacturing data.",
                },
            ],
            "analysis": {
                "metrics": {
                    "market_cap_gap": -8.2,
                    "win_rate": 58,
                    "pricing_delta": -3.1,
                    "last_signal_at": "2026-02-10T09:15:00Z",
                },
                "strategies": [
                    {
                        "title": "Lead with Agility",
                        "description": "Our decision-making is 3x faster for scope changes",
                        "icon": "zap",
                        "agent": "Hunter",
                    },
                    {
                        "title": "Target Gene Therapy",
                        "description": "Position strongly in cell/gene where Catalent is weak",
                        "icon": "target",
                        "agent": "Strategist",
                    },
                    {
                        "title": "Quick Win: Capacity",
                        "description": "Offer immediate slot availability for Q2 projects",
                        "icon": "clock",
                        "agent": "Operator",
                    },
                    {
                        "title": "Defend on Scale",
                        "description": "Show successful large-scale production track record",
                        "icon": "shield",
                        "agent": "Analyst",
                    },
                ],
                "feature_gaps": [
                    {"feature": "Project Management", "aria_score": 88, "competitor_score": 72},
                    {"feature": "Gene Therapy Expertise", "aria_score": 75, "competitor_score": 60},
                    {"feature": "Manufacturing Scale", "aria_score": 55, "competitor_score": 90},
                    {"feature": "Supply Chain", "aria_score": 65, "competitor_score": 85},
                    {"feature": "Pricing Flexibility", "aria_score": 82, "competitor_score": 68},
                    {"feature": "Client Communication", "aria_score": 90, "competitor_score": 70},
                ],
                "critical_gaps": [
                    {"description": "Stronger gene therapy and cell therapy capabilities", "is_advantage": True},
                    {"description": "More responsive to scope changes (avg. 2 days vs 7 days)", "is_advantage": True},
                    {"description": "Better pricing transparency and predictability", "is_advantage": True},
                    {"description": "Competitor has significantly larger manufacturing capacity", "is_advantage": False},
                    {"description": "Competitor offers broader range of dosage forms", "is_advantage": False},
                ],
            },
            "update_source": "demo_seed",
            "last_updated": ts,
            "created_at": ts,
        },
        {
            "company_id": cid,
            "competitor_name": "Repligen",
            "competitor_domain": "repligen.com",
            "overview": "Bioprocessing equipment and technology leader with $785M revenue, focused on filtration and chromatography. Industry-standard hardware supplier trusted by process development scientists worldwide, but limited to equipment sales without manufacturing services.",
            "strengths": [
                "Best-in-class filtration products (TFF, depth filtration)",
                "Industry-standard chromatography resins and columns",
                "Strong R&D pipeline with 15+ products in development",
                "Trusted brand among process development scientists",
            ],
            "weaknesses": [
                "Equipment-only — no manufacturing services",
                "Limited process development consulting capabilities",
                "Premium pricing for consumables (30-50% above generics)",
                "Long delivery times during supply chain disruptions",
            ],
            "pricing": {
                "model": "Capital equipment + consumables",
                "range": "$150K-$1.2M per system, plus $50K-$200K annual consumables",
                "notes": "Volume agreements available for enterprise customers",
            },
            "differentiation": [
                {
                    "area": "Integrated Solutions",
                    "our_advantage": "We provide complete workflow solutions (equipment + process + manufacturing) while Repligen only sells components. Clients spend 6+ months integrating Repligen hardware into their process.",
                },
                {
                    "area": "Process Optimization",
                    "our_advantage": "Our process development team optimizes for your specific molecule vs Repligen's one-size-fits-all equipment recommendations",
                },
                {
                    "area": "Single Vendor Accountability",
                    "our_advantage": "One contract, one team, one quality system vs managing Repligen equipment alongside separate CDMO and CRO vendors",
                },
            ],
            "objection_handlers": [
                {
                    "objection": "Repligen's filtration hardware is the industry standard",
                    "response": "Repligen makes excellent hardware, and we actually use their TFF systems in several of our suites. The question isn't equipment quality — it's whether you want to buy components and assemble a workflow, or get a complete manufacturing solution. Our clients save an average of 8 months by not having to integrate and validate individual equipment pieces.",
                },
                {
                    "objection": "We already have Repligen equipment installed",
                    "response": "Great — we're equipment-agnostic and can work with your existing Repligen systems. Many of our clients bring their own equipment preferences. The value we add is process optimization and GMP manufacturing around whatever platform you've standardized on.",
                },
            ],
            "analysis": {
                "metrics": {
                    "market_cap_gap": -22.4,
                    "win_rate": 65,
                    "pricing_delta": -12.0,
                    "last_signal_at": "2026-02-07T10:00:00Z",
                },
                "strategies": [
                    {
                        "title": "Sell the Solution",
                        "description": "Position complete workflow vs component-only approach",
                        "icon": "zap",
                        "agent": "Hunter",
                    },
                    {
                        "title": "Time-to-Value",
                        "description": "Quantify the 8-month integration savings vs buying components",
                        "icon": "target",
                        "agent": "Strategist",
                    },
                    {
                        "title": "Compatibility Play",
                        "description": "Emphasize we are equipment-agnostic and can use their hardware",
                        "icon": "clock",
                        "agent": "Operator",
                    },
                    {
                        "title": "Total Cost Story",
                        "description": "Show full lifecycle cost comparison including integration labor",
                        "icon": "shield",
                        "agent": "Analyst",
                    },
                ],
                "feature_gaps": [
                    {"feature": "Complete Workflow", "aria_score": 90, "competitor_score": 35},
                    {"feature": "Filtration Hardware", "aria_score": 60, "competitor_score": 95},
                    {"feature": "Process Optimization", "aria_score": 85, "competitor_score": 45},
                    {"feature": "Consumable Quality", "aria_score": 70, "competitor_score": 90},
                    {"feature": "Single Vendor Accountability", "aria_score": 95, "competitor_score": 20},
                    {"feature": "Equipment R&D Pipeline", "aria_score": 40, "competitor_score": 88},
                ],
                "critical_gaps": [
                    {"description": "Complete integrated workflow vs components-only offering", "is_advantage": True},
                    {"description": "Single vendor accountability reduces project risk", "is_advantage": True},
                    {"description": "Process optimization tailored to specific molecules", "is_advantage": True},
                    {"description": "Competitor has best-in-class filtration hardware portfolio", "is_advantage": False},
                    {"description": "Competitor brand is industry standard among PD scientists", "is_advantage": False},
                ],
            },
            "update_source": "demo_seed",
            "last_updated": ts,
            "created_at": ts,
        },
        {
            "company_id": cid,
            "competitor_name": "Thermo Fisher Scientific",
            "competitor_domain": "thermofisher.com",
            "overview": "Life sciences conglomerate with $44B revenue, operating the Patheon CDMO division. One-stop shop spanning discovery reagents to commercial manufacturing with unmatched financial stability, but often criticized for bureaucratic processes and deprioritization of smaller clients.",
            "strengths": [
                "One-stop shop from discovery reagents to commercial manufacturing",
                "Unmatched financial stability and business continuity guarantee",
                "Massive scale with 125,000+ employees globally",
                "Broad technology platform covering small molecule through cell therapy",
            ],
            "weaknesses": [
                "Bureaucratic — decision-making requires multiple approval layers",
                "Less specialized in any single modality vs focused CDMOs",
                "Account management turnover and deprioritization of smaller clients",
                "Patheon integration still incomplete 7 years post-acquisition",
            ],
            "pricing": {
                "model": "Service contract (annual or per-project)",
                "range": "$1M-$5M annually depending on scope",
                "notes": "Enterprise agreements available with preferred pricing tiers",
            },
            "differentiation": [
                {
                    "area": "Specialized Attention",
                    "our_advantage": "As a focused CDMO, your program is one of our top priorities. At Thermo Fisher Patheon, programs under $5M/year are routinely deprioritized when larger clients need capacity.",
                },
                {
                    "area": "Team Continuity",
                    "our_advantage": "Same project leader from start to finish. Thermo Fisher clients report 2-3 PM changes per program on average, losing institutional knowledge each time.",
                },
                {
                    "area": "Speed of Decision-Making",
                    "our_advantage": "We can approve protocol changes in 48 hours vs Thermo Fisher's typical 3-4 week internal review cycle for any deviation",
                },
            ],
            "objection_handlers": [
                {
                    "objection": "Thermo Fisher can handle everything we need under one roof",
                    "response": "One roof is appealing until you experience the internal handoffs. We've onboarded 4 programs this year from Thermo Fisher Patheon where clients were frustrated by 6+ month delays caused by cross-division coordination. Our integrated single-site model means zero internal transfers.",
                },
                {
                    "objection": "Thermo Fisher's financial stability is a safer bet",
                    "response": "Financial stability matters, and we're well-capitalized with $200M+ in committed funding. But consider this: Thermo Fisher's Patheon division is one of 50+ business units competing for capital investment. We invest 100% of our CAPEX into the facilities and technology that serve you directly.",
                },
            ],
            "analysis": {
                "metrics": {
                    "market_cap_gap": 45.3,
                    "win_rate": 35,
                    "pricing_delta": 15.2,
                    "last_signal_at": "2026-02-05T16:45:00Z",
                },
                "strategies": [
                    {
                        "title": "Highlight Partnership",
                        "description": "We act as partners, not vendors - dedicated teams",
                        "icon": "zap",
                        "agent": "Hunter",
                    },
                    {
                        "title": "Target Mid-Market",
                        "description": "Focus on companies too small for Thermo's attention",
                        "icon": "target",
                        "agent": "Strategist",
                    },
                    {
                        "title": "Quick Win: Responsiveness",
                        "description": "Guarantee 24-hour response on all inquiries",
                        "icon": "clock",
                        "agent": "Operator",
                    },
                    {
                        "title": "Defend on Integration",
                        "description": "Show seamless end-to-end process management",
                        "icon": "shield",
                        "agent": "Analyst",
                    },
                ],
                "feature_gaps": [
                    {"feature": "Personalized Service", "aria_score": 92, "competitor_score": 55},
                    {"feature": "Mid-Market Focus", "aria_score": 88, "competitor_score": 45},
                    {"feature": "Product Breadth", "aria_score": 40, "competitor_score": 95},
                    {"feature": "Brand Recognition", "aria_score": 50, "competitor_score": 92},
                    {"feature": "Technical Expertise", "aria_score": 78, "competitor_score": 80},
                    {"feature": "Responsiveness", "aria_score": 85, "competitor_score": 65},
                ],
                "critical_gaps": [
                    {"description": "Higher touch, more personalized client experience", "is_advantage": True},
                    {"description": "Faster decision-making on scope changes", "is_advantage": True},
                    {"description": "More attention given to mid-market clients", "is_advantage": True},
                    {"description": "Competitor has vastly superior product portfolio breadth", "is_advantage": False},
                    {"description": "Competitor has stronger brand recognition globally", "is_advantage": False},
                ],
            },
            "update_source": "demo_seed",
            "last_updated": ts,
            "created_at": ts,
        },
        {
            "company_id": cid,
            "competitor_name": "WuXi AppTec",
            "competitor_domain": "wuxiapptec.com",
            "overview": "China-based CRO/CDMO with $5.9B revenue, offering significant cost and speed advantages. Massive scientific workforce of 30,000+ enables rapid program starts, but faces increasing geopolitical headwinds including the BIOSECURE Act and FDA scrutiny.",
            "strengths": [
                "30-40% cost advantage over Western CDMOs",
                "Fastest time from contract to first batch (typically 6-8 months)",
                "Massive capacity with 30,000+ scientists",
                "Strong in early-phase development and small molecule",
            ],
            "weaknesses": [
                "Geopolitical risk — BIOSECURE Act may restrict US government-funded work",
                "IP protection concerns despite improvements",
                "Regulatory uncertainty for US and EU market submissions",
                "Cultural and timezone challenges for project management",
            ],
            "pricing": {
                "model": "Per-project with milestone payments",
                "range": "$300K-$1.8M per program",
                "notes": "Typically 30-40% below US/EU CDMOs for comparable scope",
            },
            "differentiation": [
                {
                    "area": "US-Based Manufacturing",
                    "our_advantage": "100% US-based manufacturing eliminates BIOSECURE Act risk. Three of our current clients switched from WuXi specifically due to regulatory uncertainty around Chinese CDMOs.",
                },
                {
                    "area": "IP Protection",
                    "our_advantage": "US legal jurisdiction with standard NDAs and IP assignment vs navigating Chinese IP law. Our clients retain full ownership with US-enforceable protections.",
                },
                {
                    "area": "Regulatory Clarity",
                    "our_advantage": "Direct FDA engagement and pre-approval inspection support vs WuXi's remote regulatory submissions that add 3-6 months to approval timelines",
                },
            ],
            "objection_handlers": [
                {
                    "objection": "WuXi is 40% cheaper than any US option",
                    "response": "The sticker price is lower, but total cost tells a different story. Factor in: extended timelines for FDA back-and-forth (add 3-6 months), travel costs for oversight visits ($50K-$100K/year), IP insurance premiums, and the BIOSECURE Act risk premium. Our clients who've compared total cost find the gap is actually 10-15%, and they sleep better at night.",
                },
                {
                    "objection": "WuXi's speed to first batch is unbeatable",
                    "response": "WuXi is fast to first batch, but their overall timeline to IND is comparable to ours once you factor in the additional CMC documentation needed for FDA submissions from Chinese sites. Our 8-month start-to-IND timeline is competitive, and you avoid the 3-month shipping and import logistics that WuXi programs require.",
                },
            ],
            "analysis": {
                "metrics": {
                    "market_cap_gap": -3.1,
                    "win_rate": 68,
                    "pricing_delta": -5.7,
                    "last_signal_at": None,
                },
                "strategies": [
                    {
                        "title": "BIOSECURE Act Risk",
                        "description": "Lead with regulatory certainty — US-based manufacturing eliminates geopolitical risk",
                        "icon": "zap",
                        "agent": "Hunter",
                    },
                    {
                        "title": "IP Protection Story",
                        "description": "Emphasize US legal jurisdiction and enforceable IP protections",
                        "icon": "target",
                        "agent": "Strategist",
                    },
                    {
                        "title": "Total Cost Comparison",
                        "description": "Build a comprehensive cost model including travel, logistics, and risk premiums",
                        "icon": "clock",
                        "agent": "Operator",
                    },
                    {
                        "title": "FDA Direct Engagement",
                        "description": "Show value of direct FDA interactions vs remote submissions",
                        "icon": "shield",
                        "agent": "Analyst",
                    },
                ],
                "feature_gaps": [
                    {"feature": "US Manufacturing", "aria_score": 100, "competitor_score": 0},
                    {"feature": "IP Protection", "aria_score": 90, "competitor_score": 55},
                    {"feature": "Cost Competitiveness", "aria_score": 55, "competitor_score": 92},
                    {"feature": "Speed to First Batch", "aria_score": 70, "competitor_score": 88},
                    {"feature": "Regulatory Clarity", "aria_score": 85, "competitor_score": 50},
                    {"feature": "Scientific Workforce", "aria_score": 60, "competitor_score": 90},
                ],
                "critical_gaps": [
                    {"description": "100% US-based manufacturing eliminates BIOSECURE Act risk", "is_advantage": True},
                    {"description": "US legal jurisdiction with enforceable IP protections", "is_advantage": True},
                    {"description": "Direct FDA engagement and pre-approval inspection support", "is_advantage": True},
                    {"description": "Competitor has 30-40% lower sticker price", "is_advantage": False},
                    {"description": "Competitor has massive 30,000+ scientist workforce for rapid starts", "is_advantage": False},
                ],
            },
            "update_source": "demo_seed",
            "last_updated": ts,
            "created_at": ts,
        },
    ]

    result = client.table("battle_cards").insert(cards).execute()
    count = len(result.data)
    logger.info(f"  Inserted {count} battle_cards")
    return count


# ---------------------------------------------------------------------------
# Seed: Leads
# ---------------------------------------------------------------------------


def seed_leads(client: Client, user_id: str) -> dict[str, str]:
    """Seed 15 lead memories. Returns {company_name: lead_memory_id}."""
    logger.info("Seeding leads...")

    uid = str(user_id)
    seeded_at = now_iso()

    leads = [
        {
            "user_id": uid,
            "company_name": "Genentech",
            "lifecycle_stage": "opportunity",
            "status": "active",
            "health_score": 92,
            "expected_value": 2400000,
            "expected_close_date": future(45),
            "first_touch_at": ago(days=75),
            "last_activity_at": ago(days=2),
            "tags": ["tier-1", "biologics", "west-coast"],
            "metadata": {"demo": True, "seeded_at": seeded_at},
        },
        {
            "user_id": uid,
            "company_name": "Amgen",
            "lifecycle_stage": "opportunity",
            "status": "active",
            "health_score": 85,
            "expected_value": 1800000,
            "expected_close_date": future(60),
            "first_touch_at": ago(days=60),
            "last_activity_at": ago(days=3),
            "tags": ["tier-1", "biologics", "west-coast"],
            "metadata": {"demo": True, "seeded_at": seeded_at},
        },
        {
            "user_id": uid,
            "company_name": "Regeneron",
            "lifecycle_stage": "opportunity",
            "status": "active",
            "health_score": 78,
            "expected_value": 1500000,
            "expected_close_date": future(75),
            "first_touch_at": ago(days=50),
            "last_activity_at": ago(days=5),
            "tags": ["tier-1", "biologics", "east-coast"],
            "metadata": {"demo": True, "seeded_at": seeded_at},
        },
        {
            "user_id": uid,
            "company_name": "Moderna",
            "lifecycle_stage": "lead",
            "status": "active",
            "health_score": 71,
            "expected_value": 3200000,
            "expected_close_date": future(90),
            "first_touch_at": ago(days=30),
            "last_activity_at": ago(days=4),
            "tags": ["tier-1", "mrna", "east-coast"],
            "metadata": {"demo": True, "seeded_at": seeded_at},
        },
        {
            "user_id": uid,
            "company_name": "BioNTech",
            "lifecycle_stage": "lead",
            "status": "active",
            "health_score": 65,
            "expected_value": 2100000,
            "expected_close_date": future(100),
            "first_touch_at": ago(days=35),
            "last_activity_at": ago(days=7),
            "tags": ["tier-1", "mrna", "eu"],
            "metadata": {"demo": True, "seeded_at": seeded_at},
        },
        {
            "user_id": uid,
            "company_name": "Gilead Sciences",
            "lifecycle_stage": "opportunity",
            "status": "active",
            "health_score": 88,
            "expected_value": 1900000,
            "expected_close_date": future(50),
            "first_touch_at": ago(days=65),
            "last_activity_at": ago(days=1),
            "tags": ["tier-1", "biologics", "west-coast"],
            "metadata": {"demo": True, "seeded_at": seeded_at},
        },
        {
            "user_id": uid,
            "company_name": "Vertex Pharmaceuticals",
            "lifecycle_stage": "lead",
            "status": "active",
            "health_score": 58,
            "expected_value": 950000,
            "expected_close_date": future(110),
            "first_touch_at": ago(days=25),
            "last_activity_at": ago(days=10),
            "tags": ["tier-2", "biologics", "east-coast"],
            "metadata": {"demo": True, "seeded_at": seeded_at},
        },
        {
            "user_id": uid,
            "company_name": "AbbVie",
            "lifecycle_stage": "account",
            "status": "active",
            "health_score": 95,
            "expected_value": 4500000,
            "expected_close_date": future(30),
            "first_touch_at": ago(days=90),
            "last_activity_at": ago(days=1),
            "tags": ["tier-1", "biologics", "midwest"],
            "metadata": {"demo": True, "seeded_at": seeded_at},
        },
        {
            "user_id": uid,
            "company_name": "Bristol-Myers Squibb",
            "lifecycle_stage": "opportunity",
            "status": "active",
            "health_score": 74,
            "expected_value": 2800000,
            "expected_close_date": future(80),
            "first_touch_at": ago(days=55),
            "last_activity_at": ago(days=6),
            "tags": ["tier-1", "biologics", "east-coast"],
            "metadata": {"demo": True, "seeded_at": seeded_at},
        },
        {
            "user_id": uid,
            "company_name": "Novo Nordisk",
            "lifecycle_stage": "lead",
            "status": "active",
            "health_score": 45,
            "expected_value": 1200000,
            "expected_close_date": future(120),
            "first_touch_at": ago(days=20),
            "last_activity_at": ago(days=14),
            "tags": ["tier-1", "fill-finish", "eu"],
            "metadata": {"demo": True, "seeded_at": seeded_at},
        },
        {
            "user_id": uid,
            "company_name": "Jazz Pharmaceuticals",
            "lifecycle_stage": "lead",
            "status": "active",
            "health_score": 52,
            "expected_value": 680000,
            "expected_close_date": future(105),
            "first_touch_at": ago(days=28),
            "last_activity_at": ago(days=11),
            "tags": ["tier-2", "biologics", "west-coast"],
            "metadata": {"demo": True, "seeded_at": seeded_at},
        },
        {
            "user_id": uid,
            "company_name": "Sarepta Therapeutics",
            "lifecycle_stage": "opportunity",
            "status": "active",
            "health_score": 81,
            "expected_value": 1600000,
            "expected_close_date": future(55),
            "first_touch_at": ago(days=45),
            "last_activity_at": ago(days=3),
            "tags": ["tier-2", "gene-therapy", "east-coast"],
            "metadata": {"demo": True, "seeded_at": seeded_at},
        },
        {
            "user_id": uid,
            "company_name": "Alnylam Pharmaceuticals",
            "lifecycle_stage": "lead",
            "status": "active",
            "health_score": 38,
            "expected_value": 750000,
            "expected_close_date": future(115),
            "first_touch_at": ago(days=18),
            "last_activity_at": ago(days=12),
            "tags": ["tier-2", "rnai", "east-coast"],
            "metadata": {"demo": True, "seeded_at": seeded_at},
        },
        {
            "user_id": uid,
            "company_name": "Biogen",
            "lifecycle_stage": "account",
            "status": "won",
            "health_score": 91,
            "expected_value": 3100000,
            "expected_close_date": future(30),
            "first_touch_at": ago(days=85),
            "last_activity_at": ago(days=2),
            "tags": ["tier-1", "biologics", "east-coast"],
            "metadata": {"demo": True, "seeded_at": seeded_at},
        },
        {
            "user_id": uid,
            "company_name": "Alexion (AstraZeneca)",
            "lifecycle_stage": "opportunity",
            "status": "active",
            "health_score": 69,
            "expected_value": 2200000,
            "expected_close_date": future(85),
            "first_touch_at": ago(days=40),
            "last_activity_at": ago(days=8),
            "tags": ["tier-1", "biologics", "east-coast"],
            "metadata": {"demo": True, "seeded_at": seeded_at},
        },
    ]

    result = client.table("lead_memories").insert(leads).execute()
    count = len(result.data)
    logger.info(f"  Inserted {count} lead_memories")

    # Build lookup map: company_name -> id
    lead_map: dict[str, str] = {}
    for row in result.data:
        lead_map[row["company_name"]] = row["id"]

    return lead_map


# ---------------------------------------------------------------------------
# Seed: Stakeholders
# ---------------------------------------------------------------------------


def seed_stakeholders(client: Client, lead_map: dict[str, str]) -> int:
    """Seed ~35 stakeholders across all leads."""
    logger.info("Seeding stakeholders...")

    def _s(
        company: str,
        name: str,
        email: str,
        title: str,
        role: str,
        influence: int,
        sentiment: str,
        style: str,
        days_since_contact: int,
        notes: str | None = None,
    ) -> dict[str, Any]:
        return {
            "lead_memory_id": lead_map[company],
            "contact_name": name,
            "contact_email": email,
            "title": title,
            "role": role,
            "influence_level": influence,
            "sentiment": sentiment,
            "last_contacted_at": ago(days=days_since_contact) if days_since_contact else None,
            "notes": notes,
            "personality_insights": {
                "communication_style": style,
                "demo": True,
            },
        }

    stakeholders = [
        # --- Genentech (3) ---
        _s(
            "Genentech",
            "Sarah Kim",
            "sarah.kim@genentech.com",
            "VP Manufacturing",
            "champion",
            9,
            "positive",
            "data-driven",
            2,
            "Strong advocate for single-use bioreactors. Led site visit in January. Key relationship to nurture.",
        ),
        _s(
            "Genentech",
            "James Chen",
            "james.chen@genentech.com",
            "Dir Procurement",
            "decision_maker",
            8,
            "positive",
            "direct",
            5,
            "Controls budget allocation for external manufacturing. Prefers concise proposals with clear ROI.",
        ),
        _s(
            "Genentech",
            "Dr. Lisa Park",
            "lisa.park@genentech.com",
            "Sr Scientist",
            "influencer",
            5,
            "neutral",
            "relationship-focused",
            14,
            "Evaluates technical capabilities. Needs to see process development data before endorsing.",
        ),
        # --- Amgen (3) ---
        _s(
            "Amgen",
            "Robert Nakamura",
            "robert.nakamura@amgen.com",
            "SVP Operations",
            "decision_maker",
            10,
            "positive",
            "direct",
            3,
            "C-suite sponsor. Values speed and reliability above all else. Reports directly to CEO.",
        ),
        _s(
            "Amgen",
            "Maria Santos",
            "maria.santos@amgen.com",
            "Dir Process Development",
            "champion",
            7,
            "positive",
            "data-driven",
            7,
            "Technical champion who has used our platform at a previous company. Strong internal advocate.",
        ),
        _s(
            "Amgen",
            "David Liu",
            "david.liu@amgen.com",
            "Procurement Manager",
            "influencer",
            5,
            "neutral",
            "data-driven",
            10,
            "Handles vendor qualification. Focused on compliance documentation and audit readiness.",
        ),
        # --- Regeneron (2) ---
        _s(
            "Regeneron",
            "Dr. Jennifer Walsh",
            "jennifer.walsh@regeneron.com",
            "VP Biologics Manufacturing",
            "decision_maker",
            9,
            "neutral",
            "data-driven",
            5,
            "Technical decision-maker. Requires detailed process comparisons before advancing discussions.",
        ),
        _s(
            "Regeneron",
            "Thomas Martinez",
            "thomas.martinez@regeneron.com",
            "Dir Supply Chain",
            "influencer",
            6,
            "positive",
            "relationship-focused",
            8,
            "Manages external supply network. Interested in supply chain resilience and backup capacity.",
        ),
        # --- Moderna (2) ---
        _s(
            "Moderna",
            "Dr. Richard Huang",
            "richard.huang@modernatx.com",
            "Chief Manufacturing Officer",
            "decision_maker",
            10,
            "neutral",
            "direct",
            4,
            "Top manufacturing executive. Samsung Biologics deal covers bulk DS but still needs fill-finish partners.",
        ),
        _s(
            "Moderna",
            "Amanda Foster",
            "amanda.foster@modernatx.com",
            "VP External Supply",
            "influencer",
            7,
            "neutral",
            "data-driven",
            9,
            "Manages all CDMO relationships. Currently evaluating 3 potential partners for non-vaccine pipeline.",
        ),
        # --- BioNTech (3) ---
        _s(
            "BioNTech",
            "Klaus Weber",
            "klaus.weber@biontech.de",
            "Head of CDMO Relations",
            "decision_maker",
            9,
            "neutral",
            "direct",
            7,
            "Primary decision-maker for external manufacturing partnerships. Concerned about Catalent stability.",
        ),
        _s(
            "BioNTech",
            "Dr. Anna Schneider",
            "anna.schneider@biontech.de",
            "Dir Technical Operations",
            "influencer",
            6,
            "positive",
            "data-driven",
            10,
            "Technical evaluator. Impressed by our mRNA handling capabilities during initial discussions.",
        ),
        _s(
            "BioNTech",
            "Hans Mueller",
            "hans.mueller@biontech.de",
            "Procurement Lead",
            "blocker",
            7,
            "negative",
            "direct",
            12,
            "Resistant to switching CDMOs due to perceived transition costs. Needs total-cost-of-ownership analysis.",
        ),
        # --- Gilead Sciences (2) ---
        _s(
            "Gilead Sciences",
            "Patricia Rodriguez",
            "patricia.rodriguez@gilead.com",
            "VP Manufacturing Sciences",
            "champion",
            8,
            "positive",
            "relationship-focused",
            1,
            "Long-standing relationship. Previously worked with our team at prior company. Strong internal advocate.",
        ),
        _s(
            "Gilead Sciences",
            "Dr. Kevin Patel",
            "kevin.patel@gilead.com",
            "Dir Quality Assurance",
            "influencer",
            6,
            "neutral",
            "data-driven",
            6,
            "Quality gatekeeper. Will require full quality dossier and facility audit before sign-off.",
        ),
        # --- Vertex Pharmaceuticals (2) ---
        _s(
            "Vertex Pharmaceuticals",
            "Dr. Michael Chang",
            "michael.chang@vrtx.com",
            "Dir Biologics",
            "decision_maker",
            8,
            "neutral",
            "data-driven",
            10,
            "Leading Vertex's push into biologics manufacturing. Evaluating multiple CDMOs for new pipeline.",
        ),
        _s(
            "Vertex Pharmaceuticals",
            "Rachel Thompson",
            "rachel.thompson@vrtx.com",
            "Sr Mgr External Manufacturing",
            "influencer",
            5,
            "neutral",
            "relationship-focused",
            13,
            "Day-to-day contact for external manufacturing. Values responsiveness and communication frequency.",
        ),
        # --- AbbVie (3) ---
        _s(
            "AbbVie",
            "William O'Brien",
            "william.obrien@abbvie.com",
            "VP Global Manufacturing",
            "decision_maker",
            10,
            "positive",
            "direct",
            1,
            "Executive sponsor for renewal. Has publicly praised our partnership at industry conferences.",
        ),
        _s(
            "AbbVie",
            "Catherine Lee",
            "catherine.lee@abbvie.com",
            "Dir Procurement",
            "champion",
            8,
            "positive",
            "data-driven",
            3,
            "Driving the renewal process. Requested multi-year pricing options with expanded scope.",
        ),
        _s(
            "AbbVie",
            "Frank Morrison",
            "frank.morrison@abbvie.com",
            "Plant Director",
            "influencer",
            7,
            "positive",
            "relationship-focused",
            5,
            "Oversees the dedicated suite. Extremely satisfied with operational performance and team continuity.",
        ),
        # --- Bristol-Myers Squibb (3) ---
        _s(
            "Bristol-Myers Squibb",
            "Dr. Susan Park",
            "susan.park@bms.com",
            "SVP Biologics Operations",
            "decision_maker",
            10,
            "neutral",
            "direct",
            6,
            "Senior decision-maker. Methodical evaluation process — expects detailed proposal before advancing.",
        ),
        _s(
            "Bristol-Myers Squibb",
            "Andrew Kim",
            "andrew.kim@bms.com",
            "VP Procurement",
            "influencer",
            7,
            "neutral",
            "data-driven",
            8,
            "Procurement lead for CDMO contracts. Benchmarks all proposals against 3+ competitors.",
        ),
        _s(
            "Bristol-Myers Squibb",
            "Dr. Emily Rhodes",
            "emily.rhodes@bms.com",
            "Dir Technology Transfer",
            "champion",
            7,
            "positive",
            "data-driven",
            4,
            "Technical champion. Experienced a smooth tech transfer with us on a previous program and advocates internally.",
        ),
        # --- Novo Nordisk (2) ---
        _s(
            "Novo Nordisk",
            "Henrik Larsen",
            "henrik.larsen@novonordisk.com",
            "VP Fill-Finish Operations",
            "decision_maker",
            9,
            "neutral",
            "direct",
            14,
            "Key decision-maker for fill-finish partnerships. Currently evaluating US-based options for GLP-1 portfolio.",
        ),
        _s(
            "Novo Nordisk",
            "Mette Andersen",
            "mette.andersen@novonordisk.com",
            "Global Procurement Director",
            "blocker",
            8,
            "negative",
            "data-driven",
            14,
            "Skeptical of newer CDMOs. Prefers established relationships and requires extensive financial due diligence.",
        ),
        # --- Jazz Pharmaceuticals (2) ---
        _s(
            "Jazz Pharmaceuticals",
            "Brian Murphy",
            "brian.murphy@jazzpharma.com",
            "Dir External Manufacturing",
            "decision_maker",
            8,
            "neutral",
            "direct",
            11,
            "Primary contact for external manufacturing decisions. Budget-conscious, needs clear value proposition.",
        ),
        _s(
            "Jazz Pharmaceuticals",
            "Siobhan Kelly",
            "siobhan.kelly@jazzpharma.com",
            "Sr Buyer",
            "influencer",
            4,
            "neutral",
            "relationship-focused",
            13,
            "Handles procurement logistics. Good relationship but limited influence on strategic decisions.",
        ),
        # --- Sarepta Therapeutics (2) ---
        _s(
            "Sarepta Therapeutics",
            "Dr. Yuki Tanaka",
            "yuki.tanaka@sarepta.com",
            "VP Gene Therapy Manufacturing",
            "decision_maker",
            9,
            "positive",
            "data-driven",
            3,
            "Leading Sarepta's CDMO evaluation for commercial gene therapy programs. Technically rigorous.",
        ),
        _s(
            "Sarepta Therapeutics",
            "Christopher Evans",
            "christopher.evans@sarepta.com",
            "Dir CMC",
            "champion",
            7,
            "positive",
            "relationship-focused",
            5,
            "CMC lead who values transparent communication. Has been our internal champion since initial technical review.",
        ),
        # --- Alnylam Pharmaceuticals (2) ---
        _s(
            "Alnylam Pharmaceuticals",
            "Dr. Priya Sharma",
            "priya.sharma@alnylam.com",
            "Dir Manufacturing",
            "decision_maker",
            8,
            "neutral",
            "data-driven",
            12,
            "Manufacturing lead evaluating CDMO options for RNAi therapeutic pipeline expansion.",
        ),
        _s(
            "Alnylam Pharmaceuticals",
            "Jason Mitchell",
            "jason.mitchell@alnylam.com",
            "Procurement Analyst",
            "influencer",
            4,
            "negative",
            "direct",
            14,
            "Cost-focused analyst. Has expressed concern about our pricing relative to offshore alternatives.",
        ),
        # --- Biogen (3) ---
        _s(
            "Biogen",
            "Margaret O'Sullivan",
            "margaret.osullivan@biogen.com",
            "VP Manufacturing",
            "champion",
            9,
            "positive",
            "relationship-focused",
            2,
            "Executive champion for our partnership. Instrumental in securing the initial contract win.",
        ),
        _s(
            "Biogen",
            "Daniel Park",
            "daniel.park@biogen.com",
            "Dir Supply Planning",
            "decision_maker",
            8,
            "positive",
            "data-driven",
            3,
            "Manages supply planning and forecasting. Appreciates our forecast accuracy and delivery reliability.",
        ),
        _s(
            "Biogen",
            "Dr. Nancy Chen",
            "nancy.chen@biogen.com",
            "Quality VP",
            "influencer",
            7,
            "positive",
            "data-driven",
            4,
            "Quality oversight. Conducted 2 successful audits of our facility with zero critical findings.",
        ),
        # --- Alexion / AstraZeneca (2) ---
        _s(
            "Alexion (AstraZeneca)",
            "Stefan Andersson",
            "stefan.andersson@alexion.com",
            "Head of Biologics Supply",
            "decision_maker",
            9,
            "neutral",
            "direct",
            8,
            "Senior supply chain leader. Evaluating CDMO consolidation across AstraZeneca's biologics portfolio.",
        ),
        _s(
            "Alexion (AstraZeneca)",
            "Laura Bennett",
            "laura.bennett@alexion.com",
            "Dir External Partnerships",
            "influencer",
            6,
            "positive",
            "relationship-focused",
            6,
            "Partnership manager with positive view of our capabilities. Good internal relationships to leverage.",
        ),
    ]

    result = client.table("lead_memory_stakeholders").insert(stakeholders).execute()
    count = len(result.data)
    logger.info(f"  Inserted {count} lead_memory_stakeholders")
    return count


# ---------------------------------------------------------------------------
# Seed: Email Drafts
# ---------------------------------------------------------------------------


def seed_email_drafts(client: Client, user_id: str, lead_map: dict[str, str]) -> int:
    """Seed 3 email drafts."""
    logger.info("Seeding email drafts...")

    uid = str(user_id)

    drafts = [
        {
            "user_id": uid,
            "recipient_email": "sarah.kim@genentech.com",
            "recipient_name": "Sarah Kim",
            "subject": "Following up on single-use bioreactor discussion",
            "body": (
                "Hi Sarah,\n\n"
                "Thank you for hosting us at the South San Francisco campus last week. "
                "It was great to see your team's biologics operation firsthand, and I appreciated "
                "the candid discussion about your Q2 capacity planning challenges.\n\n"
                "As we discussed, our single-use bioreactor platform (50L-2000L) offers the flexibility "
                "your CHO cell culture programs need without the long lead times of stainless steel "
                "changeovers. Based on your production schedule, we could have a dedicated suite operational "
                "within 4 months — well ahead of your Q3 campaign start.\n\n"
                "I'd love to invite you and James for a site visit to see our single-use suites in action. "
                "We have a 500L CHO campaign running next month that closely mirrors your process parameters. "
                "Would the week of March 10th work for your team?\n\n"
                "Looking forward to continuing the conversation.\n\n"
                "Best regards"
            ),
            "purpose": "follow_up",
            "tone": "friendly",
            "status": "draft",
            "context": {
                "demo": True,
                "user_context": "Discussed single-use bioreactor options during last site visit. Sarah was enthusiastic about flexibility.",
            },
            "lead_memory_id": lead_map.get("Genentech"),
            "style_match_score": 0.91,
        },
        {
            "user_id": uid,
            "recipient_email": "richard.huang@modernatx.com",
            "recipient_name": "Dr. Richard Huang",
            "subject": "Flexible manufacturing capacity for mRNA programs",
            "body": (
                "Dear Dr. Huang,\n\n"
                "I'm reaching out regarding a manufacturing capability that may be relevant as "
                "Moderna expands its mRNA therapeutic pipeline beyond vaccines. With your recent "
                "Samsung Biologics agreement covering bulk drug substance, I understand there's "
                "an emerging need for specialized formulation and fill-finish partners — particularly "
                "for the rare disease and oncology programs in your expanding portfolio.\n\n"
                "Our facility has invested significantly in lipid nanoparticle formulation and "
                "aseptic fill-finish capabilities specifically designed for mRNA therapeutics. "
                "We offer dedicated suites with the controlled environment and specialized "
                "handling that mRNA products require, with the flexibility to support programs "
                "from clinical through commercial scale.\n\n"
                "I would welcome the opportunity to discuss how our capabilities might complement "
                "your manufacturing strategy. Would you or a member of your external supply team "
                "be available for a brief introductory call in the coming weeks?\n\n"
                "Respectfully"
            ),
            "purpose": "intro",
            "tone": "formal",
            "status": "draft",
            "context": {
                "demo": True,
                "user_context": "Moderna expanding mRNA pipeline beyond vaccines. Manufacturing capacity is a known bottleneck.",
            },
            "lead_memory_id": lead_map.get("Moderna"),
            "style_match_score": 0.87,
        },
        {
            "user_id": uid,
            "recipient_email": "yuki.tanaka@sarepta.com",
            "recipient_name": "Dr. Yuki Tanaka",
            "subject": "Gene therapy CDMO partnership proposal",
            "body": (
                "Dear Dr. Tanaka,\n\n"
                "Following our productive discussions over the past several weeks, I am pleased to "
                "formally propose a manufacturing partnership to support Sarepta's gene therapy programs "
                "as they advance toward commercial launch.\n\n"
                "Our proposal addresses the three priorities you identified during our technical review: "
                "AAV vector production scalability, consistent viral titer yields, and regulatory readiness "
                "for BLA submissions. Specifically, we are proposing:\n\n"
                "1. Dedicated AAV manufacturing suite with 200L-2000L suspension culture capability\n"
                "2. Process development program to optimize your serotype-specific yields (targeting >1E14 vg/L)\n"
                "3. Full CMC package aligned with recent FDA guidance on gene therapy manufacturing controls\n"
                "4. Dedicated project team from process development through commercial validation\n\n"
                "Our timeline projects first GMP batch within 8 months of contract execution, with "
                "BLA-readiness within 18 months. This positions Sarepta well for your anticipated "
                "2027 filing timeline.\n\n"
                "I have attached a detailed technical proposal and would welcome the opportunity to "
                "review it with you and Christopher. Would next Tuesday or Thursday work for a "
                "90-minute deep-dive session?\n\n"
                "Best regards"
            ),
            "purpose": "proposal",
            "tone": "formal",
            "status": "sent",
            "context": {
                "demo": True,
                "user_context": "Sarepta moving multiple gene therapy programs toward commercial. Need reliable AAV manufacturing partner.",
            },
            "lead_memory_id": lead_map.get("Sarepta Therapeutics"),
            "style_match_score": 0.93,
            "sent_at": ago(days=1),
        },
    ]

    result = client.table("email_drafts").insert(drafts).execute()
    count = len(result.data)
    logger.info(f"  Inserted {count} email_drafts")
    return count


# ---------------------------------------------------------------------------
# Seed: Market Signals
# ---------------------------------------------------------------------------


def seed_market_signals(client: Client, user_id: str) -> int:
    """Seed 5 market signals."""
    logger.info("Seeding market signals...")

    uid = str(user_id)

    signals = [
        {
            "user_id": uid,
            "company_name": "Catalent",
            "signal_type": "leadership_change",
            "headline": "Catalent CFO Resigns Amid Restructuring",
            "summary": (
                "Catalent's Chief Financial Officer announced departure effective March 2026 "
                "as the company undergoes significant operational restructuring. This follows two "
                "FDA warning letters and a 15% workforce reduction announced in Q4 2025. The "
                "leadership vacuum may create instability in ongoing client programs and opens "
                "a window for competitive displacement."
            ),
            "source_url": "https://www.biopharmadive.com/catalent-cfo-restructuring",
            "source_name": "BioPharma Dive",
            "relevance_score": 0.92,
            "detected_at": ago(days=2),
            "read_at": ago(days=1),
            "metadata": {"demo": True, "impact": "high", "actionable": True},
        },
        {
            "user_id": uid,
            "company_name": "Repligen",
            "signal_type": "acquisition",
            "headline": "Repligen Acquires FlexBiosys for $380M",
            "summary": (
                "Repligen Corporation announced the acquisition of FlexBiosys, expanding their "
                "single-use bioprocessing portfolio. The $380M deal adds flexible manufacturing "
                "bag systems and tubing assemblies to Repligen's filtration and chromatography "
                "lineup. This positions Repligen as a more comprehensive equipment supplier but "
                "still lacks end-to-end CDMO services."
            ),
            "source_url": "https://www.fiercepharma.com/repligen-flexbiosys-acquisition",
            "source_name": "Fierce Pharma",
            "relevance_score": 0.88,
            "detected_at": ago(days=5),
            "read_at": ago(days=4),
            "metadata": {"demo": True, "impact": "medium", "actionable": True},
        },
        {
            "user_id": uid,
            "company_name": "Genentech",
            "signal_type": "expansion",
            "headline": "Genentech Expands South San Francisco Biologics Facility",
            "summary": (
                "Genentech is investing $800M in expanding their South San Francisco campus with "
                "a new 200,000 sq ft biologics manufacturing building. Construction begins Q2 2026 "
                "with expected completion in 2028. In the interim, external manufacturing partnerships "
                "will be critical to meet pipeline demand — creating a 2-year window for CDMO engagement."
            ),
            "source_url": "https://www.reuters.com/genentech-ssf-expansion",
            "source_name": "Reuters",
            "relevance_score": 0.85,
            "detected_at": ago(days=1),
            "metadata": {"demo": True, "impact": "high", "actionable": True},
        },
        {
            "user_id": uid,
            "company_name": "WuXi AppTec",
            "signal_type": "regulatory",
            "headline": "FDA Warning Letter to WuXi Biologics Shanghai Site",
            "summary": (
                "The FDA issued a warning letter to WuXi Biologics' Shanghai manufacturing site "
                "citing data integrity issues and inadequate contamination controls. This affects "
                "12+ active client programs and reinforces concerns about quality oversight at "
                "offshore manufacturing sites. Clients with WuXi programs may accelerate "
                "nearshoring evaluations."
            ),
            "source_url": "https://www.fda.gov/inspections-compliance/warning-letters/wuxi-2026",
            "source_name": "FDA.gov",
            "relevance_score": 0.95,
            "detected_at": ago(days=3),
            "read_at": ago(days=3),
            "metadata": {"demo": True, "impact": "critical", "actionable": True},
        },
        {
            "user_id": uid,
            "company_name": "Moderna",
            "signal_type": "partnership",
            "headline": "Moderna Signs $1.2B Manufacturing Agreement with Samsung Biologics",
            "summary": (
                "Moderna entered a 5-year, $1.2B manufacturing agreement with Samsung Biologics "
                "for mRNA therapeutic production. While this secures bulk drug substance capacity, "
                "Moderna still needs formulation and fill-finish partners for their expanding "
                "non-vaccine pipeline — particularly for rare disease and oncology programs."
            ),
            "source_url": "https://www.endpoints.com/moderna-samsung-deal",
            "source_name": "Endpoints News",
            "relevance_score": 0.79,
            "detected_at": ago(days=7),
            "read_at": ago(days=6),
            "metadata": {"demo": True, "impact": "medium", "actionable": True},
        },
    ]

    result = client.table("market_signals").insert(signals).execute()
    count = len(result.data)
    logger.info(f"  Inserted {count} market_signals")
    return count


# ---------------------------------------------------------------------------
# Seed: Goals + Agents
# ---------------------------------------------------------------------------


def seed_goals(client: Client, user_id: str) -> int:
    """Seed 2 goals with 6 agents total."""
    logger.info("Seeding goals and agents...")

    uid = str(user_id)

    goals = [
        {
            "user_id": uid,
            "title": "Expand Repligen Relationship into CDMO Services",
            "description": (
                "Leverage existing Repligen equipment relationship to position our CDMO services "
                "as complementary to their hardware. Target 3 Repligen accounts currently using "
                "competitor CDMOs for a combined pipeline value of $4.5M."
            ),
            "goal_type": "outreach",
            "status": "active",
            "progress": 65,
            "started_at": ago(days=14),
            "config": {
                "demo": True,
                "target_accounts": ["Genentech", "Amgen", "Regeneron"],
                "target_value": 4500000,
            },
            "strategy": {
                "phase": "execution",
                "milestones": [
                    {
                        "title": "Map Repligen equipment users in target accounts",
                        "status": "complete",
                    },
                    {
                        "title": "Develop co-marketing positioning with Repligen sales team",
                        "status": "complete",
                    },
                    {
                        "title": "Secure introductions through Repligen channel partners",
                        "status": "in_progress",
                    },
                    {
                        "title": "Schedule discovery calls with 3 target accounts",
                        "status": "pending",
                    },
                ],
                "competitive_positioning": (
                    "Position as natural extension of Repligen equipment investment — "
                    "same workflow, integrated manufacturing"
                ),
            },
        },
        {
            "user_id": uid,
            "title": "Win Catalent Displacement at BioNTech",
            "description": (
                "Capitalize on Catalent quality issues and CFO departure to position as a "
                "reliable alternative for BioNTech's European manufacturing needs. Target: "
                "displace Catalent as primary CDMO for BioNTech's mRNA therapeutic programs."
            ),
            "goal_type": "analysis",
            "status": "active",
            "progress": 30,
            "started_at": ago(days=7),
            "config": {
                "demo": True,
                "target_account": "BioNTech",
                "displacement_target": "Catalent",
                "estimated_value": 2100000,
            },
            "strategy": {
                "phase": "research",
                "milestones": [
                    {
                        "title": "Analyze Catalent quality issues and impact on BioNTech programs",
                        "status": "complete",
                    },
                    {
                        "title": "Map BioNTech decision-making committee for CDMO selection",
                        "status": "in_progress",
                    },
                    {"title": "Prepare competitive displacement proposal", "status": "pending"},
                    {
                        "title": "Engage BioNTech procurement through existing relationship",
                        "status": "pending",
                    },
                ],
                "key_leverage": (
                    "Catalent's FDA warning letters and CFO departure signal instability — "
                    "BioNTech's procurement team has expressed concerns internally"
                ),
            },
        },
    ]

    result = client.table("goals").insert(goals).execute()
    goal_count = len(result.data)
    logger.info(f"  Inserted {goal_count} goals")

    # Build agent records keyed by goal title
    goal_ids: dict[str, str] = {}
    for row in result.data:
        goal_ids[row["title"]] = row["id"]

    agents = [
        # Goal 1 agents
        {
            "goal_id": goal_ids["Expand Repligen Relationship into CDMO Services"],
            "agent_type": "hunter",
            "agent_config": {},
            "status": "complete",
        },
        {
            "goal_id": goal_ids["Expand Repligen Relationship into CDMO Services"],
            "agent_type": "analyst",
            "agent_config": {},
            "status": "running",
        },
        {
            "goal_id": goal_ids["Expand Repligen Relationship into CDMO Services"],
            "agent_type": "scribe",
            "agent_config": {},
            "status": "pending",
        },
        # Goal 2 agents
        {
            "goal_id": goal_ids["Win Catalent Displacement at BioNTech"],
            "agent_type": "strategist",
            "agent_config": {},
            "status": "running",
        },
        {
            "goal_id": goal_ids["Win Catalent Displacement at BioNTech"],
            "agent_type": "scout",
            "agent_config": {},
            "status": "running",
        },
        {
            "goal_id": goal_ids["Win Catalent Displacement at BioNTech"],
            "agent_type": "analyst",
            "agent_config": {},
            "status": "pending",
        },
    ]

    agent_result = client.table("goal_agents").insert(agents).execute()
    agent_count = len(agent_result.data)
    logger.info(f"  Inserted {agent_count} goal_agents")

    return goal_count


# ---------------------------------------------------------------------------
# Seed: Action Queue
# ---------------------------------------------------------------------------


def seed_action_queue(client: Client, user_id: str) -> int:
    """Seed 2 action queue items."""
    logger.info("Seeding action queue...")

    uid = str(user_id)

    actions = [
        {
            "user_id": uid,
            "agent": "strategist",
            "action_type": "research",
            "title": "Draft competitive comparison for BioNTech procurement team",
            "description": (
                "Create a detailed side-by-side comparison of our capabilities vs Catalent for "
                "BioNTech's mRNA therapeutic manufacturing needs, highlighting quality track record, "
                "timeline reliability, and total cost of ownership."
            ),
            "risk_level": "medium",
            "status": "pending",
            "payload": {
                "demo": True,
                "target_account": "BioNTech",
                "competitor": "Catalent",
                "deliverable": "competitive_comparison_doc",
            },
            "reasoning": (
                "BioNTech's procurement lead Hans Mueller raised concerns about switching costs "
                "in last week's call. A data-driven comparison document addressing his specific "
                "objections around cost and timeline risk would advance the displacement conversation. "
                "This requires ARIA's competitive intelligence analysis capabilities."
            ),
            "result": {},
        },
        {
            "user_id": uid,
            "agent": "operator",
            "action_type": "crm_update",
            "title": "Update CRM with Genentech meeting notes",
            "description": (
                "Sync notes from last week's Genentech site visit into Salesforce, including "
                "single-use bioreactor discussion points and next steps with Sarah Kim."
            ),
            "risk_level": "low",
            "status": "completed",
            "payload": {
                "demo": True,
                "crm_provider": "salesforce",
                "lead": "Genentech",
                "update_type": "meeting_notes",
            },
            "reasoning": (
                "Meeting notes from Feb 7 Genentech visit haven't been logged in CRM. "
                "Auto-approving as low-risk CRM data entry to keep records current."
            ),
            "result": {
                "synced": True,
                "fields_updated": ["last_activity", "notes", "next_steps"],
            },
            "approved_at": ago(hours=1),
            "completed_at": ago(hours=1),
        },
    ]

    result = client.table("aria_action_queue").insert(actions).execute()
    count = len(result.data)
    logger.info(f"  Inserted {count} aria_action_queue items")
    return count


# ---------------------------------------------------------------------------
# Seed: Meetings
# ---------------------------------------------------------------------------


def seed_meetings(client: Client, user_id: str) -> int:
    """Seed 3 meeting briefs."""
    logger.info("Seeding meeting briefs...")

    uid = str(user_id)

    meetings = [
        {
            "user_id": uid,
            "calendar_event_id": "demo_meeting_1",
            "meeting_title": "Morning Pipeline Review",
            "meeting_time": today_at(9, 0),
            "attendees": ["Dhruv Patwardhan", "Sales Team"],
            "status": "completed",
            "generated_at": today_at(8, 30),
            "brief_content": {
                "demo": True,
                "summary": (
                    "Weekly pipeline review covering 15 active opportunities totaling $33.6M. "
                    "Key focus: Genentech Q2 planning call prep and Catalent displacement strategy at BioNTech."
                ),
                "key_points": [
                    "Genentech health score improved to 92 after positive site visit",
                    "BioNTech Catalent displacement goal at 30% — need stakeholder mapping",
                    "AbbVie renewal ($4.5M) on track, all stakeholders positive",
                    "New lead: Alnylam showing early interest in RNAi manufacturing",
                ],
                "action_items": [
                    "Prepare Genentech Q2 planning call deck",
                    "Review Catalent competitive comparison draft",
                    "Schedule follow-up with Vertex Dir Biologics",
                ],
            },
        },
        {
            "user_id": uid,
            "calendar_event_id": "demo_meeting_2",
            "meeting_title": "Genentech Q2 Planning Call",
            "meeting_time": today_at(14, 0),
            "attendees": ["Dhruv Patwardhan", "Sarah Kim", "James Chen"],
            "status": "pending",
            "brief_content": {
                "demo": True,
                "summary": (
                    "Q2 capacity planning discussion with Genentech manufacturing team. "
                    "Sarah Kim (VP Mfg, champion) and James Chen (Dir Procurement, decision-maker) attending."
                ),
                "key_points": [
                    "Sarah enthusiastic about single-use bioreactor flexibility — reinforce with data",
                    "James will want pricing details — prepare tiered proposal options",
                    "Genentech expanding SSF campus but needs interim CDMO capacity (2-year window)",
                    "Competitor intelligence: Lonza currently quoting 12-month lead time for comparable program",
                ],
                "talking_points": [
                    "Reference their CHO cell culture programs and our 50L-2000L flexibility",
                    "Position dedicated suite model vs Lonza's shared facility queue",
                    "Propose pilot batch to demonstrate speed advantage",
                ],
            },
        },
        {
            "user_id": uid,
            "calendar_event_id": "demo_meeting_3",
            "meeting_title": "Weekly Forecast Review with Leadership",
            "meeting_time": today_at(16, 30),
            "attendees": ["Dhruv Patwardhan", "Executive Team"],
            "status": "pending",
            "brief_content": {
                "demo": True,
                "summary": (
                    "Weekly forecast review with executive leadership team. Total pipeline: $33.6M "
                    "across 15 opportunities. Weighted pipeline: $22.1M based on health scores."
                ),
                "key_points": [
                    "Pipeline grew 8% week-over-week with Moderna lead qualification",
                    "Win probability improved on 3 accounts (Genentech, Gilead, Sarepta)",
                    "Risk flag: Alnylam health score dropped to 38 — procurement analyst showing negative sentiment",
                    "Catalent market disruption creating 3 potential displacement opportunities",
                ],
                "forecast_summary": {
                    "total_pipeline": 33600000,
                    "weighted_pipeline": 22100000,
                    "expected_closes_q2": 3,
                    "expected_q2_value": 9400000,
                },
            },
        },
    ]

    result = client.table("meeting_briefs").insert(meetings).execute()
    count = len(result.data)
    logger.info(f"  Inserted {count} meeting_briefs")
    return count


# ---------------------------------------------------------------------------
# Seed: Tavus Briefing
# ---------------------------------------------------------------------------


def seed_tavus_briefing(client: Client, user_id: str) -> None:
    """Seed video session and briefing context for Tavus avatar."""
    logger.info("Seeding Tavus briefing session...")

    uid = str(user_id)

    # 1. Insert video session
    video_session = {
        "user_id": uid,
        "tavus_conversation_id": "demo_briefing",
        "session_type": "briefing",
        "status": "created",
    }
    result = client.table("video_sessions").insert(video_session).execute()
    logger.info(f"  Inserted {len(result.data)} video_sessions")

    # 2. Upsert briefing context into user_settings
    briefing_context = {
        "briefing_context": {
            "greeting": "Good morning Dhruv. I've prepared your daily briefing.",
            "key_highlights": [
                "Genentech pipeline progressing well — health score at 92, Q2 planning call at 2 PM today",
                "Catalent CFO resignation creates displacement opportunity at BioNTech — goal is 30% complete",
                "Repligen relationship expansion on track at 65% — analyst agent currently mapping stakeholder network",
                "FDA warning letter to WuXi Shanghai may accelerate nearshoring conversations with 3 prospects",
                "AbbVie account renewal ($4.5M) on track — all stakeholders showing positive sentiment",
            ],
            "demo": True,
        }
    }

    # Try to fetch existing user_settings
    existing = client.table("user_settings").select("id, preferences").eq("user_id", uid).execute()

    if existing.data and len(existing.data) > 0:
        # Merge briefing_context into existing preferences
        current_prefs = existing.data[0].get("preferences") or {}
        current_prefs.update(briefing_context)
        client.table("user_settings").update({"preferences": current_prefs}).eq(
            "user_id", uid
        ).execute()
        logger.info("  Updated user_settings with briefing context")
    else:
        # Insert new user_settings row
        client.table("user_settings").insert(
            {
                "user_id": uid,
                "preferences": briefing_context,
            }
        ).execute()
        logger.info("  Inserted user_settings with briefing context")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def print_summary(
    battle_cards: int,
    leads: int,
    stakeholders: int,
    drafts: int,
    signals: int,
    goals: int,
    actions: int,
    meetings: int,
) -> None:
    """Print a formatted summary of seeded data."""
    print()
    print("\u2554" + "\u2550" * 42 + "\u2557")
    print("\u2551       ARIA Demo Data Seeded              \u2551")
    print("\u2560" + "\u2550" * 42 + "\u2563")
    print(f"\u2551 Battle Cards:     {battle_cards:<23}\u2551")
    print(f"\u2551 Leads:           {leads:<23}\u2551")
    print(f"\u2551 Stakeholders:    {stakeholders:<23}\u2551")
    print(f"\u2551 Email Drafts:     {drafts:<23}\u2551")
    print(f"\u2551 Market Signals:   {signals:<23}\u2551")
    print(f"\u2551 Goals:            {goals} (with 6 agents)      \u2551")
    print(f"\u2551 Action Queue:     {actions:<23}\u2551")
    print(f"\u2551 Meetings:         {meetings:<23}\u2551")
    print(f"\u2551 Tavus Briefing:   {'1':<23}\u2551")
    print("\u2560" + "\u2550" * 42 + "\u2563")
    print("\u2551 Run again to refresh. Use --clean to     \u2551")
    print("\u2551 remove demo data without re-seeding.     \u2551")
    print("\u255a" + "\u2550" * 42 + "\u255d")
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Seed ARIA demo data for investor demonstrations")
    parser.add_argument(
        "--user-id",
        type=str,
        required=True,
        help="User ID to seed data for (UUID)",
    )
    parser.add_argument(
        "--company-id",
        type=str,
        required=False,
        default=None,
        help="Company ID (UUID). If omitted, looked up from user_profiles.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Only clean demo data (no seeding)",
    )

    args = parser.parse_args()

    # Validate UUIDs
    user_id = validate_uuid(args.user_id)

    company_id = str(validate_uuid(args.company_id)) if args.company_id else None

    # Get client
    client = get_supabase_client()

    # Resolve company_id if not provided
    if not company_id:
        company_id = resolve_company_id(client, user_id)

    uid = str(user_id)
    cid = str(company_id)

    # Always clean first (idempotent)
    clean_demo_data(client, uid, cid)

    if args.clean:
        logger.info("Clean-only mode. Done.")
        return

    # Seed in dependency order
    battle_card_count = seed_battle_cards(client, cid)
    lead_map = seed_leads(client, uid)
    stakeholder_count = seed_stakeholders(client, lead_map)
    draft_count = seed_email_drafts(client, uid, lead_map)
    signal_count = seed_market_signals(client, uid)
    goal_count = seed_goals(client, uid)
    action_count = seed_action_queue(client, uid)
    meeting_count = seed_meetings(client, uid)
    seed_tavus_briefing(client, uid)

    print_summary(
        battle_cards=battle_card_count,
        leads=len(lead_map),
        stakeholders=stakeholder_count,
        drafts=draft_count,
        signals=signal_count,
        goals=goal_count,
        actions=action_count,
        meetings=meeting_count,
    )

    logger.info("Demo data seeding complete.")


if __name__ == "__main__":
    main()
