# US-304: Analyst Agent Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement the Analyst Agent for ARIA with tools for PubMed, ClinicalTrials.gov, FDA, and ChEMBL searches to provide scientific research capabilities.

**Architecture:** The AnalystAgent extends BaseAgent and implements async tool methods for querying scientific APIs. It validates research questions, uses httpx for API calls with rate limiting, caches results, and returns structured research reports with citations.

**Tech Stack:** Python 3.11+, httpx (already in requirements), pytest, mocking for tests

---

## Task 1: Create AnalystAgent module stub with name and description

**Files:**
- Create: `backend/src/agents/analyst.py`

**Step 1: Write the failing test**

Create test file: `backend/tests/test_analyst_agent.py`

```python
"""Tests for AnalystAgent module."""

from unittest.mock import MagicMock

import pytest


def test_analyst_agent_has_name_and_description() -> None:
    """Test AnalystAgent has correct name and description class attributes."""
    from src.agents.analyst import AnalystAgent

    assert AnalystAgent.name == "Analyst"
    assert AnalystAgent.description == "Scientific research agent for life sciences queries"


def test_analyst_agent_extends_base_agent() -> None:
    """Test AnalystAgent extends BaseAgent."""
    from src.agents.base import BaseAgent
    from src.agents.analyst import AnalystAgent

    assert issubclass(AnalystAgent, BaseAgent)
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_analyst_agent.py -v`
Expected: FAIL with "ModuleNotFoundError: No module named 'src.agents.analyst'"

**Step 3: Write minimal implementation**

Create: `backend/src/agents/analyst.py`

```python
"""AnalystAgent module for ARIA.

Provides scientific research capabilities using life sciences APIs
including PubMed, ClinicalTrials.gov, FDA, and ChEMBL.
"""

from typing import Any

from src.agents.base import BaseAgent


class AnalystAgent(BaseAgent):
    """Scientific research agent for life sciences queries.

    The Analyst agent searches scientific databases to provide
    domain expertise, literature reviews, and data extraction
    from biomedical APIs.
    """

    name = "Analyst"
    description = "Scientific research agent for life sciences queries"

    def __init__(self, llm_client: Any, user_id: str) -> None:
        """Initialize the Analyst agent.

        Args:
            llm_client: LLM client for reasoning and generation.
            user_id: ID of the user this agent is working for.
        """
        self._research_cache: dict[str, Any] = {}
        super().__init__(llm_client=llm_client, user_id=user_id)

    def _register_tools(self) -> dict[str, Any]:
        """Register Analyst agent's research tools.

        Returns:
            Dictionary mapping tool names to callable functions.
        """
        return {
            "pubmed_search": self._pubmed_search,
            "clinical_trials_search": self._clinical_trials_search,
            "fda_drug_search": self._fda_drug_search,
            "chembl_search": self._chembl_search,
        }

    async def execute(self, task: dict[str, Any]) -> Any:
        """Execute the analyst agent's primary task.

        Args:
            task: Task specification with parameters.

        Returns:
            AgentResult with success status and output data.
        """
        from src.agents.base import AgentResult

        return AgentResult(success=True, data={})
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_analyst_agent.py -v`
Expected: PASS (2 tests pass)

**Step 5: Commit**

```bash
git add backend/src/agents/analyst.py backend/tests/test_analyst_agent.py
git commit -m "feat(agents): add AnalystAgent stub with name and description"
```

---

## Task 2: Add initialization tests and cache attribute

**Files:**
- Modify: `backend/tests/test_analyst_agent.py`
- Modify: `backend/src/agents/analyst.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_analyst_agent.py`:

```python
def test_analyst_agent_initializes_with_llm_and_user() -> None:
    """Test AnalystAgent initializes with llm_client, user_id, and _research_cache."""
    from src.agents.base import AgentStatus
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    assert agent.llm == mock_llm
    assert agent.user_id == "user-123"
    assert agent.status == AgentStatus.IDLE
    assert hasattr(agent, "_research_cache")
    assert agent._research_cache == {}
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_analyst_agent.py::test_analyst_agent_initializes_with_llm_and_user -v`
Expected: PASS (already have _research_cache in __init__)

**Step 3: No implementation needed**

The implementation from Task 1 already includes _research_cache.

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_analyst_agent.py -v`
Expected: PASS (3 tests pass)

**Step 5: Commit**

```bash
git add backend/tests/test_analyst_agent.py
git commit -m "test(agents): add AnalystAgent initialization test"
```

---

## Task 3: Test tool registration

**Files:**
- Modify: `backend/tests/test_analyst_agent.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_analyst_agent.py`:

```python
def test_analyst_agent_registers_four_tools() -> None:
    """Test AnalystAgent._register_tools returns dict with 4 tools."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    tools = agent.tools

    assert len(tools) == 4
    assert "pubmed_search" in tools
    assert "clinical_trials_search" in tools
    assert "fda_drug_search" in tools
    assert "chembl_search" in tools
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_analyst_agent.py::test_analyst_agent_registers_four_tools -v`
Expected: PASS (tools already registered in Task 1)

**Step 3: No implementation needed**

The implementation from Task 1 already includes tool registration.

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_analyst_agent.py -v`
Expected: PASS (4 tests pass)

**Step 5: Commit**

```bash
git add backend/tests/test_analyst_agent.py
git commit -m "test(agents): add AnalystAgent tool registration test"
```

---

## Task 4: Create PubMed search tool with rate limiting

**Files:**
- Modify: `backend/src/agents/analyst.py`
- Modify: `backend/tests/test_analyst_agent.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_analyst_agent.py`:

```python
import httpx
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_pubmed_search_returns_articles() -> None:
    """Test _pubmed_search returns list of articles from PubMed API."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    # Mock httpx client response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "esearchresult": {
            "idlist": ["12345", "67890"],
            "count": "2"
        }
    }

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await agent._pubmed_search(query="cancer immunotherapy", max_results=10)

    assert result["count"] == 2
    assert len(result["pmids"]) == 2
    assert "12345" in result["pmids"]
    assert "67890" in result["pmids"]


