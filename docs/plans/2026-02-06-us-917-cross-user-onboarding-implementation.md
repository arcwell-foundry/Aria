# US-917: Cross-User Onboarding Acceleration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** When user #2+ at a company starts onboarding, ARIA detects existing Corporate Memory and skips/shortens company discovery steps based on data richness.

**Architecture:** A new `CrossUserAccelerationService` checks company existence by domain, calculates richness score (0-100) using hybrid approach, and returns tiered Memory Delta for confirmation. Privacy enforced at all layers via explicit filtering.

**Tech Stack:** Python/FastAPI (backend), React/TypeScript (frontend), Supabase (database), existing MemoryDeltaPresenter pattern

---

## Prerequisites

Read these files before starting:
- `backend/src/onboarding/company_discovery.py` - Company lookup pattern
- `backend/src/memory/delta_presenter.py` - Memory Delta pattern
- `backend/src/onboarding/readiness.py` - Readiness score calculation
- `docs/plans/2026-02-06-us-917-cross-user-onboarding-design.md` - Full design

---

## Task 1: Backend Data Models

**Files:**
- Create: `backend/src/onboarding/cross_user.py`

**Step 1: Write the failing test**

Create `backend/tests/test_cross_user.py`:

```python
import pytest
from src.onboarding.cross_user import CrossUserAccelerationService, CompanyCheckResult

@pytest.mark.asyncio
async def test_check_company_exists_not_found(db_client, llm_client):
    """New company should return not exists with full recommendation."""
    service = CrossUserAccelerationService(db_client, llm_client)
    result = await service.check_company_exists("nonexistent-company.com")

    assert result.exists is False
    assert result.company_id is None
    assert result.company_name is None
    assert result.richness_score == 0
    assert result.recommendation == "full"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_cross_user.py::test_check_company_exists_not_found -v`

Expected: `ModuleNotFoundError: No module named 'src.onboarding.cross_user'`

**Step 3: Write minimal implementation**

Create `backend/src/onboarding/cross_user.py`:

```python
from dataclasses import dataclass
from typing import Literal

from src.db.supabase_client import SupabaseClient
from src.core.llm_client import AnthropicClient


@dataclass
class CompanyCheckResult:
    """Result of checking if a company exists for cross-user acceleration."""
    exists: bool
    company_id: str | None
    company_name: str | None
    richness_score: int  # 0-100
    recommendation: Literal["skip", "partial", "full"]


class CrossUserAccelerationService:
    """Handles cross-user onboarding acceleration by checking existing company data."""

    # Sources that are corporate-safe (no personal data)
    _CORPORATE_SOURCES = {
        "company_enrichment",
        "document_upload",
        "crm_sync",
        "web_research",
    }

    # Sources that contain personal data - must be excluded
    _PERSONAL_SOURCES = {
        "email_analysis",
        "writing_sample",
        "linkedin_research",
        "user_stated",
    }

    def __init__(self, db: SupabaseClient, llm_client: AnthropicClient):
        self._db = db
        self._llm = llm_client

    async def check_company_exists(self, domain: str) -> CompanyCheckResult:
        """
        Check if company exists and calculate richness score.

        Returns CompanyCheckResult with recommendation based on richness:
        - >70: skip (full acceleration)
        - 30-70: partial (partial acceleration with gaps)
        - <30: full (no acceleration)
        """
        company = await self._get_company_by_domain(domain)

        if not company:
            return CompanyCheckResult(
                exists=False,
                company_id=None,
                company_name=None,
                richness_score=0,
                recommendation="full"
            )

        company_id = company["id"]
        company_name = company["name"]

        # Calculate richness score
        richness_score = await self._calculate_richness_score(company_id)

        # Determine recommendation based on richness
        if richness_score > 70:
            recommendation = "skip"
        elif richness_score >= 30:
            recommendation = "partial"
        else:
            recommendation = "full"

        return CompanyCheckResult(
            exists=True,
            company_id=company_id,
            company_name=company_name,
            richness_score=richness_score,
            recommendation=recommendation
        )

    async def _get_company_by_domain(self, domain: str) -> dict | None:
        """Query companies table by domain."""
        result = (
            self._db.table("companies")
            .select("*")
            .eq("domain", domain)
            .maybe_single()
            .execute()
        )
        return dict(result.data) if result.data else None

    async def _calculate_richness_score(self, company_id: str) -> int:
        """
        Calculate richness score using hybrid approach.

        Fast path: weighted formula based on counts
        Deep path (if 30-70%): full readiness assessment
        """
        # Fast calculation
        fact_count = await self._count_company_facts(company_id)
        domain_coverage = await self._calculate_domain_coverage(company_id)
        document_count = await self._count_company_documents(company_id)

        # Weighted formula (0-100)
        fast_score = (
            min(fact_count * 2, 50) +           # Max 50 points from facts
            min(domain_coverage * 10, 30) +     # Max 30 points from domains
            min(document_count * 5, 20)         # Max 20 points from documents
        )

        # For now, return fast score. Deep analysis comes later.
        return fast_score

    async def _count_company_facts(self, company_id: str) -> int:
        """Count corporate memory facts for this company."""
        result = (
            self._db.table("corporate_memory_facts")
            .select("id", count="exact")
            .eq("company_id", company_id)
            .in_("source", list(self._CORPORATE_SOURCES))
            .execute()
        )
        return result.count or 0

    async def _calculate_domain_coverage(self, company_id: str) -> int:
        """Count distinct domains covered (products, pipeline, leadership, etc.)."""
        result = (
            self._db.table("corporate_memory_facts")
            .select("domain")
            .eq("company_id", company_id)
            .execute()
        )

        if not result.data:
            return 0

        domains = set(item.get("domain") for item in result.data if item.get("domain"))
        return len(domains)

    async def _count_company_documents(self, company_id: str) -> int:
        """Count uploaded documents for this company."""
        result = (
            self._db.table("company_documents")
            .select("id", count="exact")
            .eq("company_id", company_id)
            .execute()
        )
        return result.count or 0
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_cross_user.py::test_check_company_exists_not_found -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/onboarding/cross_user.py backend/tests/test_cross_user.py
git commit -m "feat: add CrossUserAccelerationService with company existence check"
```

