"""Web Intelligence capability for ScoutAgent and AnalystAgent.

Provides deep web scraping, competitor monitoring, SEC filing search,
patent tracking, and press release discovery — all from public sources
with no OAuth required. Extracted data flows into corporate_facts (for
the knowledge graph) and market_signals (for alerting).

Key responsibilities:
- Deep scrape URLs for structured content extraction
- Monitor competitor websites for changes
- Search SEC EDGAR for 10-K / 10-Q filings
- Search USPTO for patent filings by therapeutic area
- Scrape PR Newswire / GlobeNewswire for press releases

All operations are headless server-side; no browser UI.
"""

import hashlib
import json
import logging
import time
import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urljoin, urlparse

from src.agents.capabilities.base import BaseCapability, CapabilityResult
from src.db.supabase import SupabaseClient

logger = logging.getLogger(__name__)

# ── SEC EDGAR constants ──────────────────────────────────────────────────
SEC_EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
SEC_EDGAR_FULL_TEXT_URL = "https://efts.sec.gov/LATEST/search-index"
SEC_EDGAR_COMPANY_URL = "https://www.sec.gov/cgi-bin/browse-edgar"
SEC_EDGAR_SUBMISSIONS_URL = "https://data.sec.gov/submissions"

# ── USPTO constants ──────────────────────────────────────────────────────
USPTO_SEARCH_URL = "https://developer.uspto.gov/ibd-api/v1/application/publications"

# ── Press release source URLs ────────────────────────────────────────────
PR_NEWSWIRE_SEARCH_URL = "https://www.prnewswire.com/search/news/"
GLOBENEWSWIRE_SEARCH_URL = "https://www.globenewswire.com/search"

# ── User-Agent for public API requests ───────────────────────────────────
# SEC EDGAR requires a User-Agent with contact info per their fair use policy
DEFAULT_USER_AGENT = "ARIA-Intelligence/1.0 (support@aria-intel.com)"


# ── Lightweight domain dataclasses ───────────────────────────────────────


