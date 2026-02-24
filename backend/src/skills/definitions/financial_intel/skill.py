"""FinancialIntelSkill — SEC EDGAR-backed financial intelligence analysis.

This is a Category B LLM skill (structured prompt chain) that enriches
its prompts with real filing data from the SEC EDGAR full-text search
API before delegating to the LLM for analysis.

Assigned to: AnalystAgent, StrategistAgent
Trust level: core
"""

import asyncio
import json
import logging
from pathlib import Path
from typing import Any

import httpx

from src.core.llm import LLMClient
from src.skills.definitions.base import BaseSkillDefinition

logger = logging.getLogger(__name__)

# SEC EDGAR API configuration
EDGAR_SEARCH_URL = "https://efts.sec.gov/LATEST/search-index"
EDGAR_USER_AGENT = "ARIA-Intelligence research@aria-ai.com"
EDGAR_RATE_LIMIT_DELAY = 0.1  # seconds between requests (max 10 req/s)
EDGAR_REQUEST_TIMEOUT = 15.0  # seconds

# Template name constants
TEMPLATE_COMPANY_FINANCIAL_SNAPSHOT = "company_financial_snapshot"
TEMPLATE_REVENUE_TREND_ANALYSIS = "revenue_trend_analysis"
TEMPLATE_RD_INVESTMENT_TRACKER = "rd_investment_tracker"

# Context variable keys
CONTEXT_COMPANY_NAME = "company_name"
CONTEXT_TEMPLATE_NAME = "template_name"
CONTEXT_EDGAR_FILINGS = "edgar_filings"

# Required context keys per template
_TEMPLATE_REQUIREMENTS: dict[str, list[str]] = {
    TEMPLATE_COMPANY_FINANCIAL_SNAPSHOT: [CONTEXT_COMPANY_NAME],
    TEMPLATE_REVENUE_TREND_ANALYSIS: [CONTEXT_COMPANY_NAME],
    TEMPLATE_RD_INVESTMENT_TRACKER: [CONTEXT_COMPANY_NAME],
}


