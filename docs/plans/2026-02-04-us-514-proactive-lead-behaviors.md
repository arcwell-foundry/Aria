# US-514: Proactive Lead Behaviors Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a proactive lead behavior module that detects silent leads and health score drops, then sends notifications to users via the existing NotificationService.

**Architecture:** A new `LeadProactiveBehaviors` service class in `src/behaviors/lead_proactive.py` that:
1. Uses `LeadPatternDetector.find_silent_leads()` to detect inactive leads
2. Uses `HealthScoreCalculator._should_alert()` to detect health drops
3. Calls `NotificationService.create_notification()` to alert users

**Tech Stack:** Python 3.11+, pytest, existing NotificationService from Phase 4

---

## Context

### Existing Components

**Lead Pattern Detection** (`src/memory/lead_patterns.py`):
- `LeadPatternDetector.find_silent_leads(user_id, inactive_days=14)` returns `list[SilentLead]`
- `SilentLead` dataclass has: `lead_id`, `company_name`, `days_inactive`, `last_activity_at`, `health_score`

**Health Score Calculator** (`src/memory/health_score.py`):
- `HealthScoreCalculator._should_alert(current_score, history, threshold=20)` returns `bool`
- `HealthScoreHistory` dataclass has: `score`, `calculated_at`

**Notification Service** (`src/services/notification_service.py`):
- `NotificationService.create_notification(user_id, type, title, message, link, metadata)`
- Uses `NotificationType` enum from `src/models/notification.py`

### What Needs to Be Created

1. Add two new notification types: `LEAD_SILENT` and `LEAD_HEALTH_DROP`
2. Create `src/behaviors/` directory and `__init__.py`
3. Create `LeadProactiveBehaviors` service class
4. Write comprehensive tests

---

## Task 1: Add New NotificationType Values

**Files:**
- Modify: `backend/src/models/notification.py:13-21`
- Test: `backend/tests/test_notification_model.py` (create if needed)

**Step 1: Read the notification model file**

Run: Read `backend/src/models/notification.py`

**Step 2: Add new enum values**

Add `LEAD_SILENT` and `LEAD_HEALTH_DROP` to the `NotificationType` enum:

```python
class NotificationType(str, Enum):
    """Type of notification."""

    BRIEFING_READY = "briefing_ready"
    SIGNAL_DETECTED = "signal_detected"
    TASK_DUE = "task_due"
    MEETING_BRIEF_READY = "meeting_brief_ready"
    DRAFT_READY = "draft_ready"
    LEAD_SILENT = "lead_silent"
    LEAD_HEALTH_DROP = "lead_health_drop"
```

**Step 3: Run existing notification tests to verify no breakage**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_notification_service.py -v`
Expected: All existing tests pass

**Step 4: Commit**

```bash
git add backend/src/models/notification.py
git commit -m "feat(notifications): add LEAD_SILENT and LEAD_HEALTH_DROP types

Support proactive lead behavior alerts (US-514).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 2: Create Behaviors Directory Structure

**Files:**
- Create: `backend/src/behaviors/__init__.py`
- Create: `backend/tests/test_lead_proactive.py` (empty placeholder)

**Step 1: Create the behaviors directory**

Run: `mkdir -p /Users/dhruv/aria/backend/src/behaviors`

**Step 2: Create __init__.py**

```python
"""Behaviors module for ARIA proactive behaviors.

This module contains services that implement proactive, autonomous
behaviors that ARIA performs without explicit user request.
"""

from src.behaviors.lead_proactive import LeadProactiveBehaviors

__all__ = ["LeadProactiveBehaviors"]
```

Note: This will initially cause an import error until we create lead_proactive.py.

**Step 3: Create empty test file placeholder**

```python
"""Tests for LeadProactiveBehaviors service."""

# Tests will be added in subsequent tasks
```

**Step 4: Commit directory structure**