@pytest.mark.asyncio
async def test_pubmed_search_handles_api_error() -> None:
    """Test _pubmed_search handles API errors gracefully."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    # Mock httpx to raise an error
    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.HTTPStatusError(
        "Server error", request=MagicMock(), response=MagicMock()
    )

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await agent._pubmed_search(query="test query")

    assert "error" in result
    assert result["pmids"] == []
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_analyst_agent.py::test_pubmed_search_returns_articles -v`
Expected: FAIL with "_pubmed_search not implemented"

**Step 3: Write minimal implementation**

Update `backend/src/agents/analyst.py`:

```python
"""AnalystAgent module for ARIA.

Provides scientific research capabilities using life sciences APIs
including PubMed, ClinicalTrials.gov, FDA, and ChEMBL.
"""

import logging
from typing import Any

import httpx

from src.agents.base import BaseAgent

logger = logging.getLogger(__name__)

# PubMed API endpoints
PUBMED_ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
PUBMED_EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


class AnalystAgent(BaseAgent):
    """Scientific research agent for life sciences queries.

    The Analyst agent searches scientific databases to provide
    domain expertise, literature reviews, and data extraction
    from biomedical APIs.
    """

    name = "Analyst"
    description = "Scientific research agent for life sciences queries"

    # Rate limiting: PubMed allows 3 requests/second without API key
    _pubmed_rate_limit = 3
    _pubmem_last_call_time = 0

    def __init__(self, llm_client: Any, user_id: str) -> None:
        """Initialize the Analyst agent.

        Args:
            llm_client: LLM client for reasoning and generation.
            user_id: ID of the user this agent is working for.
        """
        self._research_cache: dict[str, Any] = {}
        self._http_client: httpx.AsyncClient | None = None
        super().__init__(llm_client=llm_client, user_id=user_id)

    def _register_tools(self) -> dict[str, Any]:
        """Register Analyst agent's research tools.

        Returns:
            Dictionary mapping tool names to callable functions.
        """
        return {
            "pubmed_search": self._pubmed_search,
            "clinical_trials_search": self._clinical_trials_search,
            "fda_drug_search": self._fda_drug_search,
            "chembl_search": self._chembl_search,
        }

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client with timeout settings.

        Returns:
            Async HTTP client.
        """
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=30.0)
        return self._http_client

    async def _pubmed_search(
        self,
        query: str,
        max_results: int = 20,
        days_back: int | None = None,
    ) -> dict[str, Any]:
        """Search PubMed for articles matching the query.

        Args:
            query: Search query string.
            max_results: Maximum number of results to return.
            days_back: Optional filter to articles from last N days.

        Returns:
            Dictionary with count and list of PMIDs.
        """
        import time

        # Rate limiting
        current_time = time.time()
        time_since_last = current_time - self._pubmem_last_call_time
        min_interval = 1.0 / self._pubmed_rate_limit
        if time_since_last < min_interval:
            await asyncio.sleep(min_interval - time_since_last)

        # Check cache
        cache_key = f"pubmed:{query}:{max_results}:{days_back}"
        if cache_key in self._research_cache:
            logger.info(f"PubMed cache hit for query: {query}")
            return self._research_cache[cache_key]

        try:
            client = await self._get_http_client()

            # Build search parameters
            params: dict[str, Any] = {
                "db": "pubmed",
                "term": query,
                "retmode": "json",
                "retmax": max_results,
                "sort": "relevance",
            }

            if days_back:
                # Add date filter
                params["datetype"] = "edat"
                params["reldate"] = days_back

            response = await client.get(PUBMED_ESEARCH_URL, params=params)
            response.raise_for_status()

            data = response.json()
            search_result = data.get("esearchresult", {})

            result = {
                "query": query,
                "count": int(search_result.get("count", 0)),
                "pmids": search_result.get("idlist", []),
                "retmax": int(search_result.get("retmax", 0)),
            }

            # Cache result
            self._research_cache[cache_key] = result
            self._pubmem_last_call_time = time.time()

            logger.info(
                f"PubMed search found {result['count']} articles for: {query}",
                extra={"query": query, "count": result["count"]},
            )

            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"PubMed API error: {e}")
            return {"error": str(e), "pmids": [], "count": 0}
        except Exception as e:
            logger.error(f"PubMed search failed: {e}")
            return {"error": str(e), "pmids": [], "count": 0}

    async def execute(self, task: dict[str, Any]) -> Any:
        """Execute the analyst agent's primary task.

        Args:
            task: Task specification with parameters.

        Returns:
            AgentResult with success status and output data.
        """
        from src.agents.base import AgentResult

        return AgentResult(success=True, data={})
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_analyst_agent.py::test_pubmed_search_returns_articles tests/test_analyst_agent.py::test_pubmed_search_handles_api_error -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/analyst.py backend/tests/test_analyst_agent.py
git commit -m "feat(agents): implement PubMed search tool with rate limiting"
```

---

## Task 5: Create PubMed article details fetcher

**Files:**
- Modify: `backend/src/agents/analyst.py`
- Modify: `backend/tests/test_analyst_agent.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_analyst_agent.py`:

```python
@pytest.mark.asyncio
async def test_pubmed_fetch_details_returns_article_metadata() -> None:
    """Test _pubmed_fetch_details returns article metadata."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    # Mock httpx client response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "result": {
            "12345": {
                "title": "Test Article Title",
                "authors": [{"name": "Smith J"}],
                "pubdate": "2023 Jan",
                "source": "Nature",
            }
        }
    }

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await agent._pubmed_fetch_details(pmids=["12345"])

    assert len(result) == 1
    assert result["12345"]["title"] == "Test Article Title"
    assert result["12345"]["authors"][0]["name"] == "Smith J"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_analyst_agent.py::test_pubmed_fetch_details_returns_article_metadata -v`
Expected: FAIL with "_pubmed_fetch_details not implemented"

**Step 3: Write minimal implementation**

Add to `backend/src/agents/analyst.py`:

```python
    async def _pubmed_fetch_details(self, pmids: list[str]) -> dict[str, Any]:
        """Fetch detailed metadata for PubMed articles.

        Args:
            pmids: List of PubMed IDs to fetch details for.

        Returns:
            Dictionary mapping PMID to article metadata.
        """
        import time

        # Rate limiting
        current_time = time.time()
        time_since_last = current_time - self._pubmem_last_call_time
        min_interval = 1.0 / self._pubmed_rate_limit
        if time_since_last < min_interval:
            await asyncio.sleep(min_interval - time_since_last)

        if not pmids:
            return {}

        # Check cache for batch
        cache_key = f"pubmed_details:{','.join(sorted(pmids))}"
        if cache_key in self._research_cache:
            logger.info(f"PubMed details cache hit for {len(pmids)} PMIDs")
            return self._research_cache[cache_key]

        try:
            client = await self._get_http_client()

            params = {
                "db": "pubmed",
                "id": ",".join(pmids),
                "retmode": "json",
                "rettype": "abstract",
            }

            response = await client.get(PUBMED_ESUMMARY_URL, params=params)
            response.raise_for_status()

            data = response.json()
            result_data = data.get("result", {})

            # Remove the "uids" key which contains the list, not the details
            if "uids" in result_data:
                del result_data["uids"]

            self._research_cache[cache_key] = result_data
            self._pubmem_last_call_time = time.time()

            logger.info(f"Fetched details for {len(result_data)} articles")

            return result_data

        except httpx.HTTPStatusError as e:
            logger.error(f"PubMed details API error: {e}")
            return {}
        except Exception as e:
            logger.error(f"PubMed details fetch failed: {e}")
            return {}
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_analyst_agent.py::test_pubmed_fetch_details_returns_article_metadata -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/analyst.py backend/tests/test_analyst_agent.py
git commit -m "feat(agents): add PubMed article details fetcher"
```

---

## Task 6: Create ClinicalTrials.gov search tool

**Files:**
- Modify: `backend/src/agents/analyst.py`
- Modify: `backend/tests/test_analyst_agent.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_analyst_agent.py`:

```python
@pytest.mark.asyncio
async def test_clinical_trials_search_returns_studies() -> None:
    """Test _clinical_trials_search returns studies from ClinicalTrials.gov API."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    # Mock httpx client response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "studies": [
            {
                "protocolSection": {
                    "identificationModule": {"nctId": "NCT00000001"},
                    "statusModule": {"overallStatus": "Recruiting"},
                }
            },
            {
                "protocolSection": {
                    "identificationModule": {"nctId": "NCT00000002"},
                    "statusModule": {"overallStatus": "Completed"},
                }
            },
        ],
        "totalCount": 2,
    }

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await agent._clinical_trials_search(query="Alzheimer's disease", max_results=10)

    assert result["total_count"] == 2
    assert len(result["studies"]) == 2
    assert result["studies"][0]["nct_id"] == "NCT00000001"
    assert result["studies"][0]["status"] == "Recruiting"


