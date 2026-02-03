# US-404: Daily Briefing Backend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Complete the Daily Briefing Backend by implementing the four data-gathering methods that populate briefings with real data from lead memories, prospective memories, and market signals.

**Architecture:** The briefing service (`BriefingService`) already has the structure for generating briefings. The migration, routes, and LLM summary generation are complete. This plan implements the four stubbed data-gathering methods: `_get_task_data()`, `_get_lead_data()`, `_get_signal_data()`, and `_get_calendar_data()`. Each method queries the appropriate Supabase table and returns structured data for the briefing.

**Tech Stack:** Python 3.11+ / FastAPI / Supabase / Pydantic / pytest

---

## Task 1: Implement Task Data Gathering

**Files:**
- Modify: `/Users/dhruv/aria/backend/src/services/briefing.py:199-209`
- Test: `/Users/dhruv/aria/backend/tests/test_briefing_service.py`

**Step 1: Write the failing test for overdue tasks**

Add to `/Users/dhruv/aria/backend/tests/test_briefing_service.py`:

```python
@pytest.mark.asyncio
async def test_get_task_data_returns_overdue_tasks() -> None:
    """Test _get_task_data returns overdue tasks from prospective_memories."""
    with patch("src.services.briefing.SupabaseClient") as mock_db_class:
        overdue_tasks = [
            {
                "id": "task-1",
                "task": "Follow up with Acme Corp",
                "priority": "high",
                "trigger_config": {"due_at": "2026-02-01T09:00:00Z"},
            },
        ]
        today_tasks = [
            {
                "id": "task-2",
                "task": "Send proposal",
                "priority": "medium",
                "trigger_config": {"due_at": "2026-02-03T17:00:00Z"},
            },
        ]

        # Setup DB mock for two separate queries
        mock_db = MagicMock()
        mock_table = MagicMock()

        # First call returns overdue, second call returns today
        mock_table.select.return_value.eq.return_value.eq.return_value.lt.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=overdue_tasks
        )
        mock_table.select.return_value.eq.return_value.eq.return_value.gte.return_value.lt.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=today_tasks
        )
        mock_db.table.return_value = mock_table
        mock_db_class.get_client.return_value = mock_db

        from src.services.briefing import BriefingService

        service = BriefingService()
        result = await service._get_task_data(user_id="test-user-123")

        assert "overdue" in result
        assert "due_today" in result
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_briefing_service.py::test_get_task_data_returns_overdue_tasks -v`
Expected: FAIL - test expects real database queries but method returns empty structure

**Step 3: Write minimal implementation**

Replace `_get_task_data` in `/Users/dhruv/aria/backend/src/services/briefing.py`:

```python
async def _get_task_data(self, user_id: str) -> dict[str, Any]:
    """Get task status from prospective memories.

    Args:
        user_id: The user's ID.

    Returns:
        Dict with overdue and due_today tasks.
    """
    from datetime import datetime, timedelta

    today_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    # Get overdue tasks (due_at < today AND status = pending)
    overdue_result = (
        self._db.table("prospective_memories")
        .select("id, task, priority, trigger_config")
        .eq("user_id", user_id)
        .eq("status", "pending")
        .lt("trigger_config->>due_at", today_start.isoformat())
        .order("trigger_config->>due_at", desc=False)
        .limit(10)
        .execute()
    )

    # Get tasks due today (today_start <= due_at < today_end AND status = pending)
    today_result = (
        self._db.table("prospective_memories")
        .select("id, task, priority, trigger_config")
        .eq("user_id", user_id)
        .eq("status", "pending")
        .gte("trigger_config->>due_at", today_start.isoformat())
        .lt("trigger_config->>due_at", today_end.isoformat())
        .order("trigger_config->>due_at", desc=False)
        .limit(10)
        .execute()
    )

    overdue = [
        {
            "id": t["id"],
            "task": t["task"],
            "priority": t["priority"],
            "due_at": t.get("trigger_config", {}).get("due_at"),
        }
        for t in (overdue_result.data or [])
        if isinstance(t, dict)
    ]

    due_today = [
        {
            "id": t["id"],
            "task": t["task"],
            "priority": t["priority"],
            "due_at": t.get("trigger_config", {}).get("due_at"),
        }
        for t in (today_result.data or [])
        if isinstance(t, dict)
    ]

    return {"overdue": overdue, "due_today": due_today}
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_briefing_service.py::test_get_task_data_returns_overdue_tasks -v`
Expected: PASS

