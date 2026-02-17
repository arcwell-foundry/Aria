#!/usr/bin/env python
"""Setup and manage ARIA's Tavus Knowledge Base for 30ms RAG retrieval.

Uploads reference materials across four categories so ARIA can answer
factual questions during video conversations with near-instant retrieval:

  1. Company knowledge  (tag: aria-context)
  2. Life sciences ref  (tag: life-sciences)
  3. Competitive intel   (tag: competitive)
  4. Industry news crawl (tag: signals)

Idempotent: checks existing documents by name before re-uploading.

Usage:
    python scripts/setup_tavus_knowledge_base.py                # Upload all
    python scripts/setup_tavus_knowledge_base.py --category competitive  # One category
    python scripts/setup_tavus_knowledge_base.py --refresh-competitive   # Re-gen from DB
    python scripts/setup_tavus_knowledge_base.py --dry-run               # Preview only
"""

import argparse
import asyncio
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any

# Add backend to path for imports
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────
# Static content: Company Knowledge
# ────────────────────────────────────────────────────────────────

ARIA_CAPABILITIES_DOC = """\
# ARIA — Autonomous Reasoning & Intelligence Agent

## What ARIA Is
ARIA is an AI-powered Department Director for Life Sciences commercial teams.
She operates as an autonomous colleague — not a chatbot, not a tool — who
proactively manages pipeline, intelligence, communications, and strategy.

## Key Capabilities
- **Pipeline Management**: Tracks leads across lifecycle stages with health
  scoring, automated outreach timing, and risk-based action routing.
- **Competitive Intelligence**: Maintains battle cards on ~40 competitors,
  monitors market signals, and surfaces win/loss strategy in real time.
- **Scientific Research**: Searches PubMed, ClinicalTrials.gov, ChEMBL, and
  FDA databases for relevant data during conversations.
- **Email Drafting**: Writes emails matching each user's personal style via
  learned writing fingerprints, with per-recipient tone adaptation.
- **Meeting Preparation**: Generates meeting briefs with attendee intel,
  talking points, and competitive context before every meeting.
- **Calendar & CRM Sync**: Integrates with Google Calendar, Outlook,
  Salesforce, and HubSpot via Composio OAuth.
- **Goal Execution**: Users set high-level goals; ARIA breaks them into
  milestones and autonomously executes via six specialized agents.
- **Daily Briefings**: Morning briefing with priority actions, hot leads,
  upcoming meetings, and market signals.

## The Six Agents
1. **Hunter** — Prospect discovery, lead qualification, company research
2. **Analyst** — Scientific research, clinical trial analysis, publication review
3. **Strategist** — Competitive positioning, win/loss strategy, market analysis
4. **Scribe** — Email drafting, document creation, communication management
5. **Operator** — Calendar management, CRM updates, workflow automation
6. **Scout** — Market signal detection, news monitoring, trend analysis

## How ARIA Works
ARIA uses an OODA (Observe-Orient-Decide-Act) loop that runs every 30
minutes for active goals. She observes changes in pipeline, signals, and
context, then decides on actions. Low-risk actions execute automatically.
Medium-risk actions auto-approve after 30 minutes. High and critical risk
actions always require explicit user approval.

## Video Conversations
ARIA appears as a lifelike avatar powered by Tavus Phoenix-4 and Daily.co
WebRTC. During video, she can execute any of her 12 tools (search companies,
get battle cards, draft emails, etc.) while maintaining natural conversation.
She detects user emotion and engagement via Raven-1 perception.
"""

LUMINONE_PRODUCT_DOC = """\
# LuminOne by Arcwell Foundry LLC

## Product Overview
LuminOne is an enterprise AI platform for Life Sciences commercial teams.
The flagship product is ARIA (Autonomous Reasoning & Intelligence Agent),
an AI Department Director that transforms how biotech, pharma, and CDMO/CRO
sales teams operate.

## Pricing
- **ARIA Professional**: $1,500/month per seat
  - Full AI Director capabilities
  - 6 specialized agents
  - Pipeline and lead management
  - Competitive intelligence
  - Email drafting with style learning
  - Meeting preparation
  - Daily briefings
  - Standard integrations (CRM, Calendar, Email)

- **ARIA Enterprise**: $2,000/month per seat
  - Everything in Professional
  - Custom agent creation
  - Advanced analytics and ROI tracking
  - Priority support
  - Custom integration development
  - Dedicated success manager

## Target Market
- Biotech commercial teams (5-50 reps)
- Pharma sales organizations
- CDMO/CRO business development teams
- Life sciences consulting firms

## Value Proposition
"Solve the 72% admin trap — a 5-person team with ARIA performs like 7."
ARIA eliminates administrative overhead so commercial teams can focus on
what matters: building relationships and closing deals.

## Company
- **Legal Entity**: Arcwell Foundry LLC
- **DBA**: LuminOne
- **Founded**: 2025
- **Headquarters**: United States
- **Focus**: Enterprise AI for Life Sciences
"""

