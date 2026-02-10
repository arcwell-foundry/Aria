"""KOLMapperSkill -- maps and ranks Key Opinion Leaders via PubMed publication data.

This is a Category B+ LLM skill that augments LLM analysis with real
PubMed E-utilities API data. It fetches publication records from NCBI,
extracts author/journal metadata, and injects the structured data into
prompt templates so the LLM can score and rank KOLs with grounded evidence.

Assigned to: AnalystAgent, ScoutAgent
Trust level: core

PubMed API reference:
    https://www.ncbi.nlm.nih.gov/books/NBK25500/
Rate limit: 3 requests/second without API key.
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

# ---------------------------------------------------------------------------
# PubMed E-utilities constants
# ---------------------------------------------------------------------------

_PUBMED_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_ESEARCH_URL = f"{_PUBMED_BASE}/esearch.fcgi"
_ESUMMARY_URL = f"{_PUBMED_BASE}/esummary.fcgi"

# NCBI allows 3 req/s without an API key.  0.34s sleep guarantees compliance.
_RATE_LIMIT_DELAY: float = 0.34

# Maximum PMIDs per esummary batch (NCBI recommended ceiling)
_BATCH_SIZE: int = 100

# httpx timeout for PubMed requests
_HTTP_TIMEOUT: float = 30.0

# Context variable keys
CONTEXT_THERAPEUTIC_AREA = "therapeutic_area"
CONTEXT_TEMPLATE_NAME = "template_name"
CONTEXT_PUBMED_DATA = "pubmed_data"

# Template name constants
TEMPLATE_KOL_LANDSCAPE = "kol_landscape"
TEMPLATE_PUBLICATION_TRACKER = "publication_tracker"
TEMPLATE_INFLUENCE_RANKING = "influence_ranking"


class KOLMapperSkill(BaseSkillDefinition):
    """Map and rank Key Opinion Leaders using PubMed publication data.

    Extends :class:`BaseSkillDefinition` with real HTTP calls to the
    NCBI PubMed E-utilities API.  Publication search results and author
    metadata are injected into the LLM prompt context so the model can
    produce grounded KOL rankings rather than relying purely on
    parametric knowledge.

    If PubMed is unreachable the skill falls back to LLM-only analysis
    with a warning logged and a ``pubmed_unavailable`` flag in the context.

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
            "kol_mapper",
            llm_client,
            definitions_dir=definitions_dir,
        )

    # ------------------------------------------------------------------
    # MeSH-aware query builder
    # ------------------------------------------------------------------

    @staticmethod
    def _build_mesh_query(therapeutic_area: str) -> str:
        """Build a MeSH-aware PubMed search query from a therapeutic area.

        Combines a MeSH term search with a title/abstract keyword search
        so that results include both formally-indexed articles and recent
        publications that have not yet received MeSH annotations.

        Args:
            therapeutic_area: Free-text therapeutic area description
                (e.g. ``"non-small cell lung cancer"``).

        Returns:
            PubMed query string ready for the ``term`` parameter.
        """
        # Normalise whitespace
        area = " ".join(therapeutic_area.strip().split())

        # MeSH heading search OR keyword in title/abstract
        mesh_part = f'"{area}"[MeSH Terms]'
        keyword_part = f'"{area}"[Title/Abstract]'

        return f"({mesh_part} OR {keyword_part})"

    # ------------------------------------------------------------------
    # PubMed API: search
    # ------------------------------------------------------------------

    async def search_publications(
        self,
        therapeutic_area: str,
        limit: int = 200,
    ) -> dict[str, Any]:
        """Search PubMed for publications in a therapeutic area.

        Constructs a MeSH-aware query, calls the ``esearch`` endpoint,
        and returns the total hit count together with the list of PMIDs
        returned (up to *limit*).

        Args:
            therapeutic_area: Target therapeutic area.
            limit: Maximum number of PMIDs to retrieve (default 200).

        Returns:
            Dict with keys:
                - ``total_count`` (int): Total matching records in PubMed.
                - ``id_list`` (list[str]): PMIDs returned for this page.
                - ``query`` (str): The query that was sent.

        Raises:
            httpx.HTTPStatusError: On non-2xx responses (caught upstream).
        """
        query = self._build_mesh_query(therapeutic_area)

        params: dict[str, str | int] = {
            "db": "pubmed",
            "term": query,
            "retmax": limit,
            "sort": "date",
            "retmode": "json",
        }

        logger.info(
            "PubMed esearch request",
            extra={"query": query, "retmax": limit},
        )

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            response = await client.get(_ESEARCH_URL, params=params)
            response.raise_for_status()

        data = response.json()
        esearch_result = data.get("esearchresult", {})

        total_count = int(esearch_result.get("count", 0))
        id_list: list[str] = esearch_result.get("idlist", [])

        logger.info(
            "PubMed esearch completed",
            extra={"total_count": total_count, "returned": len(id_list)},
        )

        return {
            "total_count": total_count,
            "id_list": id_list,
            "query": query,
        }

    # ------------------------------------------------------------------
    # PubMed API: fetch summaries
    # ------------------------------------------------------------------

    async def fetch_summaries(self, pmids: list[str]) -> list[dict[str, Any]]:
        """Fetch publication summaries from PubMed for a list of PMIDs.

        Calls the ``esummary`` endpoint in batches of up to 100 PMIDs
        (NCBI recommended maximum) with rate-limit sleeps between each
        request.

        Each returned dict contains:
            - ``pmid`` (str)
            - ``title`` (str)
            - ``authors`` (list[dict]): Each with ``name`` and ``authtype``.
            - ``journal`` (str): Abbreviated journal name.
            - ``pub_date`` (str): Publication date string.
            - ``doi`` (str): DOI if available.

        Args:
            pmids: List of PubMed IDs to retrieve.

        Returns:
            List of publication summary dicts.
        """
        if not pmids:
            return []

        summaries: list[dict[str, Any]] = []

        # Chunk into batches
        batches: list[list[str]] = [
            pmids[i : i + _BATCH_SIZE] for i in range(0, len(pmids), _BATCH_SIZE)
        ]

        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            for batch_idx, batch in enumerate(batches):
                # Rate-limit: sleep before every request except the first
                if batch_idx > 0:
                    await asyncio.sleep(_RATE_LIMIT_DELAY)

                id_list = ",".join(batch)
                params: dict[str, str] = {
                    "db": "pubmed",
                    "id": id_list,
                    "retmode": "json",
                }

                logger.info(
                    "PubMed esummary request",
                    extra={
                        "batch": batch_idx + 1,
                        "total_batches": len(batches),
                        "pmid_count": len(batch),
                    },
                )

                response = await client.get(_ESUMMARY_URL, params=params)
                response.raise_for_status()

                data = response.json()
                result = data.get("result", {})

                for pmid in batch:
                    article = result.get(pmid)
                    if article is None:
                        continue

                    # Extract author list
                    raw_authors = article.get("authors", [])
                    authors = [
                        {
                            "name": a.get("name", ""),
                            "authtype": a.get("authtype", "Author"),
                        }
                        for a in raw_authors
                        if isinstance(a, dict)
                    ]

                    # Extract DOI from articleids if present
                    doi = ""
                    for aid in article.get("articleids", []):
                        if isinstance(aid, dict) and aid.get("idtype") == "doi":
                            doi = aid.get("value", "")
                            break

                    summaries.append(
                        {
                            "pmid": pmid,
                            "title": article.get("title", ""),
                            "authors": authors,
                            "journal": article.get("fulljournalname", "")
                            or article.get("source", ""),
                            "pub_date": article.get("pubdate", ""),
                            "doi": doi,
                        }
                    )

        logger.info(
            "PubMed esummary completed",
            extra={"total_summaries": len(summaries)},
        )

        return summaries

    # ------------------------------------------------------------------
    # High-level analysis entry point
    # ------------------------------------------------------------------

    async def generate_analysis(
        self,
        template_name: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate a KOL analysis by combining PubMed data with LLM reasoning.

        This is the primary entry point. It:

        1. Calls :meth:`search_publications` for the therapeutic area.
        2. Calls :meth:`fetch_summaries` for the returned PMIDs.
        3. Injects the real PubMed data into the context as ``pubmed_data``.
        4. Delegates to :meth:`run_template` for LLM-driven analysis.

        If PubMed is unreachable the method falls back to LLM-only
        analysis, logs a warning, and sets a ``pubmed_unavailable`` flag
        in the context so the LLM can adjust its confidence accordingly.

        Args:
            template_name: One of ``kol_landscape``, ``publication_tracker``,
                or ``influence_ranking``.
            context: Context dict containing at least ``therapeutic_area``.

        Returns:
            Parsed JSON output from the LLM conforming to the skill's
            output schema.

        Raises:
            ValueError: If the template is unknown or required context
                keys are missing.
        """
        therapeutic_area = context.get(CONTEXT_THERAPEUTIC_AREA)
        if not therapeutic_area:
            raise ValueError("Context must include 'therapeutic_area' for KOL mapping.")

        # -- Fetch real PubMed data (with graceful fallback) ---------------

        pubmed_data: dict[str, Any] = {}
        pubmed_available = True

        try:
            search_result = await self.search_publications(therapeutic_area)

            # Rate-limit before the summary call
            await asyncio.sleep(_RATE_LIMIT_DELAY)

            summaries = await self.fetch_summaries(search_result["id_list"])

            pubmed_data = {
                "total_count": search_result["total_count"],
                "search_query": search_result["query"],
                "publications": summaries,
                "publication_count_returned": len(summaries),
            }

            logger.info(
                "PubMed data fetched for KOL analysis",
                extra={
                    "therapeutic_area": therapeutic_area,
                    "publications_fetched": len(summaries),
                },
            )

        except httpx.HTTPStatusError as exc:
            logger.warning(
                "PubMed API returned error status; falling back to LLM-only",
                extra={
                    "status_code": exc.response.status_code,
                    "therapeutic_area": therapeutic_area,
                },
            )
            pubmed_available = False

        except httpx.RequestError as exc:
            logger.warning(
                "PubMed API unreachable; falling back to LLM-only analysis",
                extra={
                    "error": str(exc),
                    "therapeutic_area": therapeutic_area,
                },
            )
            pubmed_available = False

        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning(
                "Failed to parse PubMed response; falling back to LLM-only",
                extra={
                    "error": str(exc),
                    "therapeutic_area": therapeutic_area,
                },
            )
            pubmed_available = False

        # -- Inject PubMed data into context for the LLM -------------------

        enriched_context = dict(context)

        if pubmed_available and pubmed_data:
            enriched_context[CONTEXT_PUBMED_DATA] = json.dumps(pubmed_data, indent=2, default=str)
        else:
            enriched_context[CONTEXT_PUBMED_DATA] = json.dumps(
                {
                    "pubmed_unavailable": True,
                    "note": (
                        "PubMed data could not be retrieved. Provide analysis "
                        "based on your parametric knowledge and flag reduced "
                        "confidence in the output metadata."
                    ),
                }
            )

        logger.info(
            "Running KOL analysis template",
            extra={
                "template": template_name,
                "therapeutic_area": therapeutic_area,
                "pubmed_available": pubmed_available,
            },
        )

        return await self.run_template(template_name, enriched_context)