class StructuredContent:
    """Result of a deep scrape with extracted structured data."""

    def __init__(
        self,
        *,
        url: str,
        title: str = "",
        content: str = "",
        metadata: dict[str, Any] | None = None,
        structured_data: list[dict[str, Any]] | None = None,
        links: list[str] | None = None,
        scraped_at: datetime | None = None,
    ) -> None:
        self.url = url
        self.title = title
        self.content = content
        self.metadata = metadata or {}
        self.structured_data = structured_data or []
        self.links = links or []
        self.scraped_at = scraped_at or datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to JSON-friendly dict."""
        return {
            "url": self.url,
            "title": self.title,
            "content": self.content[:5000],  # Truncate for payload size
            "metadata": self.metadata,
            "structured_data": self.structured_data,
            "links": self.links[:50],
            "scraped_at": self.scraped_at.isoformat(),
        }


class Change:
    """A detected change on a competitor website."""

    def __init__(
        self,
        *,
        domain: str,
        page_url: str,
        change_type: str,
        summary: str,
        old_hash: str | None = None,
        new_hash: str | None = None,
        detected_at: datetime | None = None,
    ) -> None:
        self.domain = domain
        self.page_url = page_url
        self.change_type = change_type
        self.summary = summary
        self.old_hash = old_hash
        self.new_hash = new_hash
        self.detected_at = detected_at or datetime.now(UTC)

    def to_dict(self) -> dict[str, Any]:
        """Serialise to JSON-friendly dict."""
        return {
            "domain": self.domain,
            "page_url": self.page_url,
            "change_type": self.change_type,
            "summary": self.summary,
            "old_hash": self.old_hash,
            "new_hash": self.new_hash,
            "detected_at": self.detected_at.isoformat(),
        }


class Filing:
    """An SEC filing result."""

    def __init__(
        self,
        *,
        company: str,
        cik: str = "",
        filing_type: str = "",
        filed_date: str = "",
        period_of_report: str = "",
        description: str = "",
        filing_url: str = "",
        accession_number: str = "",
    ) -> None:
        self.company = company
        self.cik = cik
        self.filing_type = filing_type
        self.filed_date = filed_date
        self.period_of_report = period_of_report
        self.description = description
        self.filing_url = filing_url
        self.accession_number = accession_number

    def to_dict(self) -> dict[str, Any]:
        """Serialise to JSON-friendly dict."""
        return {
            "company": self.company,
            "cik": self.cik,
            "filing_type": self.filing_type,
            "filed_date": self.filed_date,
            "period_of_report": self.period_of_report,
            "description": self.description,
            "filing_url": self.filing_url,
            "accession_number": self.accession_number,
        }


class Patent:
    """A patent search result from USPTO."""

    def __init__(
        self,
        *,
        title: str = "",
        application_number: str = "",
        publication_number: str = "",
        applicant: str = "",
        filed_date: str = "",
        publication_date: str = "",
        abstract: str = "",
        patent_url: str = "",
    ) -> None:
        self.title = title
        self.application_number = application_number
        self.publication_number = publication_number
        self.applicant = applicant
        self.filed_date = filed_date
        self.publication_date = publication_date
        self.abstract = abstract
        self.patent_url = patent_url

    def to_dict(self) -> dict[str, Any]:
        """Serialise to JSON-friendly dict."""
        return {
            "title": self.title,
            "application_number": self.application_number,
            "publication_number": self.publication_number,
            "applicant": self.applicant,
            "filed_date": self.filed_date,
            "publication_date": self.publication_date,
            "abstract": self.abstract[:2000],
            "patent_url": self.patent_url,
        }


class PressRelease:
    """A press release search result."""

    def __init__(
        self,
        *,
        title: str = "",
        company: str = "",
        published_at: str = "",
        source: str = "",
        url: str = "",
        snippet: str = "",
    ) -> None:
        self.title = title
        self.company = company
        self.published_at = published_at
        self.source = source
        self.url = url
        self.snippet = snippet

    def to_dict(self) -> dict[str, Any]:
        """Serialise to JSON-friendly dict."""
        return {
            "title": self.title,
            "company": self.company,
            "published_at": self.published_at,
            "source": self.source,
            "url": self.url,
            "snippet": self.snippet[:1000],
        }


# ── Capability implementation ────────────────────────────────────────────


class WebIntelligenceCapability(BaseCapability):
    """Web intelligence: scraping, competitor monitoring, SEC/patent/PR search.

    Uses httpx for static pages and Playwright (headless) for JS-rendered
    content. All data sources are public — no OAuth scopes required.

    Designed for ScoutAgent (signal detection, competitive intel) and
    AnalystAgent (deep research, filing analysis).
    """

    capability_name: str = "web-intelligence"
    agent_types: list[str] = ["ScoutAgent", "AnalystAgent"]
    oauth_scopes: list[str] = []
    data_classes: list[str] = ["PUBLIC", "INTERNAL"]

    # ── BaseCapability abstract interface ──────────────────────────────────

    async def can_handle(self, task: dict[str, Any]) -> float:
        """Return confidence for web-intelligence tasks."""
        task_type = task.get("type", "")
        if task_type in {
            "deep_scrape",
            "monitor_competitor",
            "search_sec_filings",
            "search_patents",
            "search_press_releases",
        }:
            return 0.95
        if any(
            kw in task_type.lower()
            for kw in ("scrape", "competitor", "sec", "patent", "press_release", "web")
        ):
            return 0.6
        return 0.0

    async def execute(
        self,
        task: dict[str, Any],
        context: dict[str, Any],  # noqa: ARG002
    ) -> CapabilityResult:
        """Route to the correct method based on task type."""
        start = time.monotonic()
        user_id = self._user_context.user_id
        task_type = task.get("type", "")

        try:
            if task_type == "deep_scrape":
                url = task.get("url", "")
                result = await self.deep_scrape(url)
                data = result.to_dict()
                facts = self._extract_facts_from_content(result, user_id)

            elif task_type == "monitor_competitor":
                domain = task.get("domain", "")
                changes = await self.monitor_competitor(domain)
                data = {"domain": domain, "changes": [c.to_dict() for c in changes]}
                facts = self._extract_facts_from_changes(changes, user_id)

            elif task_type == "search_sec_filings":
                company = task.get("company", "")
                filings = await self.search_sec_filings(company)
                data = {"company": company, "filings": [f.to_dict() for f in filings]}
                facts = self._extract_facts_from_filings(filings, company, user_id)

            elif task_type == "search_patents":
                query = task.get("query", "")
                patents = await self.search_patents(query)
                data = {"query": query, "patents": [p.to_dict() for p in patents]}
                facts = self._extract_facts_from_patents(patents, user_id)

            elif task_type == "search_press_releases":
                company = task.get("company", "")
                releases = await self.search_press_releases(company)
                data = {"company": company, "press_releases": [pr.to_dict() for pr in releases]}
                facts = self._extract_facts_from_press_releases(releases, user_id)

            else:
                return CapabilityResult(
                    success=False,
                    error=f"Unknown task type: {task_type}",
                    execution_time_ms=int((time.monotonic() - start) * 1000),
                )

            elapsed_ms = int((time.monotonic() - start) * 1000)
            await self.log_activity(
                activity_type="web_intelligence",
                title=f"Web intelligence: {task_type}",
                description=f"Completed {task_type} for user {user_id}",
                confidence=0.80,
                metadata={"task_type": task_type},
            )
            return CapabilityResult(
                success=True,
                data=data,
                extracted_facts=facts,
                execution_time_ms=elapsed_ms,
            )

        except Exception as exc:
            elapsed_ms = int((time.monotonic() - start) * 1000)
            logger.exception("Web intelligence capability failed")
            return CapabilityResult(
                success=False,
                error=str(exc),
                execution_time_ms=elapsed_ms,
            )

    def get_data_classes_accessed(self) -> list[str]:
        """Declare data classification levels."""
        return ["public", "internal"]

    # ── Public methods ────────────────────────────────────────────────────

    async def deep_scrape(self, url: str) -> StructuredContent:
        """Scrape a URL and extract structured content.

        Attempts a static fetch with httpx first. If the page appears to
        require JavaScript rendering (minimal content returned), falls back
        to Playwright headless browser.

        Extracts: title, body text, meta tags, JSON-LD structured data,
        Open Graph metadata, and outbound links.

        Args:
            url: The URL to scrape.

        Returns:
            StructuredContent with extracted data.
        """
        import httpx

        parsed = urlparse(url)
        if not parsed.scheme:
            url = f"https://{url}"

        # ── Try static fetch first ────────────────────────────────────
        html = ""
        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                follow_redirects=True,
                headers={"User-Agent": DEFAULT_USER_AGENT},
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                html = resp.text
        except httpx.HTTPError as exc:
            logger.warning("Static fetch failed for %s: %s", url, exc)

        # ── Check if JS rendering is needed ───────────────────────────
        if not html or len(html.strip()) < 500:
            html = await self._fetch_with_playwright(url)

        # ── Parse HTML ────────────────────────────────────────────────
        return self._parse_html(url, html)

    async def monitor_competitor(self, domain: str) -> list[Change]:
        """Check a competitor website for changes since last snapshot.

        Fetches key pages (homepage, /about, /products, /news) and
        compares content hashes against stored snapshots in market_signals
        metadata. Creates a market_signal for each detected change.

        Args:
            domain: Competitor domain (e.g. ``"competitor.com"``).

        Returns:
            List of Change objects for detected differences.
        """
        import httpx

        changes: list[Change] = []
        client = SupabaseClient.get_client()
        user_id = self._user_context.user_id
        now = datetime.now(UTC)

        # Normalise domain
        if not domain.startswith("http"):
            base_url = f"https://{domain}"
        else:
            base_url = domain
            domain = urlparse(domain).netloc

        # Pages to monitor
        monitor_paths = ["/", "/about", "/products", "/news", "/press", "/pipeline"]

        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": DEFAULT_USER_AGENT},
        ) as http_client:
            for path in monitor_paths:
                page_url = urljoin(base_url, path)
                try:
                    resp = await http_client.get(page_url)
                    if resp.status_code >= 400:
                        continue
                    content = resp.text
                except httpx.HTTPError:
                    continue

                content_hash = hashlib.sha256(content.encode()).hexdigest()

                # Look up previous snapshot
                snapshot_resp = (
                    client.table("market_signals")
                    .select("id, metadata")
                    .eq("user_id", user_id)
                    .eq("company_name", domain)
                    .eq("signal_type", "competitor_page_snapshot")
                    .eq("source_url", page_url)
                    .order("detected_at", desc=True)
                    .limit(1)
                    .execute()
                )
                previous = snapshot_resp.data[0] if snapshot_resp.data else None
                old_hash = (
                    (previous.get("metadata") or {}).get("content_hash") if previous else None
                )

                if old_hash and old_hash != content_hash:
                    # Page changed — extract summary of what changed
                    summary = self._summarise_page_change(path, content)
                    change = Change(
                        domain=domain,
                        page_url=page_url,
                        change_type="content_changed",
                        summary=summary,
                        old_hash=old_hash,
                        new_hash=content_hash,
                        detected_at=now,
                    )
                    changes.append(change)

                    # Store as market signal
                    self._store_market_signal(
                        client=client,
                        user_id=user_id,
                        company_name=domain,
                        signal_type="competitor_page_snapshot",
                        headline=f"Competitor page changed: {domain}{path}",
                        summary=summary,
                        source_url=page_url,
                        relevance_score=0.7,
                        metadata={"content_hash": content_hash, "change_type": "content_changed"},
                    )

                elif old_hash is None:
                    # First snapshot — store baseline
                    self._store_market_signal(
                        client=client,
                        user_id=user_id,
                        company_name=domain,
                        signal_type="competitor_page_snapshot",
                        headline=f"Competitor page snapshot: {domain}{path}",
                        summary=f"Initial snapshot of {page_url}",
                        source_url=page_url,
                        relevance_score=0.3,
                        metadata={"content_hash": content_hash, "change_type": "initial_snapshot"},
                    )

        logger.info(
            "Competitor monitoring complete",
            extra={"user_id": user_id, "domain": domain, "changes_found": len(changes)},
        )
        return changes

    async def search_sec_filings(self, company: str) -> list[Filing]:
        """Search SEC EDGAR for company filings.

        Uses the SEC EDGAR full-text search API (public, no auth) to find
        10-K and 10-Q filings. Results are stored as market_signals for
        the user.

        Args:
            company: Company name to search for.

        Returns:
            List of Filing objects.
        """
        import httpx

        filings: list[Filing] = []
        user_id = self._user_context.user_id

        # ── Step 1: Search EDGAR full-text search ─────────────────────
        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": DEFAULT_USER_AGENT,
                    "Accept": "application/json",
                },
            ) as http_client:
                # Use the EDGAR full-text search API
                resp = await http_client.get(
                    "https://efts.sec.gov/LATEST/search-index",
                    params={
                        "q": company,
                        "dateRange": "custom",
                        "startdt": "2023-01-01",
                        "forms": "10-K,10-Q",
                        "hits.hits.total": "20",
                    },
                )

                if resp.status_code != 200:
                    # Fallback to company search endpoint
                    filings = await self._search_edgar_company(http_client, company)
                else:
                    data = resp.json()
                    hits = data.get("hits", {}).get("hits", [])

                    for hit in hits[:20]:
                        source = hit.get("_source", {})
                        filing = Filing(
                            company=source.get("display_names", [company])[0]
                            if source.get("display_names")
                            else company,
                            cik=str(source.get("entity_id", "")),
                            filing_type=source.get("form_type", ""),
                            filed_date=source.get("file_date", ""),
                            period_of_report=source.get("period_of_report", ""),
                            description=source.get("file_description", ""),
                            filing_url=f"https://www.sec.gov/Archives/edgar/data/"
                            f"{source.get('entity_id', '')}/{source.get('file_num', '')}",
                            accession_number=source.get("accession_no", ""),
                        )
                        filings.append(filing)
        except httpx.HTTPError as exc:
            logger.warning("SEC EDGAR search failed: %s", exc)
            # Try company search as fallback
            try:
                async with httpx.AsyncClient(
                    timeout=30.0,
                    headers={"User-Agent": DEFAULT_USER_AGENT},
                ) as fallback_client:
                    filings = await self._search_edgar_company(fallback_client, company)
            except Exception as fallback_exc:
                logger.warning("SEC EDGAR company search also failed: %s", fallback_exc)

        # Store filings as market signals
        if filings:
            client = SupabaseClient.get_client()
            for filing in filings:
                self._store_market_signal(
                    client=client,
                    user_id=user_id,
                    company_name=filing.company,
                    signal_type="earnings",
                    headline=f"{filing.filing_type}: {filing.company} ({filing.filed_date})",
                    summary=filing.description,
                    source_url=filing.filing_url,
                    relevance_score=0.8,
                    metadata={
                        "filing_type": filing.filing_type,
                        "cik": filing.cik,
                        "accession_number": filing.accession_number,
                        "period_of_report": filing.period_of_report,
                    },
                )

        logger.info(
            "SEC filing search complete",
            extra={"user_id": user_id, "company": company, "filings_found": len(filings)},
        )
        return filings

    async def search_patents(self, query: str) -> list[Patent]:
        """Search USPTO for patent publications.

        Uses the USPTO Open Data API (public, no auth) to find patent
        applications by keyword. Life sciences keywords are appended
        to improve relevance for therapeutic area tracking.

        Args:
            query: Search query (e.g. ``"CAR-T cell therapy"``).

        Returns:
            List of Patent objects.
        """
        import httpx

        patents: list[Patent] = []
        user_id = self._user_context.user_id

        try:
            async with httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "User-Agent": DEFAULT_USER_AGENT,
                    "Accept": "application/json",
                },
            ) as http_client:
                resp = await http_client.get(
                    USPTO_SEARCH_URL,
                    params={
                        "searchText": query,
                        "start": "0",
                        "rows": "20",
                    },
                )
                resp.raise_for_status()
                data = resp.json()

                results = data.get("results", [])
                for result in results:
                    patent = Patent(
                        title=result.get("inventionTitle", ""),
                        application_number=result.get("applicationNumber", ""),
                        publication_number=result.get("publicationNumber", ""),
                        applicant=self._extract_first_applicant(result),
                        filed_date=result.get("filingDate", ""),
                        publication_date=result.get("publicationDate", ""),
                        abstract=result.get("abstractText", [""])[0]
                        if isinstance(result.get("abstractText"), list)
                        else str(result.get("abstractText", "")),
                        patent_url=f"https://patents.google.com/patent/"
                        f"US{result.get('publicationNumber', '')}",
                    )
                    patents.append(patent)

        except httpx.HTTPError as exc:
            logger.warning("USPTO search failed: %s", exc)

        # Store patents as market signals
        if patents:
            client = SupabaseClient.get_client()
            for patent in patents:
                self._store_market_signal(
                    client=client,
                    user_id=user_id,
                    company_name=patent.applicant or "Unknown",
                    signal_type="patent",
                    headline=patent.title,
                    summary=patent.abstract[:500],
                    source_url=patent.patent_url,
                    relevance_score=0.7,
                    metadata={
                        "application_number": patent.application_number,
                        "publication_number": patent.publication_number,
                        "filed_date": patent.filed_date,
                    },
                )

        logger.info(
            "Patent search complete",
            extra={"user_id": user_id, "query": query, "patents_found": len(patents)},
        )
        return patents

    async def search_press_releases(self, company: str) -> list[PressRelease]:
        """Scrape PR Newswire and GlobeNewswire for press releases.

        Searches both major wire services for company mentions. Results
        are stored as market_signals.

        Args:
            company: Company name to search for.

        Returns:
            List of PressRelease objects.
        """
        import httpx

        releases: list[PressRelease] = []
        user_id = self._user_context.user_id

        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": DEFAULT_USER_AGENT},
        ) as http_client:
            # ── PR Newswire ───────────────────────────────────────────
            try:
                resp = await http_client.get(
                    PR_NEWSWIRE_SEARCH_URL,
                    params={"keyword": company, "page": "1", "pagesize": "10"},
                )
                if resp.status_code == 200:
                    pr_releases = self._parse_pr_newswire(resp.text, company)
                    releases.extend(pr_releases)
            except httpx.HTTPError as exc:
                logger.warning("PR Newswire search failed: %s", exc)

            # ── GlobeNewswire ─────────────────────────────────────────
            try:
                resp = await http_client.get(
                    GLOBENEWSWIRE_SEARCH_URL,
                    params={"keyword": company, "pageSize": "10"},
                )
                if resp.status_code == 200:
                    gn_releases = self._parse_globenewswire(resp.text, company)
                    releases.extend(gn_releases)
            except httpx.HTTPError as exc:
                logger.warning("GlobeNewswire search failed: %s", exc)

        # Store as market signals
        if releases:
            client = SupabaseClient.get_client()
            for pr in releases:
                signal_type = self._classify_press_release(pr.title)
                self._store_market_signal(
                    client=client,
                    user_id=user_id,
                    company_name=pr.company or company,
                    signal_type=signal_type,
                    headline=pr.title,
                    summary=pr.snippet,
                    source_url=pr.url,
                    relevance_score=0.65,
                    metadata={
                        "source_wire": pr.source,
                        "published_at": pr.published_at,
                    },
                )

        logger.info(
            "Press release search complete",
            extra={"user_id": user_id, "company": company, "releases_found": len(releases)},
        )
        return releases

    # ── Private helpers ───────────────────────────────────────────────────

    async def _fetch_with_playwright(self, url: str) -> str:
        """Fetch a JS-rendered page using Playwright headless browser.

        Falls back to empty string if Playwright is not installed.

        Args:
            url: URL to render.

        Returns:
            Rendered HTML string.
        """
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(
                    user_agent=DEFAULT_USER_AGENT,
                )
                await page.goto(url, wait_until="networkidle", timeout=30000)
                html = await page.content()
                await browser.close()
                return html
        except ImportError:
            logger.warning("Playwright not installed; JS rendering unavailable")
            return ""
        except Exception as exc:
            logger.warning("Playwright fetch failed for %s: %s", url, exc)
            return ""

    def _parse_html(self, url: str, html: str) -> StructuredContent:
        """Parse HTML and extract structured content.

        Uses BeautifulSoup to extract title, body text, meta tags,
        JSON-LD structured data, Open Graph metadata, and links.

        Args:
            url: Source URL (for resolving relative links).
            html: Raw HTML string.

        Returns:
            StructuredContent instance.
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            logger.warning("BeautifulSoup not installed; returning raw content")
            return StructuredContent(url=url, content=html[:5000])

        soup = BeautifulSoup(html, "html.parser")

        # Title
        title = ""
        title_tag = soup.find("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

        # Body text (strip scripts/styles)
        for tag in soup.find_all(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        content = soup.get_text(separator="\n", strip=True)

        # Metadata extraction
        metadata: dict[str, Any] = {}

        # Meta tags
        for meta in soup.find_all("meta"):
            name = meta.get("name") or meta.get("property", "")
            meta_content = meta.get("content", "")
            if name and meta_content:
                name_str = str(name)
                if name_str.startswith("og:") or name_str in (
                    "description",
                    "keywords",
                    "author",
                ):
                    metadata[name_str] = meta_content

        # JSON-LD structured data
        structured_data: list[dict[str, Any]] = []
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                ld_data = json.loads(script.string or "")
                if isinstance(ld_data, dict):
                    structured_data.append(ld_data)
                elif isinstance(ld_data, list):
                    structured_data.extend(item for item in ld_data if isinstance(item, dict))
            except (json.JSONDecodeError, TypeError):
                continue

        # Links
        links: list[str] = []
        for a_tag in soup.find_all("a", href=True):
            href = str(a_tag["href"])
            if href.startswith(("http://", "https://")):
                links.append(href)
            elif href.startswith("/"):
                links.append(urljoin(url, href))

        return StructuredContent(
            url=url,
            title=title,
            content=content,
            metadata=metadata,
            structured_data=structured_data,
            links=links,
        )

    async def _search_edgar_company(
        self,
        http_client: Any,
        company: str,
    ) -> list[Filing]:
        """Fallback: search EDGAR by company name via submissions endpoint.

        Args:
            http_client: Active httpx.AsyncClient.
            company: Company name to search.

        Returns:
            List of Filing objects.
        """
        filings: list[Filing] = []

        try:
            # Search for company CIK first
            resp = await http_client.get(
                f"{SEC_EDGAR_SUBMISSIONS_URL}/CIK{company.replace(' ', '').upper()}.json",
            )
            if resp.status_code != 200:
                # Try company tickers lookup
                resp = await http_client.get(
                    "https://www.sec.gov/files/company_tickers.json",
                )
                if resp.status_code != 200:
                    return filings

                tickers_data = resp.json()
                cik = None
                company_lower = company.lower()
                for entry in tickers_data.values():
                    if company_lower in str(entry.get("title", "")).lower():
                        cik = str(entry.get("cik_str", "")).zfill(10)
                        break

                if not cik:
                    return filings

                resp = await http_client.get(
                    f"{SEC_EDGAR_SUBMISSIONS_URL}/CIK{cik}.json",
                )
                if resp.status_code != 200:
                    return filings

            data = resp.json()
            company_name = data.get("name", company)
            cik_str = str(data.get("cik", "")).zfill(10)
            recent = data.get("filings", {}).get("recent", {})

            forms = recent.get("form", [])
            dates = recent.get("filingDate", [])
            accessions = recent.get("accessionNumber", [])
            descriptions = recent.get("primaryDocDescription", [])
            periods = recent.get("reportDate", [])

            for i, form in enumerate(forms):
                if form not in ("10-K", "10-Q"):
                    continue
                accession = accessions[i] if i < len(accessions) else ""
                accession_path = accession.replace("-", "")

                filing = Filing(
                    company=company_name,
                    cik=cik_str,
                    filing_type=form,
                    filed_date=dates[i] if i < len(dates) else "",
                    period_of_report=periods[i] if i < len(periods) else "",
                    description=descriptions[i] if i < len(descriptions) else "",
                    filing_url=f"https://www.sec.gov/Archives/edgar/data/{cik_str}/{accession_path}/",
                    accession_number=accession,
                )
                filings.append(filing)

                if len(filings) >= 20:
                    break

        except Exception as exc:
            logger.warning("EDGAR company search failed: %s", exc)

        return filings

    def _parse_pr_newswire(self, html: str, company: str) -> list[PressRelease]:
        """Parse PR Newswire search results HTML.

        Args:
            html: Raw HTML from PR Newswire search.
            company: Company name for attribution.

        Returns:
            List of PressRelease objects.
        """
        releases: list[PressRelease] = []

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return releases

        soup = BeautifulSoup(html, "html.parser")
        articles = soup.find_all("div", class_="row") or soup.find_all("article")

        for article in articles[:10]:
            title_tag = article.find("h3") or article.find("h2") or article.find("a")
            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            link_tag = article.find("a", href=True)
            url = ""
            if link_tag:
                href = str(link_tag["href"])
                url = (
                    href if href.startswith("http") else urljoin("https://www.prnewswire.com", href)
                )

            date_tag = article.find("h6") or article.find("time") or article.find("small")
            published_at = date_tag.get_text(strip=True) if date_tag else ""

            snippet_tag = article.find("p")
            snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""

            if title:
                releases.append(
                    PressRelease(
                        title=title,
                        company=company,
                        published_at=published_at,
                        source="PR Newswire",
                        url=url,
                        snippet=snippet,
                    )
                )

        return releases

    def _parse_globenewswire(self, html: str, company: str) -> list[PressRelease]:
        """Parse GlobeNewswire search results HTML.

        Args:
            html: Raw HTML from GlobeNewswire search.
            company: Company name for attribution.

        Returns:
            List of PressRelease objects.
        """
        releases: list[PressRelease] = []

        try:
            from bs4 import BeautifulSoup
        except ImportError:
            return releases

        soup = BeautifulSoup(html, "html.parser")
        articles = soup.find_all("div", class_="main-container") or soup.find_all("article")

        for article in articles[:10]:
            title_tag = (
                article.find("a", class_="results-link") or article.find("h1") or article.find("a")
            )
            if not title_tag:
                continue

            title = title_tag.get_text(strip=True)
            url = ""
            if title_tag.get("href"):
                href = str(title_tag["href"])
                url = (
                    href
                    if href.startswith("http")
                    else urljoin("https://www.globenewswire.com", href)
                )

            date_tag = article.find("span", class_="dt-green") or article.find("time")
            published_at = date_tag.get_text(strip=True) if date_tag else ""

            snippet_tag = article.find("div", class_="results-item-txt") or article.find("p")
            snippet = snippet_tag.get_text(strip=True) if snippet_tag else ""

            if title:
                releases.append(
                    PressRelease(
                        title=title,
                        company=company,
                        published_at=published_at,
                        source="GlobeNewswire",
                        url=url,
                        snippet=snippet,
                    )
                )

        return releases

    @staticmethod
    def _summarise_page_change(path: str, content: str) -> str:
        """Generate a brief summary of what changed on a page.

        This is a simple heuristic; a future version may use LLM
        summarisation for richer diffs.

        Args:
            path: URL path that changed.
            content: New page content.

        Returns:
            Summary string.
        """
        content_length = len(content)
        page_name = path.strip("/") or "homepage"
        return (
            f"Content update detected on /{page_name} page "
            f"({content_length:,} bytes). Review for competitive intelligence."
        )

    @staticmethod
    def _extract_first_applicant(result: dict[str, Any]) -> str:
        """Extract the first applicant name from a USPTO result.

        Args:
            result: USPTO API result dict.

        Returns:
            Applicant name string.
        """
        applicants = result.get("applicants", [])
        if isinstance(applicants, list) and applicants:
            first = applicants[0]
            if isinstance(first, dict):
                return str(first.get("applicantName", ""))
            return str(first)
        return ""

    @staticmethod
    def _classify_press_release(title: str) -> str:
        """Classify a press release into a signal type based on title.

        Args:
            title: Press release title.

        Returns:
            SignalType string value.
        """
        title_lower = title.lower()
        if any(kw in title_lower for kw in ("fda", "approval", "cleared", "authorized")):
            return "fda_approval"
        if any(kw in title_lower for kw in ("trial", "phase", "clinical", "endpoint")):
            return "clinical_trial"
        if any(kw in title_lower for kw in ("patent", "intellectual property")):
            return "patent"
        if any(kw in title_lower for kw in ("partnership", "collaboration", "agreement")):
            return "partnership"
        if any(kw in title_lower for kw in ("funding", "raise", "investment", "series")):
            return "funding"
        if any(kw in title_lower for kw in ("hire", "appoint", "ceo", "cfo", "cmo", "officer")):
            return "leadership"
        if any(kw in title_lower for kw in ("revenue", "earnings", "quarter", "annual")):
            return "earnings"
        if any(kw in title_lower for kw in ("launch", "product", "platform", "release")):
            return "product"
        return "product"  # Default for press releases

    def _store_market_signal(
        self,
        *,
        client: Any,
        user_id: str,
        company_name: str,
        signal_type: str,
        headline: str,
        summary: str,
        source_url: str,
        relevance_score: float,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Insert a row into market_signals.

        Args:
            client: Supabase client.
            user_id: Authenticated user UUID.
            company_name: Company the signal is about.
            signal_type: Signal type string.
            headline: Signal headline.
            summary: Signal summary.
            source_url: Source URL.
            relevance_score: Relevance score 0-1.
            metadata: Extra metadata.
        """
        try:
            client.table("market_signals").insert(
                {
                    "id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "company_name": company_name,
                    "signal_type": signal_type,
                    "headline": headline[:500],
                    "summary": (summary or "")[:2000],
                    "source_url": source_url,
                    "relevance_score": relevance_score,
                    "detected_at": datetime.now(UTC).isoformat(),
                    "metadata": metadata or {},
                }
            ).execute()
        except Exception as exc:
            logger.warning(
                "Failed to store market signal",
                extra={
                    "user_id": user_id,
                    "company": company_name,
                    "signal_type": signal_type,
                    "error": str(exc),
                },
            )

    def _store_corporate_fact(
        self,
        *,
        client: Any,
        company_id: str,
        subject: str,
        predicate: str,
        object_value: str,
        confidence: float,
        source: str = "extracted",
        created_by: str | None = None,
    ) -> None:
        """Insert a row into corporate_facts.

        Args:
            client: Supabase client.
            company_id: Company UUID.
            subject: Fact subject.
            predicate: Fact predicate.
            object_value: Fact object.
            confidence: Confidence score 0-1.
            source: Fact source.
            created_by: User who created the fact.
        """
        try:
            client.table("corporate_facts").insert(
                {
                    "id": str(uuid.uuid4()),
                    "company_id": company_id,
                    "subject": subject,
                    "predicate": predicate,
                    "object": object_value,
                    "confidence": confidence,
                    "source": source,
                    "created_by": created_by,
                    "created_at": datetime.now(UTC).isoformat(),
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            ).execute()
        except Exception as exc:
            logger.warning(
                "Failed to store corporate fact",
                extra={
                    "company_id": company_id,
                    "subject": subject,
                    "predicate": predicate,
                    "error": str(exc),
                },
            )

    # ── Fact extraction helpers ───────────────────────────────────────────

    @staticmethod
    def _extract_facts_from_content(
        content: StructuredContent, user_id: str
    ) -> list[dict[str, Any]]:
        """Extract semantic facts from scraped content for Graphiti/pgvector.

        Args:
            content: StructuredContent result.
            user_id: Authenticated user UUID.

        Returns:
            List of fact dicts suitable for CapabilityResult.extracted_facts.
        """
        facts: list[dict[str, Any]] = []
        if content.title:
            facts.append(
                {
                    "subject": content.url,
                    "predicate": "has_title",
                    "object": content.title,
                    "confidence": 0.90,
                    "source": f"web_scrape:{user_id}",
                }
            )
        for sd in content.structured_data:
            sd_type = sd.get("@type", "")
            sd_name = sd.get("name", "")
            if sd_type and sd_name:
                facts.append(
                    {
                        "subject": content.url,
                        "predicate": f"contains_{sd_type.lower()}",
                        "object": sd_name,
                        "confidence": 0.85,
                        "source": f"web_scrape:{user_id}",
                    }
                )
        return facts

    @staticmethod
    def _extract_facts_from_changes(changes: list[Change], user_id: str) -> list[dict[str, Any]]:
        """Extract facts from competitor monitoring changes."""
        return [
            {
                "subject": change.domain,
                "predicate": "website_changed",
                "object": change.summary,
                "confidence": 0.80,
                "source": f"competitor_monitor:{user_id}",
            }
            for change in changes
        ]

    @staticmethod
    def _extract_facts_from_filings(
        filings: list[Filing], company: str, user_id: str
    ) -> list[dict[str, Any]]:
        """Extract facts from SEC filings."""
        return [
            {
                "subject": filing.company or company,
                "predicate": f"filed_{filing.filing_type.lower().replace('-', '_')}",
                "object": f"Filed {filing.filing_type} on {filing.filed_date}",
                "confidence": 0.95,
                "source": f"sec_edgar:{user_id}",
            }
            for filing in filings
        ]

    @staticmethod
    def _extract_facts_from_patents(patents: list[Patent], user_id: str) -> list[dict[str, Any]]:
        """Extract facts from patent search results."""
        return [
            {
                "subject": patent.applicant or "Unknown",
                "predicate": "filed_patent",
                "object": patent.title,
                "confidence": 0.90,
                "source": f"uspto:{user_id}",
            }
            for patent in patents
        ]

    @staticmethod
    def _extract_facts_from_press_releases(
        releases: list[PressRelease], user_id: str
    ) -> list[dict[str, Any]]:
        """Extract facts from press release search results."""
        return [
            {
                "subject": pr.company or "Unknown",
                "predicate": "announced",
                "object": pr.title,
                "confidence": 0.75,
                "source": f"press_release:{user_id}",
            }
            for pr in releases
        ]