ARIA_FAQ_DOC = """\
# ARIA Frequently Asked Questions

## General
**Q: What is ARIA?**
A: ARIA is an AI Department Director for Life Sciences commercial teams.
She's not a chatbot — she's an autonomous colleague who proactively manages
your pipeline, intelligence, and communications.

**Q: How is ARIA different from ChatGPT or other AI assistants?**
A: ARIA is purpose-built for Life Sciences sales. She has persistent memory
across all interactions, understands your pipeline and relationships, and
can autonomously execute tasks like drafting emails, researching competitors,
and preparing meeting briefs. She also appears as a video avatar.

**Q: Does ARIA replace my team members?**
A: No. ARIA augments your team. She handles the 72% of time spent on admin
tasks, freeing your team to focus on relationship building and closing deals.

## Data & Security
**Q: Is my data secure?**
A: Yes. All data is encrypted at rest and in transit. Row-level security
ensures users only see their own company's data. We use Supabase with
PostgreSQL for enterprise-grade security.

**Q: Does ARIA share data between companies?**
A: Never. Each company's data is completely isolated via row-level security
policies. ARIA's memory is company-scoped.

**Q: Can ARIA access my email?**
A: Only with your explicit OAuth authorization via Composio. ARIA reads
emails to learn your writing style and detect urgent items, but never
stores raw email content — only processed insights.

## Capabilities
**Q: What CRMs does ARIA integrate with?**
A: Salesforce and HubSpot, with more coming. Integration happens via OAuth
through Composio.

**Q: Can ARIA make phone calls?**
A: Not yet. ARIA communicates via text chat, voice (speech-to-text), and
video avatar. Phone integration is on the 2027 roadmap.

**Q: How does ARIA learn my writing style?**
A: ARIA analyzes your sent emails to build a writing fingerprint capturing
your sentence structure, vocabulary, tone, and formatting preferences. She
also tracks per-recipient adaptations.

**Q: What scientific databases does ARIA search?**
A: PubMed, ClinicalTrials.gov, ChEMBL (drug discovery), and FDA drug
approval databases.

## Technical
**Q: What AI model does ARIA use?**
A: ARIA uses Anthropic's Claude (claude-sonnet-4-20250514) for reasoning
and generation. The video avatar uses Tavus Phoenix-4 with emotion
detection via Raven-1.

**Q: Does ARIA work offline?**
A: No. ARIA requires an internet connection to access AI models, databases,
and integrations.

**Q: What browsers are supported?**
A: Chrome, Firefox, Safari, and Edge (latest versions). Video conversations
require WebRTC support.
"""

# ────────────────────────────────────────────────────────────────
# Static content: Life Sciences Reference
# ────────────────────────────────────────────────────────────────