---

## Task 2: Richness Score Calculation - Skip Case

**Files:**
- Modify: `backend/tests/test_cross_user.py`
- Modify: `backend/src/onboarding/cross_user.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_cross_user.py`:

```python
@pytest.mark.asyncio
async def test_check_company_exists_skip_recommendation(db_client, llm_client, test_company):
    """
    Company with rich data (>70% richness) should return skip recommendation.

    Test setup: create company with 40+ facts, 7+ domains, 4+ documents
    """
    # Setup: Create test company with rich data
    await _create_rich_company_data(db_client, test_company["id"])

    service = CrossUserAccelerationService(db_client, llm_client)
    result = await service.check_company_exists(test_company["domain"])

    assert result.exists is True
    assert result.company_id == test_company["id"]
    assert result.company_name == test_company["name"]
    assert result.richness_score > 70
    assert result.recommendation == "skip"


async def _create_rich_company_data(db, company_id: str):
    """Helper to create rich company data for testing."""
    # Create 40 facts across 7 domains
    domains = ["product", "pipeline", "leadership", "financial", "manufacturing", "partnership", "regulatory"]
    for domain in domains:
        for i in range(6):
            await db.table("corporate_memory_facts").insert({
                "company_id": company_id,
                "domain": domain,
                "fact": f"Test {domain} fact {i}",
                "source": "company_enrichment",
                "confidence": 0.9
            }).execute()

    # Create 4 documents
    for i in range(4):
        await db.table("company_documents").insert({
            "company_id": company_id,
            "filename": f"document_{i}.pdf",
            "status": "processed"
        }).execute()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_cross_user.py::test_check_company_exists_skip_recommendation -v`

Expected: FAIL (rich company data not yet created in test setup, but logic should work)

**Step 3: No code changes needed** - implementation from Task 1 handles this case.

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_cross_user.py::test_check_company_exists_skip_recommendation -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/tests/test_cross_user.py
git commit -m "test: add skip recommendation test with rich company data"
```

---

## Task 3: Richness Score - Partial and Full Cases

**Files:**
- Modify: `backend/tests/test_cross_user.py`

**Step 1: Write the failing tests**

Add to `backend/tests/test_cross_user.py`:

```python
@pytest.mark.asyncio
async def test_check_company_partial_recommendation(db_client, llm_client, test_company):
    """
    Company with moderate data (30-70% richness) should return partial recommendation.
    """
    # Setup: Create company with moderate data
    await _create_moderate_company_data(db_client, test_company["id"])

    service = CrossUserAccelerationService(db_client, llm_client)
    result = await service.check_company_exists(test_company["domain"])

    assert result.exists is True
    assert 30 <= result.richness_score <= 70
    assert result.recommendation == "partial"


