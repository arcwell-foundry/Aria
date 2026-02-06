# US-917: Cross-User Onboarding Acceleration

**Date:** 2026-02-06
**Status:** Design Approved
**Sprint:** 9.2

## Overview

When user #2+ at a company starts onboarding, ARIA already knows their company from user #1's onboarding. This feature skips or shortens company-related steps, showing existing data for confirmation instead of re-collection.

**Key principle:** Shared Corporate Memory is intentional in the multi-tenant architecture; Digital Twin remains strictly private per user.

## Problem Statement

Currently, every user at a company goes through full onboarding, including company discovery, document upload, and enrichment. This is redundant when ARIA already has rich Corporate Memory from the first user's onboarding.

## Solution

After user enters company domain, check if company exists with rich data. Based on "richness score" (0-100):

| Richness | Behavior |
|----------|----------|
| >70% | Skip company discovery + document upload. Show Memory Delta for confirmation. |
| 30-70% | Partial skip. Show existing data with gaps highlighted. |
| <30% | Full onboarding (as if first user). |

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                   CompanyDiscoveryStep                       │
│  ┌─────────────┐  ┌──────────────────────────────────────┐ │
│  │ Domain Input│─►│ check_cross_user(domain) API call    │ │
│  └─────────────┘  └──────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
         ┌────────────────────────────────────────┐
         │   CrossUserAccelerationService         │
         │  ┌─────────────────────────────────┐   │
         │  │ check_company_exists(domain)    │   │
         │  │  - Query companies table        │   │
         │  │  - Calculate richness score     │   │
         │  │  - Return recommendation        │   │
         │  └─────────────────────────────────┘   │
         │  ┌─────────────────────────────────┐   │
         │  │ get_company_memory_delta()      │   │
         │  │  - Filter to corporate facts    │   │
         │  │  - Apply confidence tiers       │   │
         │  │  - Return Memory Delta          │   │
         │  └─────────────────────────────────┘   │
         └────────────────────────────────────────┘
                            │
                            ▼
         ┌────────────────────────────────────────┐
         │   CompanyMemoryDeltaConfirmation       │
         │   - "I already know quite a bit..."    │
         │   - MemoryDelta (tiered)               │
         │   - Confirm / Something's changed      │
         └────────────────────────────────────────┘
```

## Backend Implementation

### File: `backend/src/onboarding/cross_user.py`

```python
from typing import Literal
from dataclasses import dataclass
from datetime import datetime

from src.db.supabase_client import SupabaseClient
from src.core.llm_client import AnthropicClient


@dataclass
class CompanyCheckResult:
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
        """Check if company exists and calculate richness score."""
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

        # Hybrid calculation: fast first, deeper if needed
        richness = await self._calculate_richness_score(company_id)

        # Determine recommendation based on richness
        if richness.richness_score > 70:
            recommendation = "skip"
        elif richness.richness_score >= 30:
            recommendation = "partial"
        else:
            recommendation = "full"

        return CompanyCheckResult(
            exists=True,
            company_id=company_id,
            company_name=company_name,
            company_name=company_name,
            richness_score=richness.richness_score,
            recommendation=recommendation
        )

    async def get_company_memory_delta(
        self,
        company_id: str,
        user_id: str
    ) -> dict:
        """
        Get existing company facts for user confirmation.

        Returns tiered Memory Delta with:
        - High-confidence facts shown first
        - Expandable for full details
        - ONLY corporate data (personal data filtered out)
        """
        # Query only corporate memory facts
        result = (
            self._db.table("corporate_memory_facts")
            .select("*")
            .eq("company_id", company_id)
            .in_("source", list(self._CORPORATE_SOURCES))
            .execute()
        )

        facts = result.data or []

        # Use existing MemoryDeltaPresenter for formatting
        from src.memory.delta_presenter import MemoryDeltaPresenter

        presenter = MemoryDeltaPresenter(self._db, self._llm)
        delta = await presenter.generate_delta(
            user_id=user_id,
            since=datetime.min,  # All facts
            filters={"domain": "corporate"}
        )

        return {
            "facts": delta["facts"],
            "high_confidence_facts": [f for f in delta["facts"] if f["confidence"] >= 0.8],
            "domains_covered": list(set(f["domain"] for f in facts)),
            "total_fact_count": len(facts)
        }

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
        - Applies corrections (if any)
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

        # Audit log
        await self._log_cross_user_event(user_id, company_id, corrections)

    async def _calculate_richness_score(self, company_id: str) -> "RichnessScore":
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

        # Deep analysis if in gray zone
        if 30 <= fast_score <= 70:
            deep_score = await self._deep_richness_analysis(company_id)
            return RichnessScore(
                richness_score=deep_score,
                analysis_depth="deep"
            )

        return RichnessScore(
            richness_score=fast_score,
            analysis_depth="fast"
        )

    async def _deep_richness_analysis(self, company_id: str) -> int:
        """Run full readiness-style assessment."""
        # Use existing OnboardingReadinessService
        from src.onboarding.readiness import OnboardingReadinessService

        readiness_service = OnboardingReadinessService(self._db, self._llm)
        corporate_readiness = await readiness_service.get_readiness(
            company_id=company_id
        )

        return corporate_readiness["corporate_memory"]