DRUG_MODALITIES_DOC = """\
# Drug Modalities Overview for Life Sciences Sales

## Monoclonal Antibodies (mAbs)
- **What**: Engineered proteins that bind specific targets (antigens)
- **Manufacturing**: Produced in mammalian cell lines (CHO cells most common)
- **Market**: Largest biologic category (~$200B+ global market)
- **Key Players**: Roche, AbbVie, J&J, Merck, Bristol-Myers Squibb
- **Sales Context**: High manufacturing complexity = long CDMO relationships.
  Biosimilar competition drives pricing pressure. Focus on process development
  and analytical characterization as selling points.

## Cell Therapy
- **What**: Living cells (usually T-cells) engineered to treat disease
- **Types**: CAR-T (chimeric antigen receptor T-cell), TIL (tumor-infiltrating
  lymphocyte), TCR-T (T-cell receptor), NK cell therapy
- **Manufacturing**: Autologous (patient's own cells) or allogeneic (donor cells)
- **Key Players**: Novartis (Kymriah), Gilead/Kite (Yescarta), BMS (Abecma/Breyanzi)
- **Sales Context**: Manufacturing is patient-specific and complex. Vein-to-vein
  time is critical. CDMOs need specialized facilities. Allogeneic is the growth area.

## Gene Therapy
- **What**: Delivering genetic material to treat or prevent disease
- **Vectors**: AAV (adeno-associated virus) most common, lentivirus for ex vivo
- **Manufacturing**: Viral vector production is the bottleneck
- **Key Players**: Novartis (Zolgensma), BioMarin (Roctavian), Spark/Roche
- **Sales Context**: Very high price points ($1M-$3.5M per treatment). Manufacturing
  scale-up is the biggest challenge. AAV vector manufacturing capacity is scarce.
  Analytical testing is complex and expensive.

## Antibody-Drug Conjugates (ADCs)
- **What**: Antibodies linked to cytotoxic drugs via chemical linkers
- **Components**: Antibody + Linker + Payload (warhead)
- **Manufacturing**: Requires expertise in both biologics AND small molecule chemistry
- **Key Players**: Daiichi Sankyo (Enhertu), Pfizer/Seagen, AbbVie, Gilead
- **Sales Context**: Fastest-growing oncology segment. Conjugation chemistry is
  specialized. Payload toxicity requires dedicated facilities. Growing pipeline
  means growing CDMO demand.

## mRNA Therapeutics
- **What**: Messenger RNA that instructs cells to produce therapeutic proteins
- **Manufacturing**: In vitro transcription (IVT) + lipid nanoparticle (LNP) formulation
- **Key Players**: Moderna, BioNTech, CureVac
- **Sales Context**: COVID vaccines proved the platform. Now expanding to oncology,
  rare disease, infectious disease. Manufacturing is relatively fast and scalable.
  LNP formulation is a differentiator.

## Small Molecules
- **What**: Traditional chemical drugs (<900 daltons)
- **Manufacturing**: Chemical synthesis, often multi-step processes
- **Market**: Still largest pharma segment by volume
- **Sales Context**: Well-established CDMO landscape. Differentiation through
  process chemistry expertise, continuous manufacturing, and speed to market.
  Generic competition after patent expiry.
"""

REGULATORY_OVERVIEW_DOC = """\
# Regulatory Pathway Overview

## FDA (United States)
- **IND (Investigational New Drug)**: Required before clinical trials. 30-day
  review period. Includes CMC (Chemistry, Manufacturing, Controls), preclinical
  data, and clinical protocol.
- **Phase 1**: Safety and dosing (20-100 healthy volunteers, 6-12 months)
- **Phase 2**: Efficacy and side effects (100-300 patients, 1-2 years)
- **Phase 3**: Confirm efficacy, monitor adverse reactions (1,000-3,000 patients, 1-4 years)
- **NDA/BLA**: New Drug Application (small molecules) or Biologics License
  Application (biologics). 10-month standard review, 6-month priority review.
- **Accelerated Pathways**:
  - Fast Track: Serious condition + unmet need. Rolling review.
  - Breakthrough Therapy: Substantial improvement over existing. Intensive FDA guidance.
  - Accelerated Approval: Surrogate endpoint. Post-marketing confirmatory trial required.
  - Priority Review: 6 months vs 10 months. Significant improvement in safety/efficacy.
- **REMS**: Risk Evaluation and Mitigation Strategy for drugs with serious safety concerns.

## EMA (European Union)
- **Centralized Procedure**: Single application for all EU member states via EMA.
  Required for biotech products, orphan drugs, and certain therapeutic areas.
- **Scientific Advice**: EMA provides development guidance (equivalent to FDA Type B meetings)
- **PRIME**: Priority Medicines scheme (similar to FDA Breakthrough)
- **Conditional Marketing Authorization**: EU equivalent of Accelerated Approval
- **Review Timeline**: 210 days (standard), clock stops for sponsor responses

## Key Differences FDA vs EMA
- FDA approves; EMA recommends (European Commission grants authorization)
- FDA uses Advisory Committees more frequently
- EMA requires pediatric investigation plan (PIP) for all new drugs
- Biosimilar pathways differ: FDA requires interchangeability studies; EMA does not

## Sales Context
Understanding regulatory pathways helps ARIA users:
- Anticipate client timelines and needs
- Position CDMO/CRO services at the right development stage
- Identify companies entering new regulatory phases (sales opportunities)
- Discuss regulatory strategy intelligently in client meetings
"""