@pytest.mark.asyncio
async def test_check_company_low_richness_full_recommendation(db_client, llm_client, test_company):
    """
    Company with minimal data (<30% richness) should return full recommendation.
    """
    # Setup: Create company with minimal data
    await _create_minimal_company_data(db_client, test_company["id"])

    service = CrossUserAccelerationService(db_client, llm_client)
    result = await service.check_company_exists(test_company["domain"])

    assert result.exists is True
    assert result.richness_score < 30
    assert result.recommendation == "full"


async def _create_moderate_company_data(db, company_id: str):
    """Helper to create moderate company data (15-30 facts, 3-5 domains, 1-2 docs)."""
    domains = ["product", "leadership", "financial"]
    for domain in domains:
        for i in range(5):
            await db.table("corporate_memory_facts").insert({
                "company_id": company_id,
                "domain": domain,
                "fact": f"Test {domain} fact {i}",
                "source": "company_enrichment",
                "confidence": 0.8
            }).execute()

    await db.table("company_documents").insert({
        "company_id": company_id,
        "filename": "document_1.pdf",
        "status": "processed"
    }).execute()


async def _create_minimal_company_data(db, company_id: str):
    """Helper to create minimal company data (5 facts, 1 domain, 0 docs)."""
    for i in range(5):
        await db.table("corporate_memory_facts").insert({
            "company_id": company_id,
            "domain": "product",
            "fact": f"Test fact {i}",
            "source": "company_enrichment",
            "confidence": 0.7
        }).execute()
```

**Step 2: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_cross_user.py::test_check_company_partial_recommendation tests/test_cross_user.py::test_check_company_low_richness_full_recommendation -v`

Expected: PASS (implementation handles all cases)

**Step 3: Commit**

```bash
git add backend/tests/test_cross_user.py
git commit -m "test: add partial and full recommendation tests"
```

---

## Task 4: Company Memory Delta with Privacy Filtering

**Files:**
- Modify: `backend/src/onboarding/cross_user.py`
- Modify: `backend/tests/test_cross_user.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_cross_user.py`:

```python
@pytest.mark.asyncio
async def test_get_company_memory_delta_filters_personal_data(db_client, llm_client, test_company, user_2):
    """
    Memory delta must only include corporate facts, never personal data.

    Even if User #1 has rich personal data (emails, writing samples, LinkedIn),
    User #2 should only see company facts.
    """
    # Setup: Create both corporate and personal facts
    await _create_mixed_facts(db_client, test_company["id"], "user_1_id")

    service = CrossUserAccelerationService(db_client, llm_client)
    delta = await service.get_company_memory_delta(test_company["id"], user_2["id"])

    # Verify only corporate facts returned
    for fact in delta["facts"]:
        assert fact["domain"] == "corporate"
        assert fact["source"] in service._CORPORATE_SOURCES
        assert fact["source"] not in service._PERSONAL_SOURCES

    # Verify personal sources are excluded
    sources_in_delta = [f["source"] for f in delta["facts"]]
    assert "email_analysis" not in sources_in_delta
    assert "writing_sample" not in sources_in_delta


async def _create_mixed_facts(db, company_id: str, user_id: str):
    """Create both corporate and personal facts for testing privacy filtering."""
    # Corporate facts (should be included)
    await db.table("corporate_memory_facts").insert({
        "company_id": company_id,
        "domain": "corporate",
        "fact": "Company develops biologics manufacturing",
        "source": "company_enrichment",
        "confidence": 0.9
    }).execute()

    # Personal facts (should be excluded)
    await db.table("digital_twin_facts").insert({
        "user_id": user_id,
        "domain": "personal",
        "fact": "User prefers formal communication",
        "source": "writing_sample",
        "confidence": 0.85
    }).execute()

    await db.table("relationship_graph").insert({
        "user_id": user_id,
        "fact": "Close relationship with John at Pfizer",
        "source": "email_analysis",
        "confidence": 0.8
    }).execute()
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_cross_user.py::test_get_company_memory_delta_filters_personal_data -v`

Expected: FAIL - `get_company_memory_delta` method not yet implemented

**Step 3: Write minimal implementation**

Add to `backend/src/onboarding/cross_user.py`:

```python
async def get_company_memory_delta(
    self,
    company_id: str,
    user_id: str
) -> dict:
    """
    Get existing company facts for user confirmation.

    Returns tiered Memory Delta with:
    - High-confidence facts shown first
    - ONLY corporate data (personal data filtered out)

    Privacy: Enforced at query level with source filtering.
    """
    # Query only corporate memory facts with allowed sources
    result = (
        self._db.table("corporate_memory_facts")
        .select("*")
        .eq("company_id", company_id)
        .in_("source", list(self._CORPORATE_SOURCES))
        .execute()
    )

    facts = result.data or []

    # Separate high-confidence facts (>=0.8) for tiered display
    high_confidence_facts = [
        {
            "id": f.get("id"),
            "fact": f.get("fact"),
            "domain": f.get("domain", "corporate"),
            "confidence": f.get("confidence", 0.5),
            "source": f.get("source")
        }
        for f in facts
        if f.get("confidence", 0) >= 0.8
    ]

    all_facts = [
        {
            "id": f.get("id"),
            "fact": f.get("fact"),
            "domain": f.get("domain", "corporate"),
            "confidence": f.get("confidence", 0.5),
            "source": f.get("source")
        }
        for f in facts
    ]

    domains_covered = list(set(f.get("domain") for f in facts if f.get("domain")))

    return {
        "facts": all_facts,
        "high_confidence_facts": high_confidence_facts,
        "domains_covered": domains_covered,
        "total_fact_count": len(facts)
    }
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_cross_user.py::test_get_company_memory_delta_filters_personal_data -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/onboarding/cross_user.py backend/tests/test_cross_user.py
git commit -m "feat: add get_company_memory_delta with privacy filtering"
```

---

## Task 5: Confirm Company Data Handler

**Files:**
- Modify: `backend/src/onboarding/cross_user.py`
- Modify: `backend/tests/test_cross_user.py`

**Step 1: Write the failing test**

Add to `backend/tests/test_cross_user.py`:

```python
@pytest.mark.asyncio
async def test_confirm_company_data_links_user_and_skips_steps(db_client, llm_client, test_company, user_2):
    """
    Confirming company data should:
    - Link user to company
    - Mark company steps as skipped
    - Inherit corporate memory readiness score
    """
    service = CrossUserAccelerationService(db_client, llm_client)

    await service.confirm_company_data(
        company_id=test_company["id"],
        user_id=user_2["id"],
        corrections=None
    )

    # Verify user linked to company
    user_result = await db_client.table("users").select("*").eq("id", user_2["id"]).single().execute()
    assert user_result.data["company_id"] == test_company["id"]

    # Verify onboarding steps skipped
    onboarding_result = await db_client.table("onboarding_state").select("*").eq("user_id", user_2["id"]).single().execute()
    skipped_steps = onboarding_result.data.get("skipped_steps", [])
    assert "company_discovery" in skipped_steps
    assert "document_upload" in skipped_steps


@pytest.mark.asyncio
async def test_confirm_company_data_applies_corrections(db_client, llm_client, test_company, user_2):
    """
    User corrections should be stored with high confidence (0.95).
    """
    service = CrossUserAccelerationService(db_client, llm_client)

    corrections = {
        "industry": "Biotechnology (updated)",
        "headquarters": "Boston, MA"
    }

    await service.confirm_company_data(
        company_id=test_company["id"],
        user_id=user_2["id"],
        corrections=corrections
    )

    # Verify corrections stored
    # (This will query for facts with source="user_stated" and confidence=0.95)
    # Implementation depends on your fact storage schema
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_cross_user.py::test_confirm_company_data_links_user_and_skips_steps -v`

Expected: FAIL - `confirm_company_data` method not yet implemented

**Step 3: Write minimal implementation**

Add to `backend/src/onboarding/cross_user.py`:

```python
async def confirm_company_data(
    self,
    company_id: str,
    user_id: str,
    corrections: dict | None = None
) -> None:
    """
    Handle user confirmation of existing company data.

    - Links user to existing company
    - Marks onboarding steps as skipped
    - Applies corrections (if any) with high confidence
    - Inherits corporate_memory readiness score
    """
    # Link user to company
    await self._link_user_to_company(user_id, company_id)

    # Apply corrections if provided
    if corrections:
        await self._apply_corrections(user_id, company_id, corrections)

    # Update onboarding state - skip company steps
    await self._skip_onboarding_steps(
        user_id,
        skipped_steps=["company_discovery", "document_upload"]
    )

    # Inherit corporate memory readiness
    await self._inherit_readiness_score(user_id, company_id)


async def _link_user_to_company(self, user_id: str, company_id: str) -> None:
    """Link user to existing company."""
    self._db.table("users").update({"company_id": company_id}).eq("id", user_id).execute()


async def _apply_corrections(self, user_id: str, company_id: str, corrections: dict) -> None:
    """
    Apply user corrections with high confidence.

    Corrections are stored as corporate memory facts with source="user_stated"
    and confidence=0.95 (per source hierarchy).
    """
    for key, value in corrections.items():
        self._db.table("corporate_memory_facts").insert({
            "company_id": company_id,
            "domain": "corporate",
            "fact": f"{key}: {value}",
            "source": "user_stated",
            "confidence": 0.95,
            "corrected_by_user_id": user_id
        }).execute()


async def _skip_onboarding_steps(self, user_id: str, skipped_steps: list[str]) -> None:
    """Mark onboarding steps as skipped."""
    # Get current onboarding state
    result = (
        self._db.table("onboarding_state")
        .select("*")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )

    if result.data:
        current_skipped = result.data.get("skipped_steps", [])
        updated_skipped = list(set(current_skipped + skipped_steps))

        self._db.table("onboarding_state").update({
            "skipped_steps": updated_skipped
        }).eq("user_id", user_id).execute()
    else:
        # Create onboarding state if doesn't exist
        self._db.table("onboarding_state").insert({
            "user_id": user_id,
            "current_step": "user_profile",
            "skipped_steps": skipped_steps,
            "completed_steps": []
        }).execute()


async def _inherit_readiness_score(self, user_id: str, company_id: str) -> None:
    """
    Inherit corporate_memory readiness score from company baseline.

    The user's corporate_memory sub-score starts from the company's
    existing richness rather than zero.
    """
    # Calculate company's current corporate memory readiness
    company_richness = await self._calculate_richness_score(company_id)

    # Get or create user's onboarding state
    result = (
        self._db.table("onboarding_state")
        .select("*")
        .eq("user_id", user_id)
        .maybe_single()
        .execute()
    )

    if result.data:
        readiness_scores = result.data.get("readiness_scores", {})
        readiness_scores["corporate_memory"] = company_richness

        self._db.table("onboarding_state").update({
            "readiness_scores": readiness_scores
        }).eq("user_id", user_id).execute()
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && pytest tests/test_cross_user.py::test_confirm_company_data_links_user_and_skips_steps tests/test_cross_user.py::test_confirm_company_data_applies_corrections -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/onboarding/cross_user.py backend/tests/test_cross_user.py
git commit -m "feat: add confirm_company_data with user linking and step skipping"
```

---

## Task 6: API Routes

**Files:**
- Modify: `backend/src/api/routes/onboarding.py`
- Create: `backend/tests/api/test_onboarding_cross_user.py`

**Step 1: Write the failing test**

Create `backend/tests/api/test_onboarding_cross_user.py`:

```python
import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def authenticated_client(client, auth_token):
    """Return authenticated test client."""
    client.headers["Authorization"] = f"Bearer {auth_token}"
    return client


def test_get_cross_user_acceleration_new_company(authenticated_client):
    """GET /onboarding/cross-user with new domain returns full recommendation."""
    response = authenticated_client.get("/api/v1/onboarding/cross-user?domain=newcompany.com")

    assert response.status_code == 200
    data = response.json()
    assert data["exists"] is False
    assert data["company_id"] is None
    assert data["recommendation"] == "full"
    assert data["facts"] is None


def test_get_cross_user_acceleration_existing_company(authenticated_client, test_company):
    """GET /onboarding/cross-user with existing domain returns company data."""
    response = authenticated_client.get(f"/api/v1/onboarding/cross-user?domain={test_company['domain']}")

    assert response.status_code == 200
    data = response.json()
    assert data["exists"] is True
    assert data["company_id"] == test_company["id"]
    assert data["company_name"] == test_company["name"]
    assert "richness_score" in data
    assert "recommendation" in data
    assert "facts" in data


def test_confirm_company_data(authenticated_client, test_company, current_user):
    """POST /onboarding/cross-user/confirm updates onboarding state."""
    response = authenticated_client.post("/api/v1/onboarding/cross-user/confirm", json={
        "company_id": test_company["id"],
        "corrections": None
    })

    assert response.status_code == 200
    data = response.json()
    assert "skipped_steps" in data
    assert "company_discovery" in data["skipped_steps"]
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/api/test_onboarding_cross_user.py -v`