class FinancialIntelSkill(BaseSkillDefinition):
    """Extract and analyze SEC EDGAR filings for financial intelligence.

    Wraps the ``financial_intel`` skill definition and enriches template
    prompts with real filing metadata fetched from the SEC EDGAR
    full-text search API before sending them to the LLM.

    When EDGAR is unreachable the skill degrades gracefully, falling
    back to LLM-only analysis with a note that live filing data was
    unavailable.

    Args:
        llm_client: LLM client for prompt execution.
        definitions_dir: Override for the skill definitions base directory.
    """

    def __init__(
        self,
        llm_client: LLMClient,
        *,
        definitions_dir: Path | None = None,
    ) -> None:
        super().__init__(
            "financial_intel",
            llm_client,
            definitions_dir=definitions_dir,
        )
        self._last_request_time: float = 0.0

    # -- Context validation ----------------------------------------------------

    def validate_template_context(
        self,
        template_name: str,
        context: dict[str, Any],
    ) -> list[str]:
        """Check that all required context keys are present for a template.

        Args:
            template_name: The template to validate against.
            context: The context dict to check.

        Returns:
            List of missing key names (empty if all present).
        """
        required = _TEMPLATE_REQUIREMENTS.get(template_name, [])
        return [key for key in required if key not in context]

    # -- EDGAR API interaction -------------------------------------------------

    async def _enforce_rate_limit(self) -> None:
        """Ensure at least EDGAR_RATE_LIMIT_DELAY seconds between requests.

        SEC EDGAR enforces a maximum of 10 requests per second. This
        method sleeps if the last request was made too recently.
        """
        now = asyncio.get_event_loop().time()
        elapsed = now - self._last_request_time
        if elapsed < EDGAR_RATE_LIMIT_DELAY:
            await asyncio.sleep(EDGAR_RATE_LIMIT_DELAY - elapsed)
        self._last_request_time = asyncio.get_event_loop().time()

    async def fetch_filings(
        self,
        company_name: str,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        """Fetch recent 10-K and 10-Q filing metadata from SEC EDGAR.

        Calls the EDGAR full-text search API, parses the JSON response,
        and returns a list of filing metadata dicts.

        Args:
            company_name: Company name to search for in EDGAR.
            limit: Maximum number of filings to return (default 10).

        Returns:
            List of dicts with keys: ``accession_number``, ``form_type``,
            ``filed_date``, ``entity_name``, ``file_number``, and ``period``.
            Returns an empty list if the API is unreachable or returns
            no results.
        """
        await self._enforce_rate_limit()

        params: dict[str, Any] = {
            "q": company_name,
            "forms": "10-K,10-Q",
        }

        headers = {
            "User-Agent": EDGAR_USER_AGENT,
            "Accept": "application/json",
        }

        logger.info(
            "Fetching EDGAR filings",
            extra={
                "company": company_name,
                "limit": limit,
                "url": EDGAR_SEARCH_URL,
            },
        )

        try:
            async with httpx.AsyncClient(timeout=EDGAR_REQUEST_TIMEOUT) as client:
                response = await client.get(
                    EDGAR_SEARCH_URL,
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()

            data = response.json()
        except httpx.TimeoutException:
            logger.warning(
                "EDGAR API request timed out",
                extra={"company": company_name},
            )
            return []
        except httpx.HTTPStatusError as exc:
            logger.warning(
                "EDGAR API returned error status",
                extra={
                    "company": company_name,
                    "status_code": exc.response.status_code,
                    "detail": str(exc),
                },
            )
            return []
        except httpx.RequestError as exc:
            logger.warning(
                "EDGAR API request failed",
                extra={
                    "company": company_name,
                    "error": str(exc),
                },
            )
            return []
        except (json.JSONDecodeError, ValueError) as exc:
            logger.warning(
                "Failed to parse EDGAR API response",
                extra={
                    "company": company_name,
                    "error": str(exc),
                },
            )
            return []

        filings = self._parse_edgar_response(data, limit)

        logger.info(
            "EDGAR filings fetched",
            extra={
                "company": company_name,
                "filings_found": len(filings),
            },
        )

        return filings

    def _parse_edgar_response(
        self,
        data: dict[str, Any],
        limit: int,
    ) -> list[dict[str, Any]]:
        """Parse the EDGAR search API JSON response into filing dicts.

        Args:
            data: Raw JSON response from the EDGAR search API.
            limit: Maximum number of filings to return.

        Returns:
            List of normalized filing metadata dicts.
        """
        hits = data.get("hits", {}).get("hits", [])
        if not hits:
            return []

        filings: list[dict[str, Any]] = []
        for hit in hits[:limit]:
            source = hit.get("_source", {})

            # Entity name: EDGAR returns a list under display_names
            display_names = source.get("display_names", [])
            entity_name = display_names[0] if display_names else ""

            # Form type: EDGAR returns root_forms (list) or form (str)
            root_forms = source.get("root_forms", [])
            form_type = root_forms[0] if root_forms else source.get("form", "")

            # File number: may be a list
            file_num_raw = source.get("file_num", "")
            file_number = (
                file_num_raw[0] if isinstance(file_num_raw, list) and file_num_raw
                else str(file_num_raw)
            )

            filing: dict[str, Any] = {
                "accession_number": source.get("adsh", ""),
                "form_type": form_type,
                "filed_date": source.get("file_date", ""),
                "entity_name": entity_name,
                "file_number": file_number,
                "period": source.get("period_ending", ""),
            }
            filings.append(filing)

        return filings

    # -- Analysis generation ---------------------------------------------------

    async def generate_analysis(
        self,
        template_name: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate financial analysis enriched with real EDGAR data.

        This is the primary entry point. It:
        1. Validates context keys for the requested template.
        2. Fetches live filing data from SEC EDGAR.
        3. Injects the EDGAR data into the context as ``edgar_filings``.
        4. Delegates to :meth:`run_template` for LLM-based analysis.

        If the EDGAR API is unreachable, the method falls back to
        LLM-only analysis with an empty filings list and logs a
        warning.

        Args:
            template_name: One of the defined template names
                (``company_financial_snapshot``, ``revenue_trend_analysis``,
                ``rd_investment_tracker``).
            context: Context dict containing at least ``company_name``.

        Returns:
            Parsed JSON output matching the skill's output schema with
            ``chart_type``, ``data``, ``config``, ``metadata``, and
            ``financial_context`` keys.

        Raises:
            ValueError: If required context keys are missing or the
                template is unknown.
        """
        missing = self.validate_template_context(template_name, context)
        if missing:
            raise ValueError(f"Template '{template_name}' is missing required context: {missing}")

        company_name: str = context[CONTEXT_COMPANY_NAME]

        # Fetch real filing data from EDGAR
        filings = await self.fetch_filings(company_name)

        if not filings:
            logger.warning(
                "No EDGAR filings found or API unavailable; falling back to LLM-only analysis",
                extra={
                    "company": company_name,
                    "template": template_name,
                },
            )

        # Inject EDGAR data into context for the prompt template
        enriched_context = {
            **context,
            CONTEXT_EDGAR_FILINGS: json.dumps(filings, indent=2),
        }

        logger.info(
            "Generating financial analysis",
            extra={
                "skill": self._skill_name,
                "template": template_name,
                "company": company_name,
                "edgar_filings_count": len(filings),
            },
        )

        return await self.run_template(template_name, enriched_context)