CDMO_CRO_OVERVIEW_DOC = """\
# CDMO/CRO Industry Overview

## What is a CDMO?
Contract Development and Manufacturing Organization. CDMOs provide
outsourced drug development and manufacturing services to pharma/biotech.

### Top CDMOs (by revenue)
1. **Lonza** — Leader in biologics, cell & gene therapy. Basel, Switzerland.
2. **Samsung Biologics** — Largest single-site biologics capacity. Incheon, South Korea.
3. **Catalent** — Broad capabilities across modalities. Somerset, NJ.
4. **WuXi Biologics** — Largest biologics CDMO in China. Growing Western presence.
5. **Thermo Fisher Scientific** — Pharma services via Patheon brand.
6. **Fujifilm Diosynth** — Growing in gene therapy and biologics. US, UK, Denmark.
7. **AGC Biologics** — Mid-tier, strong in mAbs and gene therapy.
8. **Cytiva** (Danaher) — Equipment/consumables + some CDMO services.
9. **Rentschler Biopharma** — German CDMO strong in clinical manufacturing.
10. **National Resilience** — US-focused, advanced manufacturing tech.

### CDMO Market Trends
- Market size: ~$200B (2025), growing 7-8% CAGR
- Biologics outsourcing growing faster than small molecule
- Cell & gene therapy driving premium pricing
- Capacity constraints in viral vector and cell therapy manufacturing
- Reshoring/nearshoring trend post-COVID

## What is a CRO?
Contract Research Organization. CROs provide outsourced clinical trial
management and research services.

### Top CROs (by revenue)
1. **IQVIA** — Largest CRO globally. Technology + data + clinical ops.
2. **Labcorp Drug Development** — Full-service, strong in central lab.
3. **PPD** (Thermo Fisher) — Acquired by Thermo Fisher 2021.
4. **Syneos Health** — Clinical + commercial. Now part of Elliott consortium.
5. **Parexel** — Strong in regulatory consulting and late-phase.
6. **ICON** — Growing through acquisitions (PRA Health Sciences).
7. **Medpace** — Mid-tier, strong in oncology and rare disease.

### CRO Market Trends
- Market size: ~$80B (2025), growing 6-7% CAGR
- Decentralized clinical trials accelerating
- AI/ML integration in trial design and patient recruitment
- Real-world evidence (RWE) growing as complement to traditional trials
- Biotech clients (vs pharma) are fastest-growing segment

## Sales Context for ARIA Users
- CDMOs are both customers AND competitors depending on context
- Understanding capacity constraints helps identify opportunities
- Regulatory changes create service demand shifts
- M&A activity reshuffles competitive landscape frequently
"""

BIOTECH_FUNDING_DOC = """\
# Biotech Funding Stages

## Pre-Seed / Seed
- **Typical Amount**: $500K - $5M
- **Source**: Angel investors, friends & family, seed VCs
- **Stage**: Idea/concept, early research, IP filing
- **What They Need**: Nothing from CDMOs/CROs yet. May need scientific advisory.
- **Sales Signal**: Not a sales target. Monitor for future potential.

## Series A
- **Typical Amount**: $10M - $50M
- **Source**: Biotech-focused VCs (ARCH, Flagship, OrbiMed, RA Capital)
- **Stage**: Lead candidate identified, IND-enabling studies
- **What They Need**: Preclinical CRO services, early process development
- **Sales Signal**: Entering CDMO conversations. Early engagement opportunity.

## Series B
- **Typical Amount**: $30M - $150M
- **Source**: Growth VCs, crossover investors
- **Stage**: Phase 1/2 clinical trials, scaling manufacturing
- **What They Need**: Clinical CRO, CDMO for clinical supply
- **Sales Signal**: Active CDMO procurement. Key sales target.

## Series C+
- **Typical Amount**: $100M - $500M+
- **Source**: Late-stage VCs, crossover funds, sovereign wealth
- **Stage**: Phase 2/3 trials, preparing for commercialization
- **What They Need**: Commercial-scale CDMO, regulatory consulting, Phase 3 CRO
- **Sales Signal**: Large CDMO contracts. Strategic partnerships forming.

## IPO / Public
- **Typical Amount**: $100M - $1B+
- **Stage**: Late clinical or commercial
- **What They Need**: Commercial manufacturing, global regulatory, sales operations
- **Sales Signal**: Largest contracts. Multi-year CDMO agreements.

## Key Biotech VC Firms (for lead identification)
- ARCH Venture Partners
- Flagship Pioneering (created Moderna)
- OrbiMed Advisors
- RA Capital Management
- Sofinnova Partners
- Venrock Healthcare
- Atlas Venture
- Polaris Partners
- 5AM Ventures
- Abingworth

## Funding Round Indicators
Watch for:
- SEC filings (Form D for private, S-1 for IPO)
- Press releases on funding rounds
- ClinicalTrials.gov new trial registrations (indicates funding)
- Patent filings (indicates active R&D investment)
- Leadership hires (CMO, VP Manufacturing = scaling signal)
"""