```

### API Routes

**File:** `backend/src/api/routes/onboarding.py` (add to existing)

```python
from pydantic import BaseModel
from typing import Literal, Optional
from fastapi import Query, Depends

from src.api.dependencies import get_current_user
from src.onboarding.cross_user import CrossUserAccelerationService


class CrossUserAccelerationResponse(BaseModel):
    exists: bool
    company_id: Optional[str]
    company_name: Optional[str]
    richness_score: int  # 0-100
    recommendation: Literal["skip", "partial", "full"]
    facts: Optional[dict]  # Memory Delta if exists


class ConfirmCompanyDataRequest(BaseModel):
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

## Frontend Implementation

### File: `frontend/src/components/onboarding/CompanyDiscoveryStep.tsx`

```typescript
import { useQuery } from '@tanstack/react-query'
import { api } from '@/api/client'

interface CrossUserData {
  exists: boolean
  company_id: string | null
  company_name: string | null
  richness_score: number
  recommendation: 'skip' | 'partial' | 'full'
  facts: MemoryDelta | null
}

export function CompanyDiscoveryStep() {
  const [domain, setDomain] = useState('')

  // Check for cross-user acceleration after domain entry
  const { data: crossUserData, isLoading } = useQuery({
    queryKey: ['cross-user', domain],
    queryFn: () => api.get(`/api/v1/onboarding/cross-user?domain=${domain}`),
    enabled: !!domain && isPersonalEmailDomain(domain) === false
  })

  // If company exists with rich data, show confirmation
  if (crossUserData?.exists) {
    if (crossUserData.recommendation === 'skip' || crossUserData.recommendation === 'partial') {
      return (
        <CompanyMemoryDeltaConfirmation
          data={crossUserData}
          showGaps={crossUserData.recommendation === 'partial'}
        />
      )
    }
    // recommendation === 'full': continue normal flow
  }

  // Existing company discovery form...
}
```

### File: `frontend/src/components/onboarding/CompanyMemoryDeltaConfirmation.tsx` (new)

```typescript
interface Props {
  data: CrossUserData
  showGaps?: boolean
}

export function CompanyMemoryDeltaConfirmation({ data, showGaps }: Props) {
  const navigate = useNavigate()
  const [expanded, setExpanded] = useState(false)
  const [correcting, setCorrecting] = useState(false)

  const handleConfirm = async () => {
    await api.post('/api/v1/onboarding/cross-user/confirm', {
      company_id: data.company_id,
      corrections: null
    })
    navigate('/onboarding/user-profile')
  }

  const handleCorrect = () => {
    setCorrecting(true)
    // Open correction flow...
  }

  return (
    <div className="max-w-2xl mx-auto">
      <div className="bg-white rounded-lg shadow-sm p-8">
        <h2 className="text-2xl font-semibold text-gray-900 mb-2">
          I already know quite a bit about {data.company_name}
        </h2>
        <p className="text-gray-600 mb-6">
          From working with your colleagues, here's what I've learned. Anything outdated?
        </p>

        {/* High-confidence facts - always visible */}
        <div className="space-y-4 mb-4">
          {data.facts?.high_confidence_facts.map(fact => (
            <div key={fact.id} className="flex items-start gap-3">
              <CheckCircle className="w-5 h-5 text-green-500 mt-0.5" />
              <p className="text-gray-700">{fact.fact}</p>
            </div>
          ))}
        </div>

        {/* Expandable full details */}
        <button
          onClick={() => setExpanded(!expanded)}
          className="text-sm text-gray-500 hover:text-gray-700 mb-4"
        >
          {expanded ? 'Show less' : `View all ${data.facts?.total_fact_count} facts`}
        </button>

        {expanded && (
          <MemoryDelta
            facts={data.facts?.facts}
            showCorrections={true}
            onCorrect={handleCorrect}
          />
        )}

        {/* Gap highlights for partial skip */}
        {showGaps && data.facts?.gaps && (
          <div className="mt-6 p-4 bg-amber-50 rounded-lg">
            <h3 className="font-medium text-amber-900 mb-2">
              Help me fill in a few gaps
            </h3>
            <ul className="text-sm text-amber-800 space-y-1">
              {data.facts.gaps.map(gap => (
                <li key={gap.domain}>• {gap.description}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-3 mt-6">
          <button
            onClick={handleConfirm}
            className="flex-1 bg-primary text-white px-6 py-3 rounded-lg font-medium"
          >
            That looks right, continue
          </button>
          <button
            onClick={handleCorrect}
            className="px-6 py-3 border border-gray-300 rounded-lg font-medium"
          >
            Something's changed
          </button>
        </div>
      </div>
    </div>
  )
}
```