```bash
git add backend/src/behaviors/__init__.py backend/tests/test_lead_proactive.py
git commit -m "chore: add behaviors module structure for US-514

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 3: Write Tests for check_silent_leads

**Files:**
- Modify: `backend/tests/test_lead_proactive.py`

**Step 1: Write failing tests for check_silent_leads**

```python
"""Tests for LeadProactiveBehaviors service.

Tests the proactive lead monitoring behaviors:
- Silent lead detection and notification
- Health score drop detection and notification
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.memory.lead_patterns import SilentLead


class TestCheckSilentLeads:
    """Tests for check_silent_leads method."""

    @pytest.mark.asyncio
    async def test_check_silent_leads_sends_notifications(self):
        """Test that silent leads trigger notifications."""
        from src.behaviors.lead_proactive import LeadProactiveBehaviors
        from src.models.notification import NotificationType

        mock_db = MagicMock()
        service = LeadProactiveBehaviors(db_client=mock_db)

        now = datetime.now(UTC)
        silent_leads = [
            SilentLead(
                lead_id="lead-123",
                company_name="Acme Corp",
                days_inactive=21,
                last_activity_at=now - timedelta(days=21),
                health_score=45,
            ),
            SilentLead(
                lead_id="lead-456",
                company_name="Beta Inc",
                days_inactive=14,
                last_activity_at=now - timedelta(days=14),
                health_score=60,
            ),
        ]

        with patch.object(
            service, "_pattern_detector"
        ) as mock_detector, patch(
            "src.behaviors.lead_proactive.NotificationService"
        ) as mock_notification_service:
            mock_detector.find_silent_leads = AsyncMock(return_value=silent_leads)
            mock_notification_service.create_notification = AsyncMock()

            result = await service.check_silent_leads(user_id="user-abc")

            assert result == 2
            assert mock_notification_service.create_notification.call_count == 2

            # Check first notification
            first_call = mock_notification_service.create_notification.call_args_list[0]
            assert first_call.kwargs["user_id"] == "user-abc"
            assert first_call.kwargs["type"] == NotificationType.LEAD_SILENT
            assert "Acme Corp" in first_call.kwargs["title"]
            assert "21 days" in first_call.kwargs["message"]

    @pytest.mark.asyncio
    async def test_check_silent_leads_no_results(self):
        """Test check_silent_leads with no silent leads."""
        from src.behaviors.lead_proactive import LeadProactiveBehaviors

        mock_db = MagicMock()
        service = LeadProactiveBehaviors(db_client=mock_db)

        with patch.object(
            service, "_pattern_detector"
        ) as mock_detector, patch(
            "src.behaviors.lead_proactive.NotificationService"
        ) as mock_notification_service:
            mock_detector.find_silent_leads = AsyncMock(return_value=[])
            mock_notification_service.create_notification = AsyncMock()

            result = await service.check_silent_leads(user_id="user-abc")

            assert result == 0
            mock_notification_service.create_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_silent_leads_custom_threshold(self):
        """Test check_silent_leads with custom inactive days threshold."""
        from src.behaviors.lead_proactive import LeadProactiveBehaviors

        mock_db = MagicMock()
        service = LeadProactiveBehaviors(db_client=mock_db)

        with patch.object(
            service, "_pattern_detector"
        ) as mock_detector, patch(
            "src.behaviors.lead_proactive.NotificationService"
        ):
            mock_detector.find_silent_leads = AsyncMock(return_value=[])

            await service.check_silent_leads(user_id="user-abc", inactive_days=7)

            mock_detector.find_silent_leads.assert_called_once_with(
                user_id="user-abc",
                inactive_days=7,
            )
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_lead_proactive.py -v`
Expected: FAIL with ImportError (module doesn't exist yet)

**Step 3: Commit test file**

```bash
git add backend/tests/test_lead_proactive.py
git commit -m "test(lead-proactive): add tests for check_silent_leads

Red phase of TDD for US-514.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 4: Implement LeadProactiveBehaviors.check_silent_leads

**Files:**
- Create: `backend/src/behaviors/lead_proactive.py`

**Step 1: Create the service file with check_silent_leads**

```python
"""Proactive lead behavior monitoring for ARIA.