# ────────────────────────────────────────────────────────────────
# Existing docs to upload from repo
# ────────────────────────────────────────────────────────────────

REPO_DOCS_TO_UPLOAD = [
    {
        "path": "docs/ARIA_PRD.md",
        "name": "ARIA Product Requirements Document",
        "tags": ["aria-context"],
    },
]

# ────────────────────────────────────────────────────────────────
# News crawl sources
# ────────────────────────────────────────────────────────────────

NEWS_CRAWL_SOURCES = [
    {
        "name": "BioPharma Dive - Industry News",
        "url": "https://www.biopharmadive.com",
        "tags": ["signals"],
        "max_depth": 2,
        "max_pages": 20,
    },
    {
        "name": "Fierce Pharma - Industry News",
        "url": "https://www.fiercepharma.com",
        "tags": ["signals"],
        "max_depth": 2,
        "max_pages": 20,
    },
]


class KnowledgeBaseManager:
    """Manages Tavus Knowledge Base documents with idempotency."""

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self._existing_docs: dict[str, dict[str, Any]] | None = None

    async def _get_client(self) -> Any:
        """Lazy-import and return TavusClient."""
        from src.integrations.tavus import TavusClient

        return TavusClient()

    async def _get_existing_docs(self, client: Any) -> dict[str, dict[str, Any]]:
        """Fetch and cache existing documents by name."""
        if self._existing_docs is None:
            try:
                docs = await client.list_documents()
                self._existing_docs = {
                    d.get("document_name", ""): d for d in docs
                }
                logger.info(
                    "Found %d existing knowledge base documents",
                    len(self._existing_docs),
                )
            except Exception:
                logger.warning("Could not list existing documents, assuming empty")
                self._existing_docs = {}
        return self._existing_docs

    async def _upload_text_document(
        self,
        client: Any,
        name: str,
        content: str,
        tags: list[str],
    ) -> dict[str, Any] | None:
        """Upload a text document, skipping if it already exists.

        Writes content to a temp file, uploads it, then cleans up.

        Args:
            client: TavusClient instance
            name: Document name (used for idempotency check)
            content: Markdown text content
            tags: List of tags

        Returns:
            API response dict, or None if skipped/dry-run
        """
        existing = await self._get_existing_docs(client)
        if name in existing:
            logger.info("SKIP (exists): %s", name)
            return None

        if self.dry_run:
            logger.info("DRY-RUN would upload: %s [tags=%s] (%d chars)", name, tags, len(content))
            return None

        # Write to temp file and upload
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                suffix=".md",
                delete=False,
                prefix="tavus_kb_",
            ) as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            result = await client.create_document(
                document_name=name,
                file_url_or_path=tmp_path,
                tags=tags,
            )
            doc_id = result.get("document_id", "unknown")
            logger.info("UPLOADED: %s -> %s", name, doc_id)

            # Update cache
            existing[name] = result
            return result

        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    async def _upload_url_document(
        self,
        client: Any,
        name: str,
        url: str,
        tags: list[str],
        crawl: bool = False,
        max_depth: int | None = None,
        max_pages: int | None = None,
    ) -> dict[str, Any] | None:
        """Upload a URL-based document with optional crawling.

        Args:
            client: TavusClient instance
            name: Document name
            url: URL to the document or site to crawl
            tags: List of tags
            crawl: Whether to crawl linked pages
            max_depth: Max crawl depth
            max_pages: Max pages to crawl

        Returns:
            API response dict, or None if skipped/dry-run
        """
        existing = await self._get_existing_docs(client)
        if name in existing:
            logger.info("SKIP (exists): %s", name)
            return None

        if self.dry_run:
            logger.info(
                "DRY-RUN would crawl: %s [url=%s, depth=%s, pages=%s]",
                name,
                url,
                max_depth,
                max_pages,
            )
            return None

        result = await client.create_document(
            document_name=name,
            file_url_or_path=url,
            tags=tags,
            crawl=crawl,
            max_depth=max_depth,
            max_pages=max_pages,
        )
        doc_id = result.get("document_id", "unknown")
        logger.info("UPLOADED (URL): %s -> %s", name, doc_id)

        existing = await self._get_existing_docs(client)
        existing[name] = result
        return result

    async def _upload_file_document(
        self,
        client: Any,
        name: str,
        file_path: str,
        tags: list[str],
    ) -> dict[str, Any] | None:
        """Upload a local file document.

        Args:
            client: TavusClient instance
            name: Document name
            file_path: Path to the file
            tags: List of tags

        Returns:
            API response dict, or None if skipped/dry-run
        """
        existing = await self._get_existing_docs(client)
        if name in existing:
            logger.info("SKIP (exists): %s", name)
            return None

        if not os.path.exists(file_path):
            logger.warning("File not found, skipping: %s", file_path)
            return None

        if self.dry_run:
            logger.info("DRY-RUN would upload file: %s [path=%s]", name, file_path)
            return None

        result = await client.create_document(
            document_name=name,
            file_url_or_path=file_path,
            tags=tags,
        )
        doc_id = result.get("document_id", "unknown")
        logger.info("UPLOADED (file): %s -> %s", name, doc_id)

        existing = await self._get_existing_docs(client)
        existing[name] = result
        return result

    async def _delete_by_prefix(
        self,
        client: Any,
        prefix: str,
    ) -> int:
        """Delete all documents whose name starts with a prefix.

        Args:
            client: TavusClient instance
            prefix: Name prefix to match

        Returns:
            Number of documents deleted
        """
        existing = await self._get_existing_docs(client)
        to_delete = {
            name: doc
            for name, doc in existing.items()
            if name.startswith(prefix)
        }

        if not to_delete:
            return 0

        if self.dry_run:
            logger.info("DRY-RUN would delete %d docs with prefix '%s'", len(to_delete), prefix)
            return 0

        deleted = 0
        for name, doc in to_delete.items():
            doc_id = doc.get("document_id") or doc.get("id")
            if not doc_id:
                continue
            try:
                await client.delete_document(doc_id)
                logger.info("DELETED: %s (%s)", name, doc_id)
                del existing[name]
                deleted += 1
            except Exception:
                logger.warning("Failed to delete %s", name, exc_info=True)

        return deleted

    # ────────────────────────────────────────────────────────────
    # Category: Company Knowledge
    # ────────────────────────────────────────────────────────────

    async def upload_company_knowledge(self, client: Any) -> dict[str, int]:
        """Upload ARIA/LuminOne company knowledge documents.

        Returns:
            Stats dict with uploaded and skipped counts
        """
        logger.info("=== Category: Company Knowledge (aria-context) ===")
        tags = ["aria-context"]
        uploaded = 0
        skipped = 0

        # Static documents
        static_docs = [
            ("ARIA Capabilities Overview", ARIA_CAPABILITIES_DOC),
            ("LuminOne Product and Pricing", LUMINONE_PRODUCT_DOC),
            ("ARIA FAQ", ARIA_FAQ_DOC),
        ]

        for name, content in static_docs:
            result = await self._upload_text_document(client, name, content, tags)
            if result:
                uploaded += 1
            else:
                skipped += 1

        # Repo documents
        for doc_info in REPO_DOCS_TO_UPLOAD:
            file_path = str(backend_path.parent / doc_info["path"])
            result = await self._upload_file_document(
                client,
                doc_info["name"],
                file_path,
                doc_info["tags"],
            )
            if result:
                uploaded += 1
            else:
                skipped += 1

        return {"uploaded": uploaded, "skipped": skipped}

    # ────────────────────────────────────────────────────────────
    # Category: Life Sciences Reference
    # ────────────────────────────────────────────────────────────

    async def upload_life_sciences_reference(self, client: Any) -> dict[str, int]:
        """Upload life sciences reference documents.

        Returns:
            Stats dict with uploaded and skipped counts
        """
        logger.info("=== Category: Life Sciences Reference (life-sciences) ===")
        tags = ["life-sciences"]
        uploaded = 0
        skipped = 0

        ref_docs = [
            ("Drug Modalities Overview", DRUG_MODALITIES_DOC),
            ("Regulatory Pathway Overview (FDA and EMA)", REGULATORY_OVERVIEW_DOC),
            ("CDMO and CRO Industry Overview", CDMO_CRO_OVERVIEW_DOC),
            ("Biotech Funding Stages", BIOTECH_FUNDING_DOC),
        ]

        for name, content in ref_docs:
            result = await self._upload_text_document(client, name, content, tags)
            if result:
                uploaded += 1
            else:
                skipped += 1

        return {"uploaded": uploaded, "skipped": skipped}

    # ────────────────────────────────────────────────────────────
    # Category: Competitive Intelligence
    # ────────────────────────────────────────────────────────────

    async def upload_competitive_intelligence(
        self,
        client: Any,
        refresh: bool = False,
    ) -> dict[str, int]:
        """Generate and upload competitive intelligence from battle_cards table.

        Args:
            client: TavusClient instance
            refresh: If True, delete existing competitive docs and re-upload

        Returns:
            Stats dict with uploaded, skipped, and deleted counts
        """
        logger.info("=== Category: Competitive Intelligence (competitive) ===")
        from src.db.supabase import SupabaseClient

        db = SupabaseClient.get_client()
        tags = ["competitive"]
        prefix = "Battle Card: "
        uploaded = 0
        skipped = 0
        deleted = 0

        # Fetch all battle cards
        result = db.table("battle_cards").select("*").order("competitor_name").execute()
        cards = result.data or []

        if not cards:
            logger.warning("No battle cards found in database")
            return {"uploaded": 0, "skipped": 0, "deleted": 0}

        logger.info("Found %d battle cards in database", len(cards))

        # If refreshing, delete all existing competitive docs first
        if refresh:
            deleted = await self._delete_by_prefix(client, prefix)
            # Clear cache to force re-fetch
            self._existing_docs = None

        # Generate and upload a summary doc for each competitor
        for card in cards:
            name = f"{prefix}{card['competitor_name']}"
            content = self._format_battle_card(card)
            result_doc = await self._upload_text_document(client, name, content, tags)
            if result_doc:
                uploaded += 1
            else:
                skipped += 1

        return {"uploaded": uploaded, "skipped": skipped, "deleted": deleted}

    @staticmethod
    def _format_battle_card(card: dict[str, Any]) -> str:
        """Format a battle card row into a markdown document.

        Args:
            card: Battle card row from database

        Returns:
            Formatted markdown string
        """
        competitor = card.get("competitor_name", "Unknown")
        domain = card.get("competitor_domain", "")
        overview = card.get("overview", "No overview available.")
        strengths = card.get("strengths", [])
        weaknesses = card.get("weaknesses", [])
        pricing = card.get("pricing", {})
        differentiation = card.get("differentiation", [])
        objection_handlers = card.get("objection_handlers", [])

        lines = [
            f"# Competitive Battle Card: {competitor}",
            "",
        ]

        if domain:
            lines.append(f"**Domain**: {domain}")
            lines.append("")

        lines.append("## Overview")
        lines.append(overview)
        lines.append("")

        if strengths:
            lines.append("## Strengths")
            for s in strengths:
                if isinstance(s, dict):
                    lines.append(f"- **{s.get('area', '')}**: {s.get('detail', s)}")
                else:
                    lines.append(f"- {s}")
            lines.append("")

        if weaknesses:
            lines.append("## Weaknesses")
            for w in weaknesses:
                if isinstance(w, dict):
                    lines.append(f"- **{w.get('area', '')}**: {w.get('detail', w)}")
                else:
                    lines.append(f"- {w}")
            lines.append("")

        if pricing:
            lines.append("## Pricing Intelligence")
            if isinstance(pricing, dict):
                for k, v in pricing.items():
                    lines.append(f"- **{k}**: {v}")
            else:
                lines.append(f"- {pricing}")
            lines.append("")

        if differentiation:
            lines.append("## Key Differentiation")
            for d in differentiation:
                if isinstance(d, dict):
                    lines.append(f"- **{d.get('area', '')}**: {d.get('detail', d)}")
                else:
                    lines.append(f"- {d}")
            lines.append("")

        if objection_handlers:
            lines.append("## Objection Handlers")
            for oh in objection_handlers:
                if isinstance(oh, dict):
                    lines.append(f"**Objection**: {oh.get('objection', '')}")
                    lines.append(f"**Response**: {oh.get('response', '')}")
                    lines.append("")
                else:
                    lines.append(f"- {oh}")
            lines.append("")

        return "\n".join(lines)

    # ────────────────────────────────────────────────────────────
    # Category: Industry News Crawls
    # ────────────────────────────────────────────────────────────

    async def setup_industry_news_crawls(self, client: Any) -> dict[str, int]:
        """Set up industry news site crawls.

        Returns:
            Stats dict with uploaded and skipped counts
        """
        logger.info("=== Category: Industry News Crawls (signals) ===")
        uploaded = 0
        skipped = 0

        for source in NEWS_CRAWL_SOURCES:
            result = await self._upload_url_document(
                client,
                name=source["name"],
                url=source["url"],
                tags=source["tags"],
                crawl=True,
                max_depth=source.get("max_depth"),
                max_pages=source.get("max_pages"),
            )
            if result:
                uploaded += 1
            else:
                skipped += 1

        return {"uploaded": uploaded, "skipped": skipped}

    # ────────────────────────────────────────────────────────────
    # Main orchestration
    # ────────────────────────────────────────────────────────────

    async def setup_all(
        self,
        category: str | None = None,
        refresh_competitive: bool = False,
    ) -> dict[str, Any]:
        """Run full knowledge base setup.

        Args:
            category: Optional single category to run (company, life-sciences,
                      competitive, signals). None = all.
            refresh_competitive: If True, delete and re-upload competitive docs.

        Returns:
            Summary stats dict
        """
        client = await self._get_client()
        results: dict[str, Any] = {}

        categories = {
            "company": self.upload_company_knowledge,
            "life-sciences": self.upload_life_sciences_reference,
            "competitive": None,  # handled separately due to refresh param
            "signals": self.setup_industry_news_crawls,
        }

        targets = [category] if category else list(categories.keys())

        for cat in targets:
            if cat == "competitive":
                results[cat] = await self.upload_competitive_intelligence(
                    client,
                    refresh=refresh_competitive,
                )
            elif cat in categories and categories[cat] is not None:
                handler = categories[cat]
                assert handler is not None
                results[cat] = await handler(client)
            else:
                logger.warning("Unknown category: %s", cat)

        return results