@pytest.mark.asyncio
async def test_clinical_trials_search_handles_empty_results() -> None:
    """Test _clinical_trials_search handles empty results gracefully."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"studies": [], "totalCount": 0}

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await agent._clinical_trials_search(query="obscure condition xyz")

    assert result["total_count"] == 0
    assert result["studies"] == []
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_analyst_agent.py::test_clinical_trials_search_returns_studies -v`
Expected: FAIL with "_clinical_trials_search not implemented"

**Step 3: Write minimal implementation**

Update `backend/src/agents/analyst.py` with ClinicalTrials.gov constants and method:

```python
# ClinicalTrials.gov API endpoint
CLINICALTRIALS_API_URL = "https://clinicaltrials.gov/api/v2/studies"
```

Add method:

```python
    async def _clinical_trials_search(
        self,
        query: str,
        max_results: int = 20,
        status: str | None = None,
    ) -> dict[str, Any]:
        """Search ClinicalTrials.gov for studies matching the query.

        Args:
            query: Search query string.
            max_results: Maximum number of results to return.
            status: Optional filter by study status (e.g., "Recruiting", "Completed").

        Returns:
            Dictionary with total_count and list of studies.
        """
        # Check cache
        cache_key = f"clinicaltrials:{query}:{max_results}:{status}"
        if cache_key in self._research_cache:
            logger.info(f"ClinicalTrials cache hit for query: {query}")
            return self._research_cache[cache_key]

        try:
            client = await self._get_http_client()

            # Build parameters
            params: dict[str, Any] = {
                "query.term": query,
                "pageSize": max_results,
                "fields": [
                    "protocolSection.identificationModule.nctId",
                    "protocolSection.identificationModule.briefTitle",
                    "protocolSection.statusModule.overallStatus",
                    "protocolSection.statusModule.startDate",
                    "protocolSection.conditionsModule.conditions",
                    "protocolSection.contactsLocationsModule.contacts",
                ],
            }

            if status:
                params["filter.oversightStatus"] = status

            response = await client.get(CLINICALTRIALS_API_URL, params=params)
            response.raise_for_status()

            data = response.json()

            # Transform studies to a cleaner format
            studies = []
            for study in data.get("studies", []):
                proto = study.get("protocolSection", {})
                id_module = proto.get("identificationModule", {})
                status_module = proto.get("statusModule", {})
                conditions_module = proto.get("conditionsModule", {})

                studies.append({
                    "nct_id": id_module.get("nctId"),
                    "title": id_module.get("briefTitle"),
                    "status": status_module.get("overallStatus"),
                    "start_date": status_module.get("startDate"),
                    "conditions": conditions_module.get("conditions", []),
                })

            result = {
                "query": query,
                "total_count": data.get("totalCount", 0),
                "studies": studies,
            }

            # Cache result
            self._research_cache[cache_key] = result

            logger.info(
                f"ClinicalTrials search found {result['total_count']} studies for: {query}",
                extra={"query": query, "count": result["total_count"]},
            )

            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"ClinicalTrials API error: {e}")
            return {"error": str(e), "studies": [], "total_count": 0}
        except Exception as e:
            logger.error(f"ClinicalTrials search failed: {e}")
            return {"error": str(e), "studies": [], "total_count": 0}
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_analyst_agent.py::test_clinical_trials_search_returns_studies tests/test_analyst_agent.py::test_clinical_trials_search_handles_empty_results -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/analyst.py backend/tests/test_analyst_agent.py
git commit -m "feat(agents): implement ClinicalTrials.gov search tool"
```

---

## Task 7: Create FDA drug/device search tool

**Files:**
- Modify: `backend/src/agents/analyst.py`
- Modify: `backend/tests/test_analyst_agent.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_analyst_agent.py`:

```python
@pytest.mark.asyncio
async def test_fda_drug_search_returns_products() -> None:
    """Test _fda_drug_search returns drug products from OpenFDA API."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    # Mock httpx client response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "openfda": {
                    "brand_name": ["TestDrug"],
                    "generic_name": ["test ingredient"],
                    "manufacturer": ["Test Pharma Inc."],
                },
                "purpose": ["Treatment of test condition"],
            }
        ],
        "meta": {"total": 1},
    }

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await agent._fda_drug_search(drug_name="TestDrug", search_type="brand")

    assert result["total"] == 1
    assert len(result["products"]) == 1
    assert result["products"][0]["brand_name"] == "TestDrug"