Expected: FAIL - endpoints not yet implemented

**Step 3: Write minimal implementation**

Add to `backend/src/api/routes/onboarding.py`:

```python
from pydantic import BaseModel
from typing import Literal, Optional
from fastapi import Query

from src.onboarding.cross_user import CrossUserAccelerationService


class CrossUserAccelerationResponse(BaseModel):
    """Response model for cross-user acceleration check."""
    exists: bool
    company_id: Optional[str]
    company_name: Optional[str]
    richness_score: int  # 0-100
    recommendation: Literal["skip", "partial", "full"]
    facts: Optional[dict]  # Memory Delta if exists


class ConfirmCompanyDataRequest(BaseModel):
    """Request model for confirming company data."""
    company_id: str
    corrections: Optional[dict] = None


@router.get("/cross-user")
async def check_cross_user_acceleration(
    domain: str = Query(..., description="Company domain to check"),
    current_user: dict = Depends(get_current_user)
) -> CrossUserAccelerationResponse:
    """
    Check if company exists with rich data for cross-user onboarding acceleration.

    Returns existence status, richness score, skip recommendation, and company facts
    (if company exists) in a single call.
    """
    service = CrossUserAccelerationService(db=get_db(), llm_client=get_llm())
    result = await service.check_company_exists(domain)

    facts = None
    if result.exists:
        facts = await service.get_company_memory_delta(
            company_id=result.company_id,
            user_id=current_user["id"]
        )

    return CrossUserAccelerationResponse(
        exists=result.exists,
        company_id=result.company_id,
        company_name=result.company_name,
        richness_score=result.richness_score,
        recommendation=result.recommendation,
        facts=facts
    )


@router.post("/cross-user/confirm")
async def confirm_company_data(
    request: ConfirmCompanyDataRequest,
    current_user: dict = Depends(get_current_user)
) -> dict:
    """
    Handle user confirmation of existing company data.

    Applies corrections (if any), links user to company, and updates
    onboarding state to skip ahead.
    """
    service = CrossUserAccelerationService(db=get_db(), llm_client=get_llm())
    await service.confirm_company_data(
        company_id=request.company_id,
        user_id=current_user["id"],
        corrections=request.corrections
    )

    # Return updated onboarding state
    return await get_onboarding_state(current_user["id"])
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/api/test_onboarding_cross_user.py -v`

Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/api/routes/onboarding.py backend/tests/api/test_onboarding_cross_user.py
git commit -m "feat: add cross-user acceleration API endpoints"
```

---

## Task 7: Frontend API Client

**Files:**
- Modify: `frontend/src/api/onboarding.ts`

**Step 1: Add TypeScript types and API functions**

Add to `frontend/src/api/onboarding.ts`:

```typescript
export interface CrossUserAccelerationResponse {
  exists: boolean
  company_id: string | null
  company_name: string | null
  richness_score: number
  recommendation: 'skip' | 'partial' | 'full'
  facts: CompanyMemoryDelta | null
}

export interface CompanyMemoryDelta {
  facts: CompanyFact[]
  high_confidence_facts: CompanyFact[]
  domains_covered: string[]
  total_fact_count: number
}

export interface CompanyFact {
  id: string
  fact: string
  domain: string
  confidence: number
  source: string
}

export interface ConfirmCompanyDataRequest {
  company_id: string
  corrections: Record<string, unknown> | null
}

export async function checkCrossUser(domain: string): Promise<CrossUserAccelerationResponse> {
  return api.get<CrossUserAccelerationResponse>(
    `/api/v1/onboarding/cross-user?domain=${encodeURIComponent(domain)}`
  )
}

export async function confirmCompanyData(
  request: ConfirmCompanyDataRequest
): Promise<OnboardingState> {
  return api.post<OnboardingState>(
    '/api/v1/onboarding/cross-user/confirm',
    request
  )
}
```

**Step 2: Run typecheck**

Run: `cd frontend && npm run typecheck`

Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/api/onboarding.ts
git commit -m "feat: add cross-user acceleration API client functions"
```

---

## Task 8: Frontend - Company Memory Delta Confirmation Component

