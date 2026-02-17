"""Tavus CVI tool definitions for ARIA's video persona.

Defines OpenAI function-calling schemas for 12 tools that ARIA can invoke
during live video conversations via Tavus CVI. When the LLM triggers a
tool call, Tavus sends a ``conversation.tool_call`` event through Daily's
WebRTC data channel. The frontend listens for this event, calls
``POST /video/tools/execute`` on the backend, and echoes the result back
to the conversation via ``conversation.echo``.

Each tool maps to an existing ARIA agent or service:
- Hunter: search_companies, search_leads, add_lead_to_pipeline
- Analyst: search_pubmed, search_clinical_trials
- Scribe: draft_email
- Operator: schedule_meeting
- Scout: get_market_signals
- Services: get_lead_details, get_battle_card, get_pipeline_summary, get_meeting_brief
"""

from typing import Any

# ---------------------------------------------------------------------------
# Tool schema helpers
# ---------------------------------------------------------------------------

def _tool(
    name: str,
    description: str,
    properties: dict[str, Any],
    required: list[str],
) -> dict[str, Any]:
    """Build an OpenAI function-calling tool schema."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


# ---------------------------------------------------------------------------
# 12 ARIA Video Tools
# ---------------------------------------------------------------------------

ARIA_VIDEO_TOOLS: list[dict[str, Any]] = [
    # ── 1. search_companies (Hunter) ──────────────────────────────────
    _tool(
        name="search_companies",
        description=(
            "Search for companies matching specific criteria. Use this when the "
            "user asks to find companies, biotechs, CDMOs, or any organisations "
            "in a particular industry, funding stage, or geography. Returns a "
            "ranked list of matching companies with key details."
        ),
        properties={
            "query": {
                "type": "string",
                "description": (
                    "Natural language search query, e.g. 'Series B cell therapy "
                    "biotechs in the US'"
                ),
            },
            "industry": {
                "type": "string",
                "description": (
                    "Industry filter: biotech, pharma, CDMO, medtech, diagnostics"
                ),
            },
            "funding_stage": {
                "type": "string",
                "description": (
                    "Funding stage filter: seed, series_a, series_b, series_c, "
                    "growth, public"
                ),
            },
            "location": {
                "type": "string",
                "description": "Geographic filter, e.g. 'Boston' or 'Europe'",
            },
        },
        required=["query"],
    ),

    # ── 2. search_leads (Hunter) ──────────────────────────────────────
    _tool(
        name="search_leads",
        description=(
            "Discover new leads matching the user's Ideal Customer Profile. "
            "Use when the user asks to find prospects, leads, or potential "
            "customers. Searches based on ICP criteria and returns qualified "
            "leads with fit scores."
        ),
        properties={
            "icp_criteria": {
                "type": "string",
                "description": (
                    "Description of the ideal customer, e.g. 'VP-level "
                    "decision-makers at mid-size CDMOs focused on mAb "
                    "manufacturing'"
                ),
            },
        },
        required=["icp_criteria"],
    ),

    # ── 3. get_lead_details (Lead Memory) ─────────────────────────────
    _tool(
        name="get_lead_details",
        description=(
            "Look up details about a specific lead or company already in the "
            "user's pipeline. Use when the user mentions a company or contact "
            "by name and wants to know their status, health score, recent "
            "activity, or background."
        ),
        properties={
            "company_name": {
                "type": "string",
                "description": "Company name to look up, e.g. 'Lonza' or 'Catalent'",
            },
        },
        required=["company_name"],
    ),

    # ── 4. get_battle_card (BattleCardService) ────────────────────────
    _tool(
        name="get_battle_card",
        description=(
            "Retrieve competitive intelligence for a specific competitor. "
            "Use when the user asks about a competitor's strengths, weaknesses, "
            "pricing strategy, win/loss patterns, or objection handling. "
            "Returns the full battle card with positioning guidance."
        ),
        properties={
            "competitor_name": {
                "type": "string",
                "description": "Name of the competitor, e.g. 'Catalent' or 'Samsung Biologics'",
            },
        },
        required=["competitor_name"],
    ),

    # ── 5. search_pubmed (Analyst) ────────────────────────────────────
    _tool(
        name="search_pubmed",
        description=(
            "Search PubMed for scientific publications. Use when the user "
            "asks about research, clinical evidence, scientific publications, "
            "or needs to cite specific studies. Returns article titles, "
            "authors, and key findings."
        ),
        properties={
            "query": {
                "type": "string",
                "description": (
                    "PubMed search query, e.g. 'CAR-T cell therapy solid tumors "
                    "2024'"
                ),
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default 5, max 10)",
            },
        },
        required=["query"],
    ),

    # ── 6. search_clinical_trials (Analyst) ───────────────────────────
    _tool(
        name="search_clinical_trials",
        description=(
            "Search ClinicalTrials.gov for active or completed trials. Use "
            "when the user asks about clinical trials, drug development "
            "pipelines, or specific therapeutic areas. Returns trial titles, "
            "phases, sponsors, and status."
        ),
        properties={
            "condition": {
                "type": "string",
                "description": "Disease or condition, e.g. 'non-small cell lung cancer'",
            },
            "intervention": {
                "type": "string",
                "description": "Drug or therapy, e.g. 'pembrolizumab' or 'CAR-T'",
            },
            "sponsor": {
                "type": "string",
                "description": "Sponsor or company, e.g. 'Novartis'",
            },
        },
        required=["condition"],
    ),

    # ── 7. get_pipeline_summary (Lead Memory) ─────────────────────────
    _tool(
        name="get_pipeline_summary",
        description=(
            "Get a summary of the user's current lead pipeline. Use when the "
            "user asks about their pipeline status, how many leads they have, "
            "conversion rates, or overall pipeline health. Returns counts by "
            "stage and key metrics."
        ),
        properties={},
        required=[],
    ),

    # ── 8. get_meeting_brief (MeetingBriefService) ────────────────────
    _tool(
        name="get_meeting_brief",
        description=(
            "Get the pre-meeting research brief for an upcoming meeting. "
            "Use when the user asks about their next meeting, who they're "
            "meeting with, or wants a quick prep summary. Returns attendee "
            "profiles, company signals, and talking points."
        ),
        properties={
            "meeting_id": {
                "type": "string",
                "description": (
                    "Calendar event ID. If not provided, returns the brief "
                    "for the next upcoming meeting."
                ),
            },
        },
        required=[],
    ),

    # ── 9. draft_email (Scribe) ───────────────────────────────────────
    _tool(
        name="draft_email",
        description=(
            "Draft an email to a specific recipient. Use when the user asks "
            "to write, draft, or compose an email. Generates a personalised "
            "email with appropriate tone and context. The draft is saved for "
            "the user to review before sending."
        ),
        properties={
            "to": {
                "type": "string",
                "description": "Recipient name or email address",
            },
            "subject_context": {
                "type": "string",
                "description": (
                    "What the email is about, e.g. 'follow up on bioreactor "
                    "demo from last week'"
                ),
            },
            "tone": {
                "type": "string",
                "description": "Email tone: formal, friendly, or urgent",
            },
        },
        required=["to", "subject_context"],
    ),

    # ── 10. schedule_meeting (Operator) ───────────────────────────────
    _tool(
        name="schedule_meeting",
        description=(
            "Schedule a meeting on the user's calendar. Use when the user "
            "asks to book, schedule, or set up a meeting with someone. "
            "Creates the calendar event and sends invitations."
        ),
        properties={
            "attendees": {
                "type": "string",
                "description": (
                    "Comma-separated attendee names or emails, e.g. "
                    "'john@lonza.com, sarah@catalent.com'"
                ),
            },
            "time_range": {
                "type": "string",
                "description": (
                    "Preferred time, e.g. 'tomorrow afternoon', "
                    "'next Tuesday at 2pm', 'this week'"
                ),
            },
            "purpose": {
                "type": "string",
                "description": "Meeting purpose or agenda",
            },
        },
        required=["attendees", "time_range", "purpose"],
    ),

    # ── 11. get_market_signals (Scout) ────────────────────────────────
    _tool(
        name="get_market_signals",
        description=(
            "Get recent market signals and intelligence. Use when the user "
            "asks about industry news, competitor moves, funding rounds, "
            "regulatory changes, or any market developments. Returns "
            "classified signals with relevance scores."
        ),
        properties={
            "topic": {
                "type": "string",
                "description": (
                    "Topic or entity to monitor, e.g. 'cell therapy CDMOs' "
                    "or 'Lonza acquisitions'"
                ),
            },
        },
        required=["topic"],
    ),

    # ── 12. add_lead_to_pipeline (Lead Memory) ────────────────────────
    _tool(
        name="add_lead_to_pipeline",
        description=(
            "Add a new lead to the user's pipeline from the conversation. "
            "Use when the user says to track a company, add them to the "
            "pipeline, or wants to follow up on a company discovered during "
            "the conversation."
        ),
        properties={
            "company_name": {
                "type": "string",
                "description": "Company name to add",
            },
            "contact_name": {
                "type": "string",
                "description": "Primary contact name if known",
            },
            "notes": {
                "type": "string",
                "description": (
                    "Context or notes about why this lead is being added, "
                    "e.g. 'Discussed during briefing, expanding mAb capacity'"
                ),
            },
        },
        required=["company_name"],
    ),
]

# Tool name → agent mapping for routing
TOOL_AGENT_MAP: dict[str, str] = {
    "search_companies": "hunter",
    "search_leads": "hunter",
    "get_lead_details": "service",
    "get_battle_card": "service",
    "search_pubmed": "analyst",
    "search_clinical_trials": "analyst",
    "get_pipeline_summary": "service",
    "get_meeting_brief": "service",
    "draft_email": "scribe",
    "schedule_meeting": "operator",
    "get_market_signals": "scout",
    "add_lead_to_pipeline": "service",
}

VALID_TOOL_NAMES: frozenset[str] = frozenset(TOOL_AGENT_MAP.keys())