This module implements autonomous lead monitoring behaviors:
- Silent lead detection: Alert when leads are inactive for 14+ days
- Health drop detection: Alert when health score drops 20+ points

These behaviors run periodically (via scheduler) or on-demand and
send notifications via NotificationService.

Usage:
    ```python
    from src.db.supabase import SupabaseClient
    from src.behaviors.lead_proactive import LeadProactiveBehaviors

    client = SupabaseClient.get_client()
    service = LeadProactiveBehaviors(db_client=client)

    # Check for silent leads and send notifications
    count = await service.check_silent_leads(user_id="user-123")

    # Check for health drops and send notifications
    count = await service.check_health_drops(user_id="user-123")
    ```
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from src.memory.lead_patterns import LeadPatternDetector
from src.models.notification import NotificationType
from src.services.notification_service import NotificationService

if TYPE_CHECKING:
    from supabase import Client

logger = logging.getLogger(__name__)


class LeadProactiveBehaviors:
    """Service for proactive lead monitoring and alerting.

    Monitors leads for concerning patterns and sends notifications
    to users via NotificationService.
    """

    # Default thresholds
    DEFAULT_INACTIVE_DAYS = 14
    DEFAULT_HEALTH_DROP_THRESHOLD = 20

    def __init__(self, db_client: Client) -> None:
        """Initialize the proactive behaviors service.

        Args:
            db_client: Supabase client for database operations.
        """
        self._db = db_client
        self._pattern_detector = LeadPatternDetector(db_client=db_client)

    async def check_silent_leads(
        self,
        user_id: str,
        inactive_days: int = DEFAULT_INACTIVE_DAYS,
    ) -> int:
        """Check for silent leads and send notifications.

        Finds leads that have been inactive for the specified number of days
        and sends a notification for each one.

        Args:
            user_id: The user to check leads for.
            inactive_days: Days of inactivity to trigger alert (default 14).

        Returns:
            Number of notifications sent.
        """
        silent_leads = await self._pattern_detector.find_silent_leads(
            user_id=user_id,
            inactive_days=inactive_days,
        )

        if not silent_leads:
            logger.debug(
                "No silent leads found",
                extra={"user_id": user_id, "inactive_days": inactive_days},
            )
            return 0

        notification_count = 0

        for lead in silent_leads:
            # Determine recommended action based on inactivity
            if lead.days_inactive >= 30:
                action = "Consider scheduling a check-in call"
            elif lead.days_inactive >= 21:
                action = "Send a follow-up email to re-engage"
            else:
                action = "Review lead status and plan next touchpoint"

            try:
                await NotificationService.create_notification(
                    user_id=user_id,
                    type=NotificationType.LEAD_SILENT,
                    title=f"Silent Lead: {lead.company_name}",
                    message=f"No activity for {lead.days_inactive} days. {action}",
                    link=f"/leads/{lead.lead_id}",
                    metadata={
                        "lead_id": lead.lead_id,
                        "company_name": lead.company_name,
                        "days_inactive": lead.days_inactive,
                        "health_score": lead.health_score,
                    },
                )
                notification_count += 1
            except Exception as e:
                logger.warning(
                    "Failed to send silent lead notification",
                    extra={
                        "user_id": user_id,
                        "lead_id": lead.lead_id,
                        "error": str(e),
                    },
                )

        logger.info(
            "Checked silent leads",
            extra={
                "user_id": user_id,
                "silent_count": len(silent_leads),
                "notifications_sent": notification_count,
            },
        )

        return notification_count
```

**Step 2: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_lead_proactive.py::TestCheckSilentLeads -v`
Expected: All 3 tests pass

**Step 3: Commit implementation**