@pytest.mark.asyncio
async def test_fda_drug_search_handles_device_search() -> None:
    """Test _fda_drug_search handles device searches."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "device_name": "TestDevice",
                "device_class": "2",
                "medical_specialty": "Cardiology",
            }
        ],
        "meta": {"total": 1},
    }

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await agent._fda_drug_search(drug_name="TestDevice", search_type="device")

    assert result["total"] == 1
    assert len(result["products"]) == 1
    assert result["products"][0]["device_name"] == "TestDevice"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_analyst_agent.py::test_fda_drug_search_returns_products -v`
Expected: FAIL with "_fda_drug_search not implemented"

**Step 3: Write minimal implementation**

Update `backend/src/agents/analyst.py` with FDA API constants and method:

```python
# OpenFDA API endpoints
FDA_DRUG_API_URL = "https://api.fda.gov/drug/label.json"
FDA_DEVICE_API_URL = "https://api.fda.gov/device/510k.json"
```

Add method:

```python
    async def _fda_drug_search(
        self,
        drug_name: str,
        search_type: str = "brand",
        max_results: int = 10,
    ) -> dict[str, Any]:
        """Search OpenFDA API for drug or device information.

        Args:
            drug_name: Name of the drug or device to search.
            search_type: Type of search - "brand", "generic", or "device".
            max_results: Maximum number of results to return.

        Returns:
            Dictionary with total count and list of products/devices.
        """
        # Check cache
        cache_key = f"fda:{drug_name}:{search_type}:{max_results}"
        if cache_key in self._research_cache:
            logger.info(f"FDA cache hit for: {drug_name}")
            return self._research_cache[cache_key]

        try:
            client = await self._get_http_client()

            # Determine API endpoint and search field
            if search_type == "device":
                url = FDA_DEVICE_API_URL
                search_field = "device_name"
            else:
                url = FDA_DRUG_API_URL
                search_field = (
                    "openfda.brand_name" if search_type == "brand"
                    else "openfda.generic_name"
                )

            # Build parameters
            params = {
                "search": f"{search_field}:{drug_name}",
                "limit": max_results,
            }

            response = await client.get(url, params=params)
            response.raise_for_status()

            data = response.json()

            # Extract results
            results = data.get("results", [])
            products = []

            if search_type == "device":
                for item in results:
                    products.append({
                        "device_name": item.get("device_name"),
                        "device_class": item.get("device_class"),
                        "medical_specialty": item.get("medical_specialty_description"),
                    })
            else:
                for item in results:
                    openfda = item.get("openfda", {})
                    products.append({
                        "brand_name": openfda.get("brand_name", [""])[0] if openfda.get("brand_name") else None,
                        "generic_name": openfda.get("generic_name", [""])[0] if openfda.get("generic_name") else None,
                        "manufacturer": openfda.get("manufacturer_name", [""])[0] if openfda.get("manufacturer_name") else None,
                        "purpose": item.get("purpose", []),
                    })

            result = {
                "query": drug_name,
                "search_type": search_type,
                "total": data.get("meta", {}).get("total", 0),
                "products": products,
            }

            # Cache result
            self._research_cache[cache_key] = result

            logger.info(
                f"FDA search found {result['total']} {search_type} results for: {drug_name}",
            )

            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"FDA API error: {e}")
            return {"error": str(e), "products": [], "total": 0}
        except Exception as e:
            logger.error(f"FDA search failed: {e}")
            return {"error": str(e), "products": [], "total": 0}
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_analyst_agent.py::test_fda_drug_search_returns_products tests/test_analyst_agent.py::test_fda_drug_search_handles_device_search -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/analyst.py backend/tests/test_analyst_agent.py
git commit -m "feat(agents): implement FDA drug/device search tool"
```

---

## Task 8: Create ChEMBL search tool

**Files:**
- Modify: `backend/src/agents/analyst.py`
- Modify: `backend/tests/test_analyst_agent.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_analyst_agent.py`:

```python
@pytest.mark.asyncio
async def test_chembl_search_returns_molecules() -> None:
    """Test _chembl_search returns molecules from ChEMBL API."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    # Mock httpx client response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "molecules": [
            {
                "molecule_chembl_id": "CHEMBL0001",
                "pref_name": "Test Molecule",
                "molecule_type": "Small molecule",
                "max_phase": 4,
                "therapeutic_area": "Oncology",
            }
        ],
        "page_meta": {"total_count": 1},
    }

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await agent._chembl_search(query="aspirin", max_results=10)

    assert result["total_count"] == 1
    assert len(result["molecules"]) == 1
    assert result["molecules"][0]["molecule_chembl_id"] == "CHEMBL0001"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_analyst_agent.py::test_chembl_search_returns_molecules -v`
Expected: FAIL with "_chembl_search not implemented"

**Step 3: Write minimal implementation**

Update `backend/src/agents/analyst.py` with ChEMBL API constants and method:

```python
# ChEMBL API endpoint
CHEMBL_API_URL = "https://www.ebi.ac.uk/chembl/api/data"
```

Add method:

```python
    async def _chembl_search(
        self,
        query: str,
        search_type: str = "molecule",
        max_results: int = 20,
    ) -> dict[str, Any]:
        """Search ChEMBL database for bioactive molecules.

        Args:
            query: Search query string (molecule name, target, etc.).
            search_type: Type of search - "molecule", "target", or "drug".
            max_results: Maximum number of results to return.

        Returns:
            Dictionary with total_count and list of molecules/targets.
        """
        # Check cache
        cache_key = f"chembl:{query}:{search_type}:{max_results}"
        if cache_key in self._research_cache:
            logger.info(f"ChEMBL cache hit for: {query}")
            return self._research_cache[cache_key]

        try:
            client = await self._get_http_client()

            # Determine endpoint
            if search_type == "target":
                endpoint = f"{CHEMBL_API_URL}/target"
                search_field = "target_chembl_id"
            elif search_type == "drug":
                endpoint = f"{CHEMBL_API_URL}/drug"
                search_field = "drug_chembl_id"
            else:  # molecule
                endpoint = f"{CHEMBL_API_URL}/molecule"
                search_field = "molecule_chembl_id"

            # Build parameters - JSON format
            params = {
                "format": "json",
                "q": query,
                "limit": max_results,
            }

            response = await client.get(endpoint, params=params)
            response.raise_for_status()

            data = response.json()

            # Extract results
            molecules = data.get("molecules", {})
            if isinstance(molecules, dict):
                molecule_list = molecules.get("molecule", [])
            else:
                molecule_list = molecules if isinstance(molecules, list) else []

            results = []
            for item in molecule_list[:max_results]:
                results.append({
                    "molecule_chembl_id": item.get("molecule_chembl_id"),
                    "pref_name": item.get("pref_name"),
                    "molecule_type": item.get("molecule_type"),
                    "max_phase": item.get("max_phase"),
                    "therapeutic_area": item.get("therapeutic_area"),
                })

            # Get total count from page_meta if available
            page_meta = data.get("page_meta", {})
            total_count = page_meta.get("total_count", len(results))

            result = {
                "query": query,
                "search_type": search_type,
                "total_count": total_count,
                "molecules": results,
            }

            # Cache result
            self._research_cache[cache_key] = result

            logger.info(
                f"ChEMBL search found {result['total_count']} molecules for: {query}",
            )

            return result

        except httpx.HTTPStatusError as e:
            logger.error(f"ChEMBL API error: {e}")
            return {"error": str(e), "molecules": [], "total_count": 0}
        except Exception as e:
            logger.error(f"ChEMBL search failed: {e}")
            return {"error": str(e), "molecules": [], "total_count": 0}
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_analyst_agent.py::test_chembl_search_returns_molecules -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/analyst.py backend/tests/test_analyst_agent.py
git commit -m "feat(agents): implement ChEMBL search tool"
```

---

## Task 9: Implement validate_input for research questions

**Files:**
- Modify: `backend/src/agents/analyst.py`
- Modify: `backend/tests/test_analyst_agent.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_analyst_agent.py`:

```python
def test_analyst_agent_validates_research_question() -> None:
    """Test validate_input requires 'query' field."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    # Valid input
    assert agent.validate_input({"query": "cancer immunotherapy"}) is True

    # Invalid inputs
    assert agent.validate_input({}) is False
    assert agent.validate_input({"other": "field"}) is False
    assert agent.validate_input({"depth": "deep"}) is False


def test_analyst_agent_validates_depth_level() -> None:
    """Test validate_input checks depth level if provided."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    # Valid depth levels
    assert agent.validate_input({"query": "test", "depth": "quick"}) is True
    assert agent.validate_input({"query": "test", "depth": "standard"}) is True
    assert agent.validate_input({"query": "test", "depth": "comprehensive"}) is True

    # Invalid depth level
    assert agent.validate_input({"query": "test", "depth": "invalid"}) is False
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_analyst_agent.py::test_analyst_agent_validates_research_question -v`
Expected: FAIL (validate_input returns True for any input by default)

**Step 3: Write minimal implementation**

Add to `backend/src/agents/analyst.py`:

```python
    def validate_input(self, task: dict[str, Any]) -> bool:
        """Validate research task input before execution.

        Args:
            task: Task specification to validate.

        Returns:
            True if valid, False otherwise.
        """
        # Require 'query' field with research question
        if "query" not in task:
            return False

        query = task["query"]
        if not query or not isinstance(query, str):
            return False

        # Validate depth level if provided
        if "depth" in task:
            valid_depths = {"quick", "standard", "comprehensive"}
            if task["depth"] not in valid_depths:
                return False

        return True
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_analyst_agent.py::test_analyst_agent_validates_research_question tests/test_analyst_agent.py::test_analyst_agent_validates_depth_level -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/analyst.py backend/tests/test_analyst_agent.py
git commit -m "feat(agents): add input validation for AnalystAgent"
```

---

## Task 10: Implement execute method with research report generation

**Files:**
- Modify: `backend/src/agents/analyst.py`
- Modify: `backend/tests/test_analyst_agent.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_analyst_agent.py`:

```python
@pytest.mark.asyncio
async def test_analyst_execute_generates_research_report() -> None:
    """Test execute generates structured research report."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    # Mock the tools
    agent._pubmed_search = AsyncMock(return_value={
        "count": 2,
        "pmids": ["12345", "67890"],
    })
    agent._pubmed_fetch_details = AsyncMock(return_value={
        "12345": {"title": "Article 1"},
        "67890": {"title": "Article 2"},
    })
    agent._clinical_trials_search = AsyncMock(return_value={
        "total_count": 1,
        "studies": [{"nct_id": "NCT001", "status": "Recruiting"}],
    })
    agent._fda_drug_search = AsyncMock(return_value={
        "total": 1,
        "products": [{"brand_name": "TestDrug"}],
    })
    agent._chembl_search = AsyncMock(return_value={
        "total_count": 1,
        "molecules": [{"molecule_chembl_id": "CHEMBL001"}],
    })

    task = {
        "query": "cancer immunotherapy",
        "depth": "standard",
    }

    result = await agent.execute(task)

    assert result.success is True
    assert "query" in result.data
    assert result.data["query"] == "cancer immunotherapy"
    assert "pubmed_articles" in result.data
    assert "clinical_trials" in result.data
    assert "fda_products" in result.data
    assert "chembl_molecules" in result.data
    assert "timestamp" in result.data


@pytest.mark.asyncio
async def test_analyst_execute_with_quick_depth_skips_databases() -> None:
    """Test execute with 'quick' depth only searches PubMed."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    agent._pubmed_search = AsyncMock(return_value={"count": 1, "pmids": ["123"]})
    agent._pubmed_fetch_details = AsyncMock(return_value={"123": {"title": "Test"}})
    agent._clinical_trials_search = AsyncMock()
    agent._fda_drug_search = AsyncMock()
    agent._chembl_search = AsyncMock()

    task = {"query": "test query", "depth": "quick"}

    result = await agent.execute(task)

    assert result.success is True
    agent._pubmed_search.assert_called_once()
    # Other tools should not be called for quick depth
    agent._clinical_trials_search.assert_not_awaited()
    agent._fda_drug_search.assert_not_awaited()
    agent._chembl_search.assert_not_awaited()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_analyst_agent.py::test_analyst_execute_generates_research_report -v`
Expected: FAIL (execute returns empty dict)

**Step 3: Write minimal implementation**

Replace the execute method in `backend/src/agents/analyst.py`:

```python
    async def execute(self, task: dict[str, Any]) -> Any:
        """Execute the analyst agent's primary research task.

        Args:
            task: Task specification with:
                - query: Research question (required)
                - depth: Research depth - "quick", "standard", or "comprehensive" (optional)

        Returns:
            AgentResult with structured research report.
        """
        from src.agents.base import AgentResult
        from datetime import datetime

        query = task["query"]
        depth = task.get("depth", "standard")

        report: dict[str, Any] = {
            "query": query,
            "depth": depth,
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Always search PubMed
        pubmed_result = await self._pubmed_search(query=query, max_results=20)
        report["pubmed_search"] = {
            "count": pubmed_result.get("count", 0),
            "pmids": pubmed_result.get("pmids", []),
        }

        # Fetch article details
        if pubmed_result.get("pmids"):
            details = await self._pubmed_fetch_details(pubmed_result["pmids"])
            report["pubmed_articles"] = details
        else:
            report["pubmed_articles"] = {}

        # Search other databases based on depth
        if depth in ("standard", "comprehensive"):
            # ClinicalTrials.gov
            trials_result = await self._clinical_trials_search(query=query)
            report["clinical_trials"] = trials_result

            # FDA
            fda_result = await self._fda_drug_search(drug_name=query, search_type="brand")
            report["fda_products"] = fda_result

        if depth == "comprehensive":
            # ChEMBL for molecule data
            chembl_result = await self._chembl_search(query=query)
            report["chembl_molecules"] = chembl_result

        return AgentResult(
            success=True,
            data=report,
        )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_analyst_agent.py::test_analyst_execute_generates_research_report tests/test_analyst_agent.py::test_analyst_execute_with_quick_depth_skips_databases -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/analyst.py backend/tests/test_analyst_agent.py
git commit -m "feat(agents): implement execute method with research report generation"
```

---

## Task 11: Add format_output for structured research reports

**Files:**
- Modify: `backend/src/agents/analyst.py`
- Modify: `backend/tests/test_analyst_agent.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_analyst_agent.py`:

```python
def test_analyst_format_output_adds_summary() -> None:
    """Test format_output adds summary statistics to report."""
    from src.agents.analyst import AnalystAgent

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    data = {
        "query": "test query",
        "pubmed_search": {"count": 10, "pmids": ["1", "2"]},
        "pubmed_articles": {"1": {"title": "A1"}, "2": {"title": "A2"}},
        "clinical_trials": {"total_count": 5, "studies": [{"nct_id": "NCT1"}]},
        "fda_products": {"total": 3, "products": [{"brand_name": "D1"}]},
        "chembl_molecules": {"total_count": 2, "molecules": [{"molecule_chembl_id": "C1"}]},
    }

    formatted = agent.format_output(data)

    assert "summary" in formatted
    assert formatted["summary"]["total_sources"] == 4
    assert formatted["summary"]["pubmed_article_count"] == 10
    assert formatted["summary"]["clinical_trials_count"] == 5
    assert formatted["summary"]["fda_products_count"] == 3
    assert formatted["summary"]["chembl_molecules_count"] == 2
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_analyst_agent.py::test_analyst_format_output_adds_summary -v`
Expected: FAIL (format_output returns data unchanged)

**Step 3: Write minimal implementation**

Add to `backend/src/agents/analyst.py`:

```python
    def format_output(self, data: Any) -> Any:
        """Format output data with summary statistics.

        Args:
            data: Raw research report data.

        Returns:
            Formatted research report with summary section.
        """
        if not isinstance(data, dict):
            return data

        summary = {
            "total_sources": 0,
            "pubmed_article_count": 0,
            "clinical_trials_count": 0,
            "fda_products_count": 0,
            "chembl_molecules_count": 0,
        }

        # Count PubMed articles
        if "pubmed_search" in data:
            summary["pubmed_article_count"] = data["pubmed_search"].get("count", 0)
            summary["total_sources"] += 1

        # Count clinical trials
        if "clinical_trials" in data:
            summary["clinical_trials_count"] = data["clinical_trials"].get("total_count", 0)
            summary["total_sources"] += 1

        # Count FDA products
        if "fda_products" in data:
            summary["fda_products_count"] = data["fda_products"].get("total", 0)
            summary["total_sources"] += 1

        # Count ChEMBL molecules
        if "chembl_molecules" in data:
            summary["chembl_molecules_count"] = data["chembl_molecules"].get("total_count", 0)
            summary["total_sources"] += 1

        # Add summary to data
        data["summary"] = summary

        return data
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_analyst_agent.py::test_analyst_format_output_adds_summary -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/analyst.py backend/tests/test_analyst_agent.py
git commit -m "feat(agents): add format_output with summary statistics"
```

---

## Task 12: Update agents module __init__ to export AnalystAgent

**Files:**
- Modify: `backend/src/agents/__init__.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_analyst_agent.py`:

```python
def test_analyst_agent_exported_from_agents_module() -> None:
    """Test AnalystAgent is exported from agents module."""
    from src.agents import AnalystAgent

    assert AnalystAgent.name == "Analyst"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_analyst_agent.py::test_analyst_agent_exported_from_agents_module -v`
Expected: FAIL with "ImportError: cannot import name 'AnalystAgent'"

**Step 3: Write minimal implementation**

Update `backend/src/agents/__init__.py`:

```python
"""ARIA specialized agents module.

This module provides the base agent class and all specialized agents
for ARIA's task execution system.
"""

from src.agents.agent import AnalystAgent
from src.agents.base import AgentResult, AgentStatus, BaseAgent
from src.agents.hunter import HunterAgent

__all__ = [
    "AgentResult",
    "AgentStatus",
    "BaseAgent",
    "HunterAgent",
    "AnalystAgent",
]
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_analyst_agent.py::test_analyst_agent_exported_from_agents_module -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/agents/__init__.py backend/tests/test_analyst_agent.py
git commit -m "feat(agents): export AnalystAgent from agents module"
```

---

## Task 13: Add integration test for full agent lifecycle

**Files:**
- Modify: `backend/tests/test_analyst_agent.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_analyst_agent.py`:

```python
@pytest.mark.asyncio
async def test_full_analyst_agent_lifecycle_with_real_execution() -> None:
    """Integration test demonstrating complete Analyst agent lifecycle."""
    from src.agents import AnalystAgent
    from src.agents.base import AgentStatus

    mock_llm = MagicMock()
    agent = AnalystAgent(llm_client=mock_llm, user_id="user-123")

    # Mock tools
    agent._pubmed_search = AsyncMock(return_value={
        "count": 1,
        "pmids": ["12345"],
    })
    agent._pubmed_fetch_details = AsyncMock(return_value={
        "12345": {
            "title": "Advances in Cancer Immunotherapy",
            "authors": [{"name": "Smith J"}],
            "pubdate": "2023 Jan",
        }
    })
    agent._clinical_trials_search = AsyncMock(return_value={
        "total_count": 1,
        "studies": [{"nct_id": "NCT001", "status": "Recruiting"}],
    })
    agent._fda_drug_search = AsyncMock(return_value={"total": 0, "products": []})
    agent._chembl_search = AsyncMock(return_value={"total_count": 0, "molecules": []})

    # Initial state
    assert agent.is_idle
    assert agent.total_tokens_used == 0

    # Run the agent
    task = {
        "query": "cancer immunotherapy",
        "depth": "standard",
    }
    result = await agent.run(task)

    # Verify successful execution
    assert result.success is True
    assert agent.is_complete
    assert result.execution_time_ms >= 0

    # Verify output structure
    assert "summary" in result.data
    assert result.data["query"] == "cancer immunotherapy"
    assert result.data["summary"]["pubmed_article_count"] == 1
    assert result.data["summary"]["clinical_trials_count"] == 1

    # Verify tools were called
    agent._pubmed_search.assert_called_once()
    agent._pubmed_fetch_details.assert_called_once_with(["12345"])

    # Test validation failure
    agent.status = AgentStatus.IDLE
    invalid_result = await agent.run({"no_query": "field"})
    assert invalid_result.success is False
    assert "validation" in (invalid_result.error or "").lower()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_analyst_agent.py::test_full_analyst_agent_lifecycle_with_real_execution -v`
Expected: PASS (all previous implementations should work)

**Step 3: No implementation needed**

This test verifies the complete integration of all previous tasks.

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_analyst_agent.py::test_full_analyst_agent_lifecycle_with_real_execution -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/tests/test_analyst_agent.py
git commit -m "test(agents): add integration test for AnalystAgent lifecycle"
```

---

## Task 14: Fix import issue and add asyncio import

**Files:**
- Modify: `backend/src/agents/analyst.py`

**Step 1: Write the failing test**

Run: `cd backend && python -c "from src.agents import AnalystAgent; print('Import OK')"`
Expected: Should fail with asyncio not imported

**Step 2: Run test to verify it fails**

Run: `cd backend && python -c "from src.agents import AnalystAgent; print('Import OK')"`
Expected: FAIL with NameError for asyncio

**Step 3: Write minimal implementation**

Update imports in `backend/src/agents/analyst.py`:

```python
"""AnalystAgent module for ARIA.

Provides scientific research capabilities using life sciences APIs
including PubMed, ClinicalTrials.gov, FDA, and ChEMBL.
"""

import asyncio
import logging
from typing import Any

import httpx

from src.agents.base import BaseAgent

logger = logging.getLogger(__name__)
```

Also fix the __init__.py import (should be analyst, not agent):

```python
"""ARIA specialized agents module.

This module provides the base agent class and all specialized agents
for ARIA's task execution system.
"""

from src.agents.analyst import AnalystAgent
from src.agents.base import AgentResult, AgentStatus, BaseAgent
from src.agents.hunter import HunterAgent

__all__ = [
    "AgentResult",
    "AgentStatus",
    "BaseAgent",
    "HunterAgent",
    "AnalystAgent",
]
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -c "from src.agents import AnalystAgent; print('Import OK')"`
Expected: PASS with "Import OK"

**Step 5: Commit**

```bash
git add backend/src/agents/__init__.py backend/src/agents/analyst.py
git commit -m "fix(agents): add missing asyncio import and fix import path"
```

---

## Task 15: Run full test suite and quality checks

**Files:**
- All test files

**Step 1: Run all AnalystAgent tests**

Run: `cd backend && pytest tests/test_analyst_agent.py -v`
Expected: All tests PASS

**Step 2: Run all agent tests**

Run: `cd backend && pytest tests/test_base_agent.py tests/test_hunter_agent.py tests/test_analyst_agent.py -v`
Expected: All tests PASS

**Step 3: Run type checking**

Run: `cd backend && mypy src/agents/analyst.py --strict`
Expected: May have some type issues to fix

**Step 4: Fix type issues**

Update type annotations as needed in `backend/src/agents/analyst.py` to pass mypy strict mode.

**Step 5: Run linting**

Run: `cd backend && ruff check src/agents/analyst.py`
Expected: No warnings

**Step 6: Format check**

Run: `cd backend && ruff format src/agents/analyst.py --check`
Expected: No changes needed

**Step 7: Final commit**

```bash
git add backend/src/agents/analyst.py backend/tests/test_analyst_agent.py backend/src/agents/__init__.py
git commit -m "feat(agents): complete AnalystAgent implementation with full test coverage"
```

---

## Task 16: Documentation and cleanup

**Files:**
- No files to create, just verification

**Step 1: Verify all acceptance criteria from US-304**

Check off each item:
- [x] `backend/src/agents/analyst.py` extends BaseAgent
- [x] Tools: pubmed_search, clinical_trials_search, fda_drug_search, chembl_search
- [x] Accepts: research question (query), depth level
- [x] Returns: structured research report with citations
- [x] Handles API rate limits gracefully
- [x] Caches research results
- [x] Unit tests with mocked APIs

**Step 2: Run complete test suite**

Run: `cd backend && pytest tests/ -v --tb=short`
Expected: All tests pass including new AnalystAgent tests

**Step 3: Final quality gate**

Run all quality checks:
```bash
cd backend
pytest tests/ -v
mypy src/agents/ --strict
ruff check src/agents/
ruff format src/agents/ --check
```

**Step 4: Final commit if needed**

```bash
git add backend/
git commit -m "feat(agents): US-304 Analyst Agent implementation complete"
```

---

## Summary

This plan implements the Analyst Agent (US-304) from Phase 3 of the ARIA PRD. The agent provides:

1. **Four Scientific API Tools:**
   - PubMed search with E-utilities
   - ClinicalTrials.gov v2 API
   - OpenFDA drug/device database
   - ChEMBL bioactive molecule database

2. **Rate Limiting & Caching:**
   - PubMed: 3 req/sec rate limiting
   - Result caching for all tools

3. **Structured Output:**
   - Research reports with summary statistics
   - Citation-ready article metadata
   - Depth levels: quick, standard, comprehensive

4. **Comprehensive Testing:**
   - 15+ unit tests with mocked APIs
   - Integration test for full lifecycle
   - Validation and error handling tests

The implementation follows TDD principles, includes proper type hints, logging, and error handling for production use.