async def refresh_competitive_docs() -> dict[str, Any]:
    """Refresh competitive intelligence docs from battle_cards.

    Called by the scheduler monthly. Deletes existing competitive docs
    and re-uploads from current battle card data.

    Returns:
        Stats dict from upload_competitive_intelligence
    """
    from src.integrations.tavus import TavusClient

    manager = KnowledgeBaseManager()
    client = TavusClient()
    return await manager.upload_competitive_intelligence(client, refresh=True)


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Setup ARIA Tavus Knowledge Base for video RAG retrieval",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
    python scripts/setup_tavus_knowledge_base.py                          # Upload all
    python scripts/setup_tavus_knowledge_base.py --category company       # Company docs only
    python scripts/setup_tavus_knowledge_base.py --category competitive   # Battle cards only
    python scripts/setup_tavus_knowledge_base.py --refresh-competitive    # Re-gen competitive
    python scripts/setup_tavus_knowledge_base.py --dry-run                # Preview only

Categories:
    company        ARIA capabilities, LuminOne product info, FAQ
    life-sciences  Drug modalities, regulatory, CDMO/CRO, biotech funding
    competitive    Battle card summaries (generated from database)
    signals        Industry news crawls (biopharmadive, fiercepharma)

Environment Variables Required:
    TAVUS_API_KEY       - Your Tavus API key
    SUPABASE_URL        - Supabase project URL (for competitive category)
    SUPABASE_SERVICE_ROLE_KEY - Supabase service role key
        """,
    )
    parser.add_argument(
        "--category",
        choices=["company", "life-sciences", "competitive", "signals"],
        help="Upload only a specific category",
    )
    parser.add_argument(
        "--refresh-competitive",
        action="store_true",
        help="Delete and re-upload competitive docs from battle_cards",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be uploaded without making API calls",
    )

    args = parser.parse_args()

    # Validate environment
    if not os.environ.get("TAVUS_API_KEY"):
        logger.error("TAVUS_API_KEY is required. Set it in your .env or environment.")
        return 1

    manager = KnowledgeBaseManager(dry_run=args.dry_run)

    refresh = args.refresh_competitive
    # If --refresh-competitive used without --category, target competitive
    category = args.category
    if refresh and not category:
        category = "competitive"

    results = asyncio.run(
        manager.setup_all(category=category, refresh_competitive=refresh)
    )

    # Print summary
    print("\n" + "=" * 60)
    print("ARIA Tavus Knowledge Base Setup Complete")
    print("=" * 60)

    total_uploaded = 0
    total_skipped = 0
    total_deleted = 0

    for cat, stats in results.items():
        up = stats.get("uploaded", 0)
        sk = stats.get("skipped", 0)
        dl = stats.get("deleted", 0)
        total_uploaded += up
        total_skipped += sk
        total_deleted += dl
        print(f"  {cat:20s}  uploaded={up}  skipped={sk}  deleted={dl}")

    print("-" * 60)
    print(
        f"  {'TOTAL':20s}  uploaded={total_uploaded}  "
        f"skipped={total_skipped}  deleted={total_deleted}"
    )

    if args.dry_run:
        print("\n  (DRY RUN — no documents were actually uploaded)")

    print("=" * 60 + "\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