**Step 5: Run all briefing tests to ensure no regressions**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_briefing_service.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add backend/src/services/briefing.py backend/tests/test_briefing_service.py
git commit -m "$(cat <<'EOF'
feat(briefing): implement task data gathering from prospective_memories

Queries prospective_memories table for overdue and due_today tasks.
Returns structured task data for daily briefing content.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Implement Lead Data Gathering

**Files:**
- Modify: `/Users/dhruv/aria/backend/src/services/briefing.py:171-181`
- Test: `/Users/dhruv/aria/backend/tests/test_briefing_service.py`

**Step 1: Write the failing test for lead data**

Add to `/Users/dhruv/aria/backend/tests/test_briefing_service.py`:

```python
@pytest.mark.asyncio
async def test_get_lead_data_returns_categorized_leads() -> None:
    """Test _get_lead_data returns leads categorized by urgency."""
    with patch("src.services.briefing.SupabaseClient") as mock_db_class:
        hot_leads = [
            {
                "id": "lead-1",
                "company_name": "Acme Corp",
                "health_score": 85,
                "lifecycle_stage": "opportunity",
            },
        ]
        needs_attention = [
            {
                "id": "lead-2",
                "company_name": "Beta Inc",
                "health_score": 35,
                "lifecycle_stage": "lead",
            },
        ]
        recently_active = [
            {
                "id": "lead-3",
                "company_name": "Gamma LLC",
                "health_score": 60,
                "last_activity_at": "2026-02-02T15:00:00Z",
            },
        ]

        mock_db = MagicMock()
        # Setup returns for three separate queries
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=hot_leads
        )
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=needs_attention
        )
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=recently_active
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.briefing import BriefingService

        service = BriefingService()
        result = await service._get_lead_data(user_id="test-user-123")

        assert "hot_leads" in result
        assert "needs_attention" in result
        assert "recently_active" in result
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_briefing_service.py::test_get_lead_data_returns_categorized_leads -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Replace `_get_lead_data` in `/Users/dhruv/aria/backend/src/services/briefing.py`:

```python
async def _get_lead_data(self, user_id: str) -> dict[str, Any]:
    """Get lead status summary from lead_memories.

    Args:
        user_id: The user's ID.

    Returns:
        Dict with hot_leads, needs_attention, and recently_active.
    """
    from datetime import timedelta

    week_ago = (datetime.now(UTC) - timedelta(days=7)).isoformat()

    # Hot leads: health_score >= 70 AND status = active
    hot_result = (
        self._db.table("lead_memories")
        .select("id, company_name, health_score, lifecycle_stage, last_activity_at")
        .eq("user_id", user_id)
        .eq("status", "active")
        .gte("health_score", 70)
        .order("health_score", desc=True)
        .limit(5)
        .execute()
    )

    # Needs attention: health_score <= 40 AND status = active
    attention_result = (
        self._db.table("lead_memories")
        .select("id, company_name, health_score, lifecycle_stage, last_activity_at")
        .eq("user_id", user_id)
        .eq("status", "active")
        .lte("health_score", 40)
        .order("health_score", desc=False)
        .limit(5)
        .execute()
    )

    # Recently active: last_activity_at within 7 days
    active_result = (
        self._db.table("lead_memories")
        .select("id, company_name, health_score, lifecycle_stage, last_activity_at")
        .eq("user_id", user_id)
        .eq("status", "active")
        .gte("last_activity_at", week_ago)
        .order("last_activity_at", desc=True)
        .limit(5)
        .execute()
    )

    def format_lead(lead: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": lead["id"],
            "company_name": lead["company_name"],
            "health_score": lead.get("health_score"),
            "lifecycle_stage": lead.get("lifecycle_stage"),
            "last_activity_at": lead.get("last_activity_at"),
        }

    return {
        "hot_leads": [format_lead(l) for l in (hot_result.data or []) if isinstance(l, dict)],
        "needs_attention": [format_lead(l) for l in (attention_result.data or []) if isinstance(l, dict)],
        "recently_active": [format_lead(l) for l in (active_result.data or []) if isinstance(l, dict)],
    }
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_briefing_service.py::test_get_lead_data_returns_categorized_leads -v`
Expected: PASS

**Step 5: Run all briefing tests**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_briefing_service.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add backend/src/services/briefing.py backend/tests/test_briefing_service.py
git commit -m "$(cat <<'EOF'
feat(briefing): implement lead data gathering from lead_memories

Queries lead_memories table for:
- hot_leads: health_score >= 70
- needs_attention: health_score <= 40
- recently_active: activity within 7 days

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Implement Signal Data Gathering

**Files:**
- Modify: `/Users/dhruv/aria/backend/src/services/briefing.py:183-197`
- Test: `/Users/dhruv/aria/backend/tests/test_briefing_service.py`

**Step 1: Write the failing test for signal data**

Add to `/Users/dhruv/aria/backend/tests/test_briefing_service.py`:

```python
@pytest.mark.asyncio
async def test_get_signal_data_returns_categorized_signals() -> None:
    """Test _get_signal_data returns signals categorized by type."""
    with patch("src.services.briefing.SupabaseClient") as mock_db_class:
        signals = [
            {
                "id": "signal-1",
                "company_name": "Acme Corp",
                "signal_type": "funding",
                "headline": "Acme raises $50M Series B",
                "relevance_score": 0.9,
                "detected_at": "2026-02-02T10:00:00Z",
            },
            {
                "id": "signal-2",
                "company_name": "Beta Inc",
                "signal_type": "hiring",
                "headline": "Beta Inc hiring 50 sales reps",
                "relevance_score": 0.7,
                "detected_at": "2026-02-02T11:00:00Z",
            },
            {
                "id": "signal-3",
                "company_name": "Competitor X",
                "signal_type": "product",
                "headline": "Competitor X launches new feature",
                "relevance_score": 0.8,
                "detected_at": "2026-02-02T12:00:00Z",
            },
        ]

        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.is_.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=signals
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.briefing import BriefingService

        service = BriefingService()
        result = await service._get_signal_data(user_id="test-user-123")

        assert "company_news" in result
        assert "market_trends" in result
        assert "competitive_intel" in result
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_briefing_service.py::test_get_signal_data_returns_categorized_signals -v`
Expected: FAIL

**Step 3: Write minimal implementation**

Replace `_get_signal_data` in `/Users/dhruv/aria/backend/src/services/briefing.py`:

```python
async def _get_signal_data(self, user_id: str) -> dict[str, Any]:
    """Get market signals from market_signals table.

    Args:
        user_id: The user's ID.

    Returns:
        Dict with company_news, market_trends, and competitive_intel.
    """
    from datetime import timedelta

    week_ago = (datetime.now(UTC) - timedelta(days=7)).isoformat()

    # Get unread signals from the past week
    result = (
        self._db.table("market_signals")
        .select("id, company_name, signal_type, headline, summary, relevance_score, detected_at")
        .eq("user_id", user_id)
        .is_("dismissed_at", "null")
        .gte("detected_at", week_ago)
        .order("relevance_score", desc=True)
        .limit(20)
        .execute()
    )

    signals = result.data or []

    # Categorize by signal type
    company_news_types = {"funding", "leadership", "earnings", "partnership"}
    market_trend_types = {"regulatory", "clinical_trial", "fda_approval", "patent"}
    competitive_types = {"product", "hiring"}

    def format_signal(s: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": s["id"],
            "company_name": s["company_name"],
            "headline": s["headline"],
            "summary": s.get("summary"),
            "relevance_score": s.get("relevance_score"),
            "detected_at": s.get("detected_at"),
        }

    company_news = [
        format_signal(s)
        for s in signals
        if isinstance(s, dict) and s.get("signal_type") in company_news_types
    ][:5]

    market_trends = [
        format_signal(s)
        for s in signals
        if isinstance(s, dict) and s.get("signal_type") in market_trend_types
    ][:5]

    competitive_intel = [
        format_signal(s)
        for s in signals
        if isinstance(s, dict) and s.get("signal_type") in competitive_types
    ][:5]

    return {
        "company_news": company_news,
        "market_trends": market_trends,
        "competitive_intel": competitive_intel,
    }
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_briefing_service.py::test_get_signal_data_returns_categorized_signals -v`
Expected: PASS

**Step 5: Run all briefing tests**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_briefing_service.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add backend/src/services/briefing.py backend/tests/test_briefing_service.py
git commit -m "$(cat <<'EOF'
feat(briefing): implement signal data gathering from market_signals

Queries market_signals table and categorizes into:
- company_news: funding, leadership, earnings, partnership
- market_trends: regulatory, clinical_trial, fda_approval, patent
- competitive_intel: product, hiring

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Implement Calendar Data Gathering (Stub for Integration)

**Files:**
- Modify: `/Users/dhruv/aria/backend/src/services/briefing.py:154-169`
- Test: `/Users/dhruv/aria/backend/tests/test_briefing_service.py`

**Note:** Calendar integration requires external OAuth connections (Composio). This task creates the structure for calendar data gathering with a graceful fallback when no calendar is connected.

**Step 1: Write the failing test for calendar data with integration**

Add to `/Users/dhruv/aria/backend/tests/test_briefing_service.py`:

```python
@pytest.mark.asyncio
async def test_get_calendar_data_returns_empty_when_no_integration() -> None:
    """Test _get_calendar_data returns empty structure when calendar not integrated."""
    with patch("src.services.briefing.SupabaseClient") as mock_db_class:
        # No calendar integration configured
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.single.return_value.execute.return_value = MagicMock(
            data=None
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.briefing import BriefingService

        service = BriefingService()
        result = await service._get_calendar_data(
            user_id="test-user-123", briefing_date=date.today()
        )

        assert result == {"meeting_count": 0, "key_meetings": []}


@pytest.mark.asyncio
async def test_get_calendar_data_structure() -> None:
    """Test _get_calendar_data returns correct structure."""
    with patch("src.services.briefing.SupabaseClient") as mock_db_class:
        mock_db = MagicMock()
        mock_db_class.get_client.return_value = mock_db

        from src.services.briefing import BriefingService

        service = BriefingService()
        result = await service._get_calendar_data(
            user_id="test-user-123", briefing_date=date.today()
        )

        # Verify structure even without integration
        assert "meeting_count" in result
        assert "key_meetings" in result
        assert isinstance(result["meeting_count"], int)
        assert isinstance(result["key_meetings"], list)
```

**Step 2: Run test to verify current implementation passes**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_briefing_service.py::test_get_calendar_data_structure -v`
Expected: PASS (current stub already returns this structure)

**Step 3: Update implementation with integration check**

Replace `_get_calendar_data` in `/Users/dhruv/aria/backend/src/services/briefing.py`:

```python
async def _get_calendar_data(
    self,
    user_id: str,
    briefing_date: date,
) -> dict[str, Any]:
    """Get calendar events for the day.

    Args:
        user_id: The user's ID.
        briefing_date: The date to get calendar for.

    Returns:
        Dict with meeting_count and key_meetings.
    """
    # Check if user has calendar integration
    integration_result = (
        self._db.table("user_integrations")
        .select("id, provider, status")
        .eq("user_id", user_id)
        .eq("provider", "google_calendar")
        .eq("status", "active")
        .single()
        .execute()
    )

    if not integration_result.data:
        logger.debug(
            "No calendar integration for user",
            extra={"user_id": user_id},
        )
        return {"meeting_count": 0, "key_meetings": []}

    # TODO: Implement Composio calendar fetch when available
    # For now, return empty structure as calendar integration
    # requires external OAuth flow completion
    logger.info(
        "Calendar integration found but fetch not yet implemented",
        extra={"user_id": user_id, "briefing_date": briefing_date.isoformat()},
    )
    return {"meeting_count": 0, "key_meetings": []}
```

**Step 4: Run all briefing tests**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_briefing_service.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add backend/src/services/briefing.py backend/tests/test_briefing_service.py
git commit -m "$(cat <<'EOF'
feat(briefing): add calendar integration check structure

Checks user_integrations table for google_calendar connection.
Returns empty calendar data when no integration configured.
Calendar fetch via Composio to be implemented when OAuth ready.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Add POST /api/v1/briefings/regenerate Endpoint

**Files:**
- Modify: `/Users/dhruv/aria/backend/src/api/routes/briefings.py`
- Test: `/Users/dhruv/aria/backend/tests/test_api_briefings.py`

**Note:** The user story specifies `/regenerate` but current implementation has `/generate`. Adding `/regenerate` as an alias for clarity.

**Step 1: Write the failing test for regenerate endpoint**

Add to `/Users/dhruv/aria/backend/tests/test_api_briefings.py`:

```python
def test_regenerate_briefing_creates_new_briefing(test_client: TestClient) -> None:
    """Test POST /api/v1/briefings/regenerate creates new briefing."""
    with patch("src.services.briefing.SupabaseClient") as mock_db_class, patch(
        "src.services.briefing.anthropic.Anthropic"
    ) as mock_llm_class:
        # Setup DB mock
        mock_db = MagicMock()
        mock_db.table.return_value.upsert.return_value.execute.return_value = MagicMock(
            data=[{"id": "briefing-123"}]
        )
        mock_db_class.get_client.return_value = mock_db

        # Setup LLM mock
        mock_llm_response = MagicMock()
        mock_llm_content = MagicMock()
        mock_llm_content.text = "Regenerated briefing"
        mock_llm_response.content = [mock_llm_content]
        mock_llm_class.return_value.messages.create.return_value = mock_llm_response

        response = test_client.post("/api/v1/briefings/regenerate")

    assert response.status_code == 200
    data = response.json()
    assert "summary" in data
```

**Step 2: Run test to verify it fails**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_api_briefings.py::test_regenerate_briefing_creates_new_briefing -v`
Expected: FAIL with 404 (endpoint doesn't exist)

**Step 3: Add regenerate endpoint**

Add to `/Users/dhruv/aria/backend/src/api/routes/briefings.py` after the generate endpoint:

```python
@router.post("/regenerate", response_model=BriefingContent)
async def regenerate_briefing(
    current_user: CurrentUser,
) -> BriefingContent:
    """Regenerate today's briefing with fresh data.

    Forces regeneration of today's briefing, useful when
    underlying data has changed (new leads, signals, etc.).
    """
    service = BriefingService()
    content = await service.generate_briefing(current_user.id)

    logger.info(
        "Briefing regenerated",
        extra={"user_id": current_user.id},
    )

    return BriefingContent(**content)
```

**Step 4: Run test to verify it passes**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_api_briefings.py::test_regenerate_briefing_creates_new_briefing -v`
Expected: PASS

**Step 5: Run all API tests**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_api_briefings.py -v`
Expected: All tests PASS

**Step 6: Commit**

```bash
git add backend/src/api/routes/briefings.py backend/tests/test_api_briefings.py
git commit -m "$(cat <<'EOF'
feat(api): add POST /api/v1/briefings/regenerate endpoint

Adds /regenerate alias for forcing briefing regeneration.
Useful when underlying data has changed since last generation.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Update Tests for Real Data Queries

**Files:**
- Test: `/Users/dhruv/aria/backend/tests/test_briefing_service.py`

**Note:** Update existing stub tests to reflect the new real implementations.

**Step 1: Update test_get_task_data_returns_empty_dict_when_no_tasks**

Update in `/Users/dhruv/aria/backend/tests/test_briefing_service.py`:

```python
@pytest.mark.asyncio
async def test_get_task_data_returns_empty_dict_when_no_tasks() -> None:
    """Test _get_task_data returns empty structure when no tasks exist."""
    with patch("src.services.briefing.SupabaseClient") as mock_db_class:
        mock_db = MagicMock()
        # Both queries return empty
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.lt.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.gte.return_value.lt.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.briefing import BriefingService

        service = BriefingService()
        result = await service._get_task_data(user_id="test-user-123")

        assert result == {"overdue": [], "due_today": []}
```

**Step 2: Update test_get_lead_data_returns_empty_dict_when_no_leads**

```python
@pytest.mark.asyncio
async def test_get_lead_data_returns_empty_dict_when_no_leads() -> None:
    """Test _get_lead_data returns empty structure when no leads exist."""
    with patch("src.services.briefing.SupabaseClient") as mock_db_class:
        mock_db = MagicMock()
        # All three queries return empty
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.lte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.briefing import BriefingService

        service = BriefingService()
        result = await service._get_lead_data(user_id="test-user-123")

        assert result == {"hot_leads": [], "needs_attention": [], "recently_active": []}
```

**Step 3: Update test_get_signal_data_returns_empty_dict_when_no_signals**

```python
@pytest.mark.asyncio
async def test_get_signal_data_returns_empty_dict_when_no_signals() -> None:
    """Test _get_signal_data returns empty structure when no signals exist."""
    with patch("src.services.briefing.SupabaseClient") as mock_db_class:
        mock_db = MagicMock()
        mock_db.table.return_value.select.return_value.eq.return_value.is_.return_value.gte.return_value.order.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[]
        )
        mock_db_class.get_client.return_value = mock_db

        from src.services.briefing import BriefingService

        service = BriefingService()
        result = await service._get_signal_data(user_id="test-user-123")

        assert result == {
            "company_news": [],
            "market_trends": [],
            "competitive_intel": [],
        }
```

**Step 4: Run all tests**

Run: `cd /Users/dhruv/aria/backend && pytest tests/test_briefing_service.py tests/test_api_briefings.py -v`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add backend/tests/test_briefing_service.py
git commit -m "$(cat <<'EOF'
test(briefing): update tests for real data query implementations

Updates existing stub tests to mock actual database queries.
All tests now reflect real implementation behavior.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Run Full Test Suite and Type Checks

**Files:**
- All backend files

**Step 1: Run full test suite**

Run: `cd /Users/dhruv/aria/backend && pytest tests/ -v`
Expected: All tests PASS

**Step 2: Run type checker**

Run: `cd /Users/dhruv/aria/backend && mypy src/services/briefing.py src/api/routes/briefings.py --strict`
Expected: No errors

**Step 3: Run linter**

Run: `cd /Users/dhruv/aria/backend && ruff check src/services/briefing.py src/api/routes/briefings.py`
Expected: No errors

**Step 4: Run formatter**

Run: `cd /Users/dhruv/aria/backend && ruff format src/services/briefing.py src/api/routes/briefings.py`
Expected: Files formatted (or already formatted)

**Step 5: Final commit if any formatting changes**

```bash
git add -A
git commit -m "$(cat <<'EOF'
style: format briefing service and routes

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)" || echo "No formatting changes"
```

---

## Summary

This plan completes US-404: Daily Briefing Backend by implementing:

1. **Task Data Gathering** - Queries `prospective_memories` for overdue and due_today tasks
2. **Lead Data Gathering** - Queries `lead_memories` for hot_leads, needs_attention, and recently_active
3. **Signal Data Gathering** - Queries `market_signals` and categorizes into company_news, market_trends, competitive_intel
4. **Calendar Data Gathering** - Checks `user_integrations` for calendar connection (stub for Composio integration)
5. **Regenerate Endpoint** - Adds `/api/v1/briefings/regenerate` as specified in requirements
6. **Test Updates** - Updates all existing tests to mock real database queries
7. **Quality Checks** - Runs full test suite, type checker, and linter

The migration, RLS policies, and basic route structure were already in place. This plan focuses solely on the data-gathering implementations.