```bash
git add backend/src/behaviors/lead_proactive.py
git commit -m "feat(lead-proactive): implement check_silent_leads

Detects inactive leads and sends notifications via NotificationService.
Part of US-514 proactive lead behaviors.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 5: Write Tests for check_health_drops

**Files:**
- Modify: `backend/tests/test_lead_proactive.py`

**Step 1: Add tests for check_health_drops**

Append to test file:

```python
class TestCheckHealthDrops:
    """Tests for check_health_drops method."""

    @pytest.mark.asyncio
    async def test_check_health_drops_sends_notification(self):
        """Test that health drops trigger notifications."""
        from src.behaviors.lead_proactive import LeadProactiveBehaviors
        from src.memory.health_score import HealthScoreHistory
        from src.models.notification import NotificationType

        mock_db = MagicMock()
        service = LeadProactiveBehaviors(db_client=mock_db)

        now = datetime.now(UTC)

        # Mock database response for active leads with health drops
        mock_leads_response = MagicMock()
        mock_leads_response.data = [
            {
                "id": "lead-123",
                "company_name": "Acme Corp",
                "health_score": 50,
            },
            {
                "id": "lead-456",
                "company_name": "Beta Inc",
                "health_score": 40,
            },
        ]

        # Mock health score history showing drops
        mock_history_response = MagicMock()
        mock_history_response.data = [
            # lead-123: dropped from 75 to 50 (25 points)
            {"lead_memory_id": "lead-123", "score": 75, "calculated_at": (now - timedelta(days=1)).isoformat()},
            # lead-456: dropped from 55 to 40 (15 points - below threshold)
            {"lead_memory_id": "lead-456", "score": 55, "calculated_at": (now - timedelta(days=1)).isoformat()},
        ]

        # Setup mock chain
        mock_table = MagicMock()
        mock_table.select.return_value.eq.return_value.execute.return_value = mock_leads_response
        mock_table.select.return_value.in_.return_value.order.return_value.execute.return_value = mock_history_response
        mock_db.table.return_value = mock_table

        with patch(
            "src.behaviors.lead_proactive.NotificationService"
        ) as mock_notification_service:
            mock_notification_service.create_notification = AsyncMock()

            result = await service.check_health_drops(user_id="user-abc")

            # Only 1 notification (lead-123 dropped 25 points, lead-456 only 15)
            assert result == 1
            assert mock_notification_service.create_notification.call_count == 1

            call = mock_notification_service.create_notification.call_args
            assert call.kwargs["type"] == NotificationType.LEAD_HEALTH_DROP
            assert "Acme Corp" in call.kwargs["title"]
            assert "25" in call.kwargs["message"]  # Drop amount

    @pytest.mark.asyncio
    async def test_check_health_drops_no_drops(self):
        """Test check_health_drops with no significant drops."""
        from src.behaviors.lead_proactive import LeadProactiveBehaviors

        mock_db = MagicMock()
        service = LeadProactiveBehaviors(db_client=mock_db)

        # No active leads
        mock_leads_response = MagicMock()
        mock_leads_response.data = []
        mock_db.table.return_value.select.return_value.eq.return_value.execute.return_value = mock_leads_response

        with patch(
            "src.behaviors.lead_proactive.NotificationService"
        ) as mock_notification_service:
            mock_notification_service.create_notification = AsyncMock()

            result = await service.check_health_drops(user_id="user-abc")

            assert result == 0
            mock_notification_service.create_notification.assert_not_called()

    @pytest.mark.asyncio
    async def test_check_health_drops_custom_threshold(self):
        """Test check_health_drops with custom threshold."""
        from src.behaviors.lead_proactive import LeadProactiveBehaviors
        from src.memory.health_score import HealthScoreCalculator

        mock_db = MagicMock()
        service = LeadProactiveBehaviors(db_client=mock_db)

        now = datetime.now(UTC)

        mock_leads_response = MagicMock()
        mock_leads_response.data = [
            {"id": "lead-123", "company_name": "Acme Corp", "health_score": 50},
        ]

        mock_history_response = MagicMock()
        mock_history_response.data = [
            {"lead_memory_id": "lead-123", "score": 60, "calculated_at": (now - timedelta(days=1)).isoformat()},
        ]

        mock_table = MagicMock()
        mock_table.select.return_value.eq.return_value.execute.return_value = mock_leads_response
        mock_table.select.return_value.in_.return_value.order.return_value.execute.return_value = mock_history_response
        mock_db.table.return_value = mock_table

        with patch(
            "src.behaviors.lead_proactive.NotificationService"
        ) as mock_notification_service:
            mock_notification_service.create_notification = AsyncMock()

            # With threshold of 10, a drop of 10 points should trigger notification
            result = await service.check_health_drops(
                user_id="user-abc",
                threshold=10,
            )

            assert result == 1
