"""TrialRadarSkill -- clinical trial intelligence from ClinicalTrials.gov.

This skill queries the ClinicalTrials.gov API v2 (public, no auth) to
pull real trial data for a given therapeutic area, then feeds that data
into LLM prompt templates for structured analysis.

Category B skill (structured prompt chain) with an HTTP data-fetch
pre-step before LLM invocation.

Assigned to: AnalystAgent, ScoutAgent, StrategistAgent
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

# ---------------------------------------------------------------------------
# ClinicalTrials.gov API v2 constants
# ---------------------------------------------------------------------------

_CT_BASE_URL = "https://clinicaltrials.gov/api/v2/studies"

_DEFAULT_STATUSES = "RECRUITING,ACTIVE_NOT_RECRUITING"

_MAX_RETRIES = 3
_INITIAL_BACKOFF_SECONDS = 1.0
_BACKOFF_MULTIPLIER = 2.0
_REQUEST_TIMEOUT_SECONDS = 30.0

# Template name constants
TEMPLATE_TRIAL_LANDSCAPE = "trial_landscape"
TEMPLATE_ENROLLMENT_TRACKER = "enrollment_tracker"
TEMPLATE_COMPETITIVE_TRIAL_COMPARISON = "competitive_trial_comparison"

# Context variable keys expected by templates
CONTEXT_THERAPEUTIC_AREA = "therapeutic_area"
CONTEXT_TEMPLATE_NAME = "template_name"
CONTEXT_CLINICAL_TRIALS_DATA = "clinical_trials_data"


class TrialRadarSkill(BaseSkillDefinition):
    """Search ClinicalTrials.gov and analyse trial landscapes via LLM.

    Combines live HTTP queries against the ClinicalTrials.gov API v2 with
    prompt-template-driven LLM analysis to produce structured competitive
    intelligence on clinical trials.

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
            "trial_radar",
            llm_client,
            definitions_dir=definitions_dir,
        )

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _request_with_backoff(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        """Issue a GET request with exponential backoff on 429 responses.

        Args:
            client: An open ``httpx.AsyncClient``.
            url: The URL to GET.
            params: Optional query parameters.

        Returns:
            The successful ``httpx.Response``.

        Raises:
            httpx.HTTPStatusError: If all retries are exhausted or a
                non-retryable error status is returned.
        """
        backoff = _INITIAL_BACKOFF_SECONDS

        for attempt in range(1, _MAX_RETRIES + 1):
            response = await client.get(url, params=params)

            if response.status_code == 429:
                if attempt == _MAX_RETRIES:
                    logger.warning(
                        "ClinicalTrials.gov rate limit exhausted after %d retries",
                        _MAX_RETRIES,
                    )
                    response.raise_for_status()

                retry_after = response.headers.get("Retry-After")
                wait = float(retry_after) if retry_after else backoff

                logger.info(
                    "ClinicalTrials.gov 429 — backing off %.1fs (attempt %d/%d)",
                    wait,
                    attempt,
                    _MAX_RETRIES,
                )
                await asyncio.sleep(wait)
                backoff *= _BACKOFF_MULTIPLIER
                continue

            # Any non-429 error should raise immediately
            response.raise_for_status()
            return response

        # Shouldn't be reached, but satisfy the type checker
        raise httpx.HTTPStatusError(  # pragma: no cover
            "Retries exhausted",
            request=httpx.Request("GET", url),
            response=response,  # type: ignore[possibly-undefined]
        )

    # ------------------------------------------------------------------
    # ClinicalTrials.gov API v2 methods
    # ------------------------------------------------------------------

    async def search_trials(
        self,
        therapeutic_area: str,
        *,
        max_results: int = 100,
    ) -> dict[str, Any]:
        """Search ClinicalTrials.gov for trials matching *therapeutic_area*.

        Calls the studies search endpoint, parses the JSON response, and
        returns a normalised dict of trial records.

        Args:
            therapeutic_area: Condition or therapeutic area to search for
                (e.g. ``"non-small cell lung cancer"``).
            max_results: Maximum number of studies to return (capped at
                1000 by the API; default 100).

        Returns:
            A dict with keys:
                - ``total_count`` (int): Total matching studies reported
                  by the API.
                - ``trials`` (list[dict]): Normalised trial records with
                  keys ``nct_id``, ``title``, ``phase``, ``status``,
                  ``sponsor``, ``enrollment``, ``start_date``,
                  ``primary_completion_date``, ``interventions``.
        """
        params: dict[str, Any] = {
            "query.cond": therapeutic_area,
            "filter.overallStatus": _DEFAULT_STATUSES,
            "pageSize": min(max_results, 1000),
            "format": "json",
        }

        try:
            async with httpx.AsyncClient(
                timeout=_REQUEST_TIMEOUT_SECONDS,
            ) as client:
                response = await self._request_with_backoff(
                    client,
                    _CT_BASE_URL,
                    params=params,
                )
                data = response.json()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning(
                "ClinicalTrials.gov search failed for '%s': %s",
                therapeutic_area,
                exc,
            )
            return {"total_count": 0, "trials": []}

        total_count: int = data.get("totalCount", 0)
        raw_studies: list[dict[str, Any]] = data.get("studies", [])

        trials: list[dict[str, Any]] = []
        for study in raw_studies:
            trials.append(self._normalise_study(study))

        logger.info(
            "ClinicalTrials.gov returned %d/%d trials for '%s'",
            len(trials),
            total_count,
            therapeutic_area,
        )

        return {"total_count": total_count, "trials": trials}

    async def get_trial_detail(self, nct_id: str) -> dict[str, Any] | None:
        """Fetch full detail for a single trial by NCT ID.

        Args:
            nct_id: The ClinicalTrials.gov identifier (e.g. ``"NCT06012345"``).

        Returns:
            Normalised trial dict, or ``None`` if the request fails.
        """
        url = f"{_CT_BASE_URL}/{nct_id}"
        params: dict[str, str] = {"format": "json"}

        try:
            async with httpx.AsyncClient(
                timeout=_REQUEST_TIMEOUT_SECONDS,
            ) as client:
                response = await self._request_with_backoff(
                    client,
                    url,
                    params=params,
                )
                data = response.json()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning(
                "ClinicalTrials.gov detail fetch failed for '%s': %s",
                nct_id,
                exc,
            )
            return None

        return self._normalise_study(data)

    # ------------------------------------------------------------------
    # Response normalisation
    # ------------------------------------------------------------------

    @staticmethod
    def _normalise_study(study: dict[str, Any]) -> dict[str, Any]:
        """Extract and flatten relevant fields from a CT.gov v2 study object.

        The v2 API nests data under ``protocolSection`` with sub-objects
        like ``identificationModule``, ``statusModule``, etc.

        Args:
            study: Raw study dict from the API.

        Returns:
            Flat dict with standardised keys.
        """
        protocol: dict[str, Any] = study.get("protocolSection", {})

        ident = protocol.get("identificationModule", {})
        status_mod = protocol.get("statusModule", {})
        design = protocol.get("designModule", {})
        sponsor_mod = protocol.get("sponsorCollaboratorsModule", {})
        arms_mod = protocol.get("armsInterventionsModule", {})
        outcomes_mod = protocol.get("outcomesModule", {})

        # Interventions list
        interventions_raw: list[dict[str, Any]] = arms_mod.get("interventions", [])
        interventions: list[str] = [iv.get("name", "Unknown") for iv in interventions_raw]

        # Primary endpoint
        primary_outcomes: list[dict[str, Any]] = outcomes_mod.get("primaryOutcomes", [])
        primary_endpoint: str = ""
        if primary_outcomes:
            primary_endpoint = primary_outcomes[0].get("measure", "")

        # Dates -- CT.gov v2 stores these as structs with "date" key
        start_date_obj = status_mod.get("startDateStruct", {})
        completion_date_obj = status_mod.get("primaryCompletionDateStruct", {})

        # Sponsor
        lead_sponsor: dict[str, Any] = sponsor_mod.get("leadSponsor", {})

        # Enrollment
        enrollment_info: dict[str, Any] = design.get("enrollmentInfo", {})

        # Phase list
        phases_raw: list[str] = design.get("phases", [])
        phase_str: str = ", ".join(phases_raw) if phases_raw else "N/A"

        return {
            "nct_id": ident.get("nctId", ""),
            "title": ident.get("briefTitle", ""),
            "phase": phase_str,
            "status": status_mod.get("overallStatus", ""),
            "sponsor": lead_sponsor.get("name", ""),
            "enrollment": enrollment_info.get("count", 0),
            "start_date": start_date_obj.get("date", ""),
            "primary_completion_date": completion_date_obj.get("date", ""),
            "interventions": interventions,
            "primary_endpoint": primary_endpoint,
        }

    # ------------------------------------------------------------------
    # High-level analysis
    # ------------------------------------------------------------------

    async def generate_analysis(
        self,
        template_name: str,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Fetch live trial data and run an LLM analysis template.

        This is the primary entry point for consumers. It:

        1. Calls :meth:`search_trials` for the ``therapeutic_area``
           found in *context*.
        2. Injects the real trial data into *context* under the key
           ``clinical_trials_data``.
        3. Delegates to :meth:`run_template` for LLM-driven analysis.

        If the ClinicalTrials.gov API is unreachable, the method falls
        back to LLM-only analysis (no real data injected) and logs a
        warning.

        Args:
            template_name: One of ``trial_landscape``,
                ``enrollment_tracker``, or
                ``competitive_trial_comparison``.
            context: Context dict.  Must include ``therapeutic_area``.

        Returns:
            Parsed JSON output conforming to the skill's output schema.

        Raises:
            ValueError: If ``therapeutic_area`` is missing from context
                or the template name is unknown.
        """
        therapeutic_area: str | None = context.get(CONTEXT_THERAPEUTIC_AREA)
        if not therapeutic_area:
            raise ValueError("TrialRadarSkill requires 'therapeutic_area' in context")

        logger.info(
            "Generating trial analysis",
            extra={
                "skill": self._skill_name,
                "template": template_name,
                "therapeutic_area": therapeutic_area,
            },
        )

        # --- Fetch live trial data ---
        search_result = await self.search_trials(therapeutic_area)

        if search_result["trials"]:
            context[CONTEXT_CLINICAL_TRIALS_DATA] = json.dumps(search_result, indent=2)
            logger.info(
                "Injected %d trials into LLM context",
                len(search_result["trials"]),
            )
        else:
            logger.warning(
                "No trial data available for '%s' — falling back to LLM-only analysis",
                therapeutic_area,
            )
            context[CONTEXT_CLINICAL_TRIALS_DATA] = json.dumps(
                {
                    "total_count": 0,
                    "trials": [],
                    "note": (
                        f"ClinicalTrials.gov returned no results for "
                        f"'{therapeutic_area}'. Generate analysis based on "
                        f"your training knowledge and note the data gap."
                    ),
                },
                indent=2,
            )

        # --- Delegate to LLM template ---
        return await self.run_template(template_name, context)