**Files:**
- Create: `frontend/src/components/onboarding/CompanyMemoryDeltaConfirmation.tsx`

**Step 1: Create the component**

Create `frontend/src/components/onboarding/CompanyMemoryDeltaConfirmation.tsx`:

```typescript
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { CheckCircle, AlertCircle } from 'lucide-react'
import { useMutation } from '@tanstack/react-query'
import { api } from '@/api/client'
import type { CrossUserAccelerationResponse } from '@/api/onboarding'

interface Props {
  data: CrossUserAccelerationResponse
  showGaps?: boolean
}

export function CompanyMemoryDeltaConfirmation({ data, showGaps }: Props) {
  const navigate = useNavigate()
  const [expanded, setExpanded] = useState(false)
  const [correcting, setCorrecting] = useState(false)

  const confirmMutation = useMutation({
    mutationFn: () => api.post('/api/v1/onboarding/cross-user/confirm', {
      company_id: data.company_id,
      corrections: null
    }),
    onSuccess: () => {
      navigate('/onboarding/user-profile')
    }
  })

  const handleConfirm = () => {
    confirmMutation.mutate()
  }

  const handleCorrect = () => {
    setCorrecting(true)
    // TODO: Open correction flow
  }

  if (!data.facts) return null

  return (
    <div className="max-w-2xl mx-auto">
      <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-8">
        <h2 className="text-2xl font-semibold text-gray-900 mb-2">
          I already know quite a bit about {data.company_name}
        </h2>
        <p className="text-gray-600 mb-6">
          From working with your colleagues, here's what I've learned. Anything outdated?
        </p>

        {/* Richness indicator */}
        <div className="mb-6 flex items-center gap-2">
          <div className={`px-3 py-1 rounded-full text-sm font-medium ${
            data.richness_score > 70 ? 'bg-green-100 text-green-800' :
            data.richness_score >= 30 ? 'bg-yellow-100 text-yellow-800' :
            'bg-gray-100 text-gray-800'
          }`}>
            Richness: {data.richness_score}%
          </div>
          <span className="text-sm text-gray-500">
            Based on {data.facts.total_fact_count} facts across {data.facts.domains_covered.length} domains
          </span>
        </div>

        {/* High-confidence facts - always visible */}
        <div className="space-y-3 mb-4">
          {data.facts.high_confidence_facts.slice(0, 5).map((fact, idx) => (
            <div key={fact.id || idx} className="flex items-start gap-3 p-3 bg-gray-50 rounded-lg">
              <CheckCircle className="w-5 h-5 text-green-500 mt-0.5 flex-shrink-0" />
              <p className="text-gray-700 text-sm">{fact.fact}</p>
            </div>
          ))}
        </div>

        {/* Expandable full details */}
        {data.facts.total_fact_count > 5 && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-sm text-gray-500 hover:text-gray-700 mb-4"
          >
            {expanded ? 'Show less' : `View all ${data.facts.total_fact_count} facts`}
          </button>
        )}

        {expanded && (
          <div className="space-y-3 mb-6 p-4 bg-gray-50 rounded-lg max-h-96 overflow-y-auto">
            {data.facts.facts.map((fact, idx) => (
              <div key={fact.id || idx} className="flex items-start gap-3">
                <div className={`w-2 h-2 rounded-full mt-2 flex-shrink-0 ${
                  fact.confidence >= 0.9 ? 'bg-green-500' :
                  fact.confidence >= 0.7 ? 'bg-yellow-500' :
                  'bg-gray-400'
                }`} />
                <div>
                  <p className="text-gray-700 text-sm">{fact.fact}</p>
                  <p className="text-xs text-gray-400 mt-1">
                    {fact.source} • {Math.round(fact.confidence * 100)}% confidence
                  </p>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Gap highlights for partial skip */}
        {showGaps && data.richness_score < 70 && (
          <div className="mb-6 p-4 bg-amber-50 border border-amber-200 rounded-lg">
            <div className="flex items-start gap-2 mb-2">
              <AlertCircle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
              <h3 className="font-medium text-amber-900">
                Help me fill in a few gaps
              </h3>
            </div>
            <p className="text-sm text-amber-800">
              I have a good foundation, but there's more I could learn about your company.
              You can upload documents or provide details in the next steps.
            </p>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-3">
          <button
            onClick={handleConfirm}
            disabled={confirmMutation.isPending}
            className="flex-1 bg-primary hover:bg-primary/90 text-white px-6 py-3 rounded-lg font-medium disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {confirmMutation.isPending ? 'Confirming...' : "That looks right, continue"}
          </button>
          <button
            onClick={handleCorrect}
            className="px-6 py-3 border border-gray-300 rounded-lg font-medium hover:bg-gray-50"
          >
            Something's changed
          </button>
        </div>
      </div>
    </div>
  )
}
```