```

**Step 2: Run tests to verify they fail**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_lead_proactive.py::TestCheckHealthDrops -v`
Expected: FAIL with AttributeError (method doesn't exist)

**Step 3: Commit tests**

```bash
git add backend/tests/test_lead_proactive.py
git commit -m "test(lead-proactive): add tests for check_health_drops

Red phase of TDD for health drop notifications (US-514).

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 6: Implement check_health_drops

**Files:**
- Modify: `backend/src/behaviors/lead_proactive.py`

**Step 1: Add check_health_drops method**

Add after `check_silent_leads` method:

```python
    async def check_health_drops(
        self,
        user_id: str,
        threshold: int = DEFAULT_HEALTH_DROP_THRESHOLD,
    ) -> int:
        """Check for leads with significant health score drops.

        Compares current health scores to recent history and sends
        notifications for leads that have dropped by the threshold or more.

        Args:
            user_id: The user to check leads for.
            threshold: Minimum score drop to trigger alert (default 20).

        Returns:
            Number of notifications sent.
        """
        from src.memory.health_score import HealthScoreCalculator, HealthScoreHistory

        # Get active leads for user with current health scores
        leads_response = (
            self._db.table("lead_memories")
            .select("id, company_name, health_score")
            .eq("user_id", user_id)
            .eq("status", "active")
            .execute()
        )

        if not leads_response.data:
            return 0

        lead_ids = [lead["id"] for lead in leads_response.data]
        lead_map = {lead["id"]: lead for lead in leads_response.data}

        # Get recent health score history for these leads
        history_response = (
            self._db.table("health_score_history")
            .select("lead_memory_id, score, calculated_at")
            .in_("lead_memory_id", lead_ids)
            .order("calculated_at", desc=True)
            .execute()
        )

        # Group history by lead_id and build HealthScoreHistory objects
        history_by_lead: dict[str, list[HealthScoreHistory]] = {}
        for item in history_response.data or []:
            lead_id = item["lead_memory_id"]
            if lead_id not in history_by_lead:
                history_by_lead[lead_id] = []
            history_by_lead[lead_id].append(
                HealthScoreHistory(
                    score=item["score"],
                    calculated_at=datetime.fromisoformat(item["calculated_at"]),
                )
            )

        calculator = HealthScoreCalculator()
        notification_count = 0

        for lead_id, lead_data in lead_map.items():
            current_score = lead_data.get("health_score", 0) or 0
            history = history_by_lead.get(lead_id, [])

            if not history:
                continue

            # Use calculator's alert logic
            if calculator._should_alert(current_score, history, threshold=threshold):
                # Calculate the actual drop for the message
                previous_score = max(history, key=lambda h: h.calculated_at).score
                drop_amount = previous_score - current_score

                # Determine recommended action based on drop severity
                if drop_amount >= 30:
                    action = "Immediate attention required - major engagement issue"
                elif drop_amount >= 25:
                    action = "Review recent interactions for concerns"
                else:
                    action = "Check for engagement opportunities"

                try:
                    await NotificationService.create_notification(
                        user_id=user_id,
                        type=NotificationType.LEAD_HEALTH_DROP,
                        title=f"Health Drop: {lead_data['company_name']}",
                        message=f"Health score dropped {drop_amount} points (from {previous_score} to {current_score}). {action}",
                        link=f"/leads/{lead_id}",
                        metadata={
                            "lead_id": lead_id,
                            "company_name": lead_data["company_name"],
                            "current_score": current_score,
                            "previous_score": previous_score,
                            "drop_amount": drop_amount,
                        },
                    )
                    notification_count += 1
                except Exception as e:
                    logger.warning(
                        "Failed to send health drop notification",
                        extra={
                            "user_id": user_id,
                            "lead_id": lead_id,
                            "error": str(e),
                        },
                    )

        logger.info(
            "Checked health drops",
            extra={
                "user_id": user_id,
                "leads_checked": len(lead_map),
                "notifications_sent": notification_count,
            },
        )

        return notification_count
```

Also add the missing import at the top:

```python
from datetime import datetime
```

**Step 2: Run tests to verify they pass**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_lead_proactive.py::TestCheckHealthDrops -v`
Expected: All 3 tests pass

**Step 3: Commit implementation**

```bash
git add backend/src/behaviors/lead_proactive.py
git commit -m "feat(lead-proactive): implement check_health_drops

Detects significant health score drops and sends notifications.
Uses HealthScoreCalculator._should_alert() for threshold logic.
Part of US-514 proactive lead behaviors.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Task 7: Run All Tests and Verify

**Files:**
- None (verification only)

**Step 1: Run all lead_proactive tests**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_lead_proactive.py -v`
Expected: All 6 tests pass

**Step 2: Run related tests to check for regressions**

Run: `cd /Users/dhruv/aria/backend && python -m pytest tests/test_notification_service.py tests/test_health_score.py tests/test_lead_patterns.py -v`
Expected: All tests pass

**Step 3: Run mypy type check**

Run: `cd /Users/dhruv/aria/backend && python -m mypy src/behaviors/lead_proactive.py --strict`
Expected: No errors

**Step 4: Run ruff check and format**

Run: `cd /Users/dhruv/aria/backend && python -m ruff check src/behaviors/ && python -m ruff format src/behaviors/`
Expected: No linting errors

---

## Task 8: Update behaviors __init__.py and Final Commit

**Files:**
- Modify: `backend/src/behaviors/__init__.py`

**Step 1: Update __init__.py with proper import**

The __init__.py we created earlier imports LeadProactiveBehaviors, so verify it works:

```python
"""Behaviors module for ARIA proactive behaviors.

This module contains services that implement proactive, autonomous
behaviors that ARIA performs without explicit user request.
"""

from src.behaviors.lead_proactive import LeadProactiveBehaviors

__all__ = ["LeadProactiveBehaviors"]
```

**Step 2: Test import works**

Run: `cd /Users/dhruv/aria/backend && python -c "from src.behaviors import LeadProactiveBehaviors; print('Import OK')"`
Expected: "Import OK"

**Step 3: Final commit**

```bash
git add backend/src/behaviors/__init__.py
git commit -m "feat(behaviors): complete US-514 proactive lead behaviors

Implements:
- Silent lead detection (14+ days inactive)
- Health score drop detection (20+ point drops)
- Notification integration via NotificationService

Closes #514

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
```

---

## Summary

This plan creates US-514 Proactive Lead Behaviors with:

1. **New notification types**: `LEAD_SILENT` and `LEAD_HEALTH_DROP`
2. **New behaviors module**: `src/behaviors/lead_proactive.py`
3. **Two main methods**:
   - `check_silent_leads()`: Finds inactive leads and sends notifications
   - `check_health_drops()`: Finds health score drops and sends notifications
4. **Full test coverage**: 6 tests covering both methods
5. **TDD approach**: Tests written before implementation

**Note on US-505**: The `analyze_event()` method in `conversation_intelligence.py` is already fully implemented with Claude API integration. No changes needed there.