### File: `frontend/src/api/onboarding.ts` (add to existing)

```typescript
export interface CrossUserAccelerationResponse {
  exists: boolean
  company_id: string | null
  company_name: string | null
  richness_score: number
  recommendation: 'skip' | 'partial' | 'full'
  facts: MemoryDelta | null
}

export async function checkCrossUser(domain: string): Promise<CrossUserAccelerationResponse> {
  return api.get(`/api/v1/onboarding/cross-user?domain=${domain}`)
}

export async function confirmCompanyData(request: {
  company_id: string
  corrections: Record<string, unknown> | null
}): Promise<OnboardingState> {
  return api.post('/api/v1/onboarding/cross-user/confirm', request)
}
```

## Privacy and Data Isolation

### Full-Stack Privacy Enforcement

**1. Database Layer (RLS)**
```sql
-- Corporate memory facts are company-scoped (no user_id)
-- Digital Twin facts have user_id RLS
-- Cross-user queries only access corporate_memory_facts table
```

**2. Service Layer Filtering**
```python
# Explicit allow-list for corporate sources
_CORPORATE_SOURCES = {
    "company_enrichment",
    "document_upload",
    "crm_sync",
    "web_research",
}

# Explicit block-list for personal sources
_PERSONAL_SOURCES = {
    "email_analysis",      # US-908 - relationships
    "writing_sample",      # US-906 - Digital Twin
    "linkedin_research",   # US-905 - personal
}
```

**3. API Response Contract**
```python
class MemoryDeltaFact(BaseModel):
    domain: Literal["corporate"]  # Never "personal" or "relationship"
    fact: str
    confidence: float
    source: str  # Validated against corporate sources
```

**4. TypeScript Type Guarantees**
```typescript
interface CompanyMemoryDelta {
  facts: Array<{
    domain: 'corporate'  // Literal type
    fact: string
    confidence: number
    source: CompanyDataSource
  }>
}
```

## Integration Checklist

- [ ] Corporate Memory: Read existing, merge new contributions
- [ ] Readiness score: User inherits company's `corporate_memory` sub-score baseline
- [ ] Episodic memory: Record cross-user acceleration event
- [ ] Audit log: Track inherited vs. newly-provided data
- [ ] Privacy enforcement: Personal data never included in company delta

## Testing

### Unit Tests (`backend/tests/test_cross_user.py`)

```python
async def test_richness_score_gt_70_returns_skip():
    """Established company with rich data should skip."""
    result = await service.check_company_exists("established-corp.com")
    assert result.recommendation == "skip"
    assert result.richness_score > 70

async def test_richness_score_30_70_returns_partial():
    """Company with moderate data should partial skip."""
    result = await service.check_company_exists("partial-corp.com")
    assert result.recommendation == "partial"
    assert 30 <= result.richness_score <= 70

async def test_new_company_returns_full():
    """New company should do full onboarding."""
    result = await service.check_company_exists("new-corp.com")
    assert result.recommendation == "full"
    assert not result.exists

async def test_personal_data_never_included():
    """Privacy: User #2 should never see User #1's personal data."""
    delta = await service.get_company_memory_delta(company_id, user_2_id)
    for fact in delta.facts:
        assert fact.domain == "corporate"
        assert fact.source not in ["email_analysis", "writing_sample"]
```

### Integration Tests

```python
async def test_cross_user_onboarding_flow_skip():
    """Full flow: User #1 onboards, User #2 gets accelerated."""
    # User #1 completes onboarding
    # Company has 50+ facts, 8 domains, documents

    # User #2 starts onboarding with same domain
    result = await check_cross_user_acceleration(domain)
    assert result.exists
    assert result.recommendation == "skip"

    # User #2 confirms
    await confirm_company_data(company_id, user_2_id, corrections=None)

    # Verify onboarding state updated
    state = await get_onboarding_state(user_2_id)
    assert "company_discovery" in state.skipped_steps
    assert "document_upload" in state.skipped_steps
```

## Acceptance Criteria

- [x] On company discovery: Check if company exists in Corporate Memory
- [x] Calculate `corporate_memory_richness` score (0-100)
- [x] Richness > 70%: Skip company discovery + document upload
- [x] Richness 30-70%: Partial skip with gap highlights
- [x] Richness < 30%: Full onboarding
- [x] Show Memory Delta of key company facts for confirmation
- [x] User can correct/update existing data
- [x] Steps 4-8 (user-specific) remain full
- [x] Privacy: User #2 never sees User #1's Digital Twin
- [x] Shared Corporate Memory is intentional per architecture

## Open Questions

None - design is complete.