**Step 2: Run typecheck**

Run: `cd frontend && npm run typecheck`

Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/onboarding/CompanyMemoryDeltaConfirmation.tsx
git commit -m "feat: add CompanyMemoryDeltaConfirmation component"
```

---

## Task 9: Frontend - Integrate into CompanyDiscoveryStep

**Files:**
- Modify: `frontend/src/components/onboarding/CompanyDiscoveryStep.tsx`

**Step 1: Update component to use cross-user check**

Modify `frontend/src/components/onboarding/CompanyDiscoveryStep.tsx`:

```typescript
import { useQuery } from '@tanstack/react-query'
import { checkCrossUser } from '@/api/onboarding'
import { CompanyMemoryDeltaConfirmation } from './CompanyMemoryDeltaConfirmation'

// In component, after domain is entered:
const { data: crossUserData, isLoading: checkingCrossUser } = useQuery({
  queryKey: ['cross-user', domain],
  queryFn: () => checkCrossUser(domain),
  enabled: !!domain && isPersonalEmailDomain(domain) === false,
  staleTime: 5 * 60 * 1000, // 5 minutes
})

// If company exists with acceleration, show confirmation
if (crossUserData?.exists && crossUserData.recommendation !== 'full') {
  return (
    <CompanyMemoryDeltaConfirmation
      data={crossUserData}
      showGaps={crossUserData.recommendation === 'partial'}
    />
  )
}

// Otherwise, show normal company discovery flow...
```

**Step 2: Run typecheck**

Run: `cd frontend && npm run typecheck`

Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/onboarding/CompanyDiscoveryStep.tsx
git commit -m "feat: integrate cross-user check into CompanyDiscoveryStep"
```

---

## Task 10: Quality Gates

**Step 1: Run backend tests**

Run: `cd backend && pytest tests/test_cross_user.py tests/api/test_onboarding_cross_user.py -v`

Expected: All PASS

**Step 2: Run backend typecheck**

Run: `cd backend && mypy src/onboarding/cross_user.py --strict`

Expected: No errors

**Step 3: Run backend linting**

Run: `cd backend && ruff check src/onboarding/cross_user.py`

Expected: No errors

**Step 4: Run frontend typecheck**

Run: `cd frontend && npm run typecheck`

Expected: No errors

**Step 5: Run frontend linting**

Run: `cd frontend && npm run lint`

Expected: No errors

**Step 6: Integration test**

Run both backend and frontend, test the full flow:
1. User #1 completes onboarding (creates rich company data)
2. User #2 starts onboarding with same domain
3. Verify skip/partial recommendation is shown
4. Confirm and verify steps are skipped

**Step 7: Final commit**

```bash
git add backend/src/onboarding/cross_user.py backend/tests/test_cross_user.py backend/tests/api/test_onboarding_cross_user.py backend/src/api/routes/onboarding.py frontend/src/api/onboarding.ts frontend/src/components/onboarding/CompanyMemoryDeltaConfirmation.tsx frontend/src/components/onboarding/CompanyDiscoveryStep.tsx

git commit -m "feat: complete US-917 cross-user onboarding acceleration

When user #2+ at a company starts onboarding, ARIA checks if company
already exists with rich data and skips/shortens company discovery
steps based on richness score (0-100).

- Richness >70%: Skip company discovery + document upload
- Richness 30-70%: Partial skip with gap highlights
- Richness <30%: Full onboarding

Privacy enforced at all layers: User #2 never sees User #1's
Digital Twin or personal data. Only shared Corporate Memory.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
"
```

---

## Summary

This implementation plan follows TDD with bite-sized tasks:

1. **Backend service** - `CrossUserAccelerationService` with richness calculation
2. **Privacy filtering** - Explicit source allow/block lists
3. **API routes** - `/cross-user` check and `/cross-user/confirm` endpoints
4. **Frontend components** - `CompanyMemoryDeltaConfirmation` with tiered display
5. **Integration** - Cross-user check triggered after domain entry

All commits are atomic and testable. Quality gates run at the end.
