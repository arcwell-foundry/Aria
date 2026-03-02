# Connection Health Monitor Tests Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add missing test coverage for the connection health monitor scheduler job

**Architecture:** The connection health monitor is already fully implemented in `backend/src/services/scheduler.py` (lines 1379-1492). It runs daily at 4 AM, checks up to 100 connections, and handles success, auth failures (401/403), and transient errors differently. Tests exist but are incomplete.

**Tech Stack:** Python 3.11+, pytest, pytest-asyncio, unittest.mock

---

## Status: Implementation Complete, Tests Incomplete

### Already Implemented

1. **`_run_connection_health_check()`** in `backend/src/services/scheduler.py:1379-1478`
   - Queries `user_connections` WHERE status='active' AND not verified in 24h
   - Batch size: 100 connections
   - 0.5s delay between checks
   - On success: updates `last_health_check_at`, resets `failure_count` to 0
   - On 401/403/token error: calls `registry.mark_connection_expired()`, sends WebSocket event
   - On transient error: increments `failure_count`, keeps status active

2. **`_get_health_check_action()`** in `backend/src/services/scheduler.py:1480-1492`
   - Maps toolkit slugs to lightweight read-only actions
   - Supports: OUTLOOK365, GMAIL, SALESFORCE, HUBSPOT, GOOGLECALENDAR, SLACK, ZOOM

3. **APScheduler registration** in `backend/src/services/scheduler.py:1772-1779`
   - Cron: 4:00 AM daily
   - id: "connection_health_check"
   - misfire_grace_time: 3600

### Existing Tests (in `backend/tests/test_ooda_connections.py:416-466`)

- ✅ `test_get_health_check_action_mapping` - verifies toolkit mapping
- ✅ `test_health_check_marks_expired_on_auth_failure` - verifies 401 handling

### Missing Tests (Required by User)

- ❌ Successful health check updates `last_health_check_at` and resets `failure_count`
- ❌ Transient error increments `failure_count` but keeps status active

---

### Task 1: Add Success Path Test

**Files:**
- Modify: `backend/tests/test_ooda_connections.py:467` (after existing tests)

**Step 1: Write the failing test**

Add this test to the `TestConnectionHealthCheck` class:

```python
@pytest.mark.asyncio
async def test_health_check_updates_timestamp_on_success(self):
    """Health check should update last_health_check_at and reset failure_count on success."""
    from src.services.scheduler import _run_connection_health_check

    with patch("src.db.supabase.SupabaseClient") as mock_sb, \
         patch("src.integrations.connection_registry.get_connection_registry") as mock_reg, \
         patch("src.integrations.composio_sessions.get_session_manager") as mock_session:

        mock_client = MagicMock()
        mock_sb.get_client.return_value = mock_client

        # Connection with previous failures
        mock_client.table.return_value.select.return_value.eq.return_value.or_.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "conn-1",
                    "user_id": "user-1",
                    "toolkit_slug": "GMAIL",
                    "composio_connection_id": "comp-1",
                    "last_health_check_at": None,
                    "failure_count": 2,  # Had previous transient errors
                }
            ]
        )

        # Successful API call
        mock_mgr = MagicMock()
        mock_mgr.execute_action = AsyncMock(return_value={"messages": []})
        mock_session.return_value = mock_mgr

        mock_registry = MagicMock()
        mock_registry.mark_connection_expired = AsyncMock()
        mock_reg.return_value = mock_registry

        await _run_connection_health_check()

        # Should NOT mark as expired
        mock_registry.mark_connection_expired.assert_not_awaited()

        # Should update last_health_check_at and reset failure_count
        update_call = mock_client.table.return_value.update.call_args
        assert update_call is not None
        update_data = update_call[0][0]
        assert "last_health_check_at" in update_data
        assert update_data["failure_count"] == 0
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_ooda_connections.py::TestConnectionHealthCheck::test_health_check_updates_timestamp_on_success -v`

Expected: PASS (implementation exists, just missing test coverage)

**Step 3: Commit**

```bash
git add backend/tests/test_ooda_connections.py
git commit -m "test: add success path test for connection health check"
```

---

### Task 2: Add Transient Error Test

**Files:**
- Modify: `backend/tests/test_ooda_connections.py` (after Task 1)

**Step 1: Write the failing test**

Add this test to the `TestConnectionHealthCheck` class:

```python
@pytest.mark.asyncio
async def test_health_check_increments_failure_count_on_transient_error(self):
    """Health check should increment failure_count but NOT expire on transient errors."""
    from src.services.scheduler import _run_connection_health_check

    with patch("src.db.supabase.SupabaseClient") as mock_sb, \
         patch("src.integrations.connection_registry.get_connection_registry") as mock_reg, \
         patch("src.integrations.composio_sessions.get_session_manager") as mock_session:

        mock_client = MagicMock()
        mock_sb.get_client.return_value = mock_client

        mock_client.table.return_value.select.return_value.eq.return_value.or_.return_value.limit.return_value.execute.return_value = MagicMock(
            data=[
                {
                    "id": "conn-1",
                    "user_id": "user-1",
                    "toolkit_slug": "GMAIL",
                    "composio_connection_id": "comp-1",
                    "last_health_check_at": None,
                    "failure_count": 1,
                }
            ]
        )

        # Transient error (not auth-related)
        mock_mgr = MagicMock()
        mock_mgr.execute_action = AsyncMock(side_effect=Exception("Network timeout"))
        mock_session.return_value = mock_mgr

        mock_registry = MagicMock()
        mock_registry.mark_connection_expired = AsyncMock()
        mock_reg.return_value = mock_registry

        await _run_connection_health_check()

        # Should NOT mark as expired for transient errors
        mock_registry.mark_connection_expired.assert_not_awaited()

        # Should increment failure_count
        update_call = mock_client.table.return_value.update.call_args
        assert update_call is not None
        update_data = update_call[0][0]
        assert "last_health_check_at" in update_data
        assert update_data["failure_count"] == 2  # 1 + 1
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_ooda_connections.py::TestConnectionHealthCheck::test_health_check_increments_failure_count_on_transient_error -v`

Expected: PASS (implementation exists, just missing test coverage)

**Step 3: Commit**

```bash
git add backend/tests/test_ooda_connections.py
git commit -m "test: add transient error test for connection health check"
```

---

### Task 3: Verify All Tests Pass

**Step 1: Run full test class**

Run: `cd backend && pytest tests/test_ooda_connections.py::TestConnectionHealthCheck -v`

Expected: 4 tests pass
- `test_get_health_check_action_mapping`
- `test_health_check_marks_expired_on_auth_failure`
- `test_health_check_updates_timestamp_on_success`
- `test_health_check_increments_failure_count_on_transient_error`

**Step 2: Commit final state**

```bash
git add backend/tests/test_ooda_connections.py
git commit -m "test: complete connection health monitor test coverage"
```

---

## Summary

| Component | Status |
|-----------|--------|
| `_run_connection_health_check()` | ✅ Implemented |
| `_get_health_check_action()` | ✅ Implemented |
| APScheduler registration | ✅ Implemented |
| Test: toolkit mapping | ✅ Exists |
| Test: 401 marks expired | ✅ Exists |
| Test: success updates timestamp | ❌ Missing (Task 1) |
| Test: transient error increments failure_count | ❌ Missing (Task 2) |

This plan adds the 2 missing tests to achieve complete test coverage for all 3 user-specified scenarios.
