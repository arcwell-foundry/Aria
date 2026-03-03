# Calendar Integration Wiring Fix

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the calendar integration naming mismatch that causes calendar context to always be empty, then wire real calendar data into draft generation prompts.

**Architecture:** The `_get_calendar_integration()` method in `email_context_gatherer.py` searches for integration types `"googlecalendar"` and `"outlook365calendar"`, but the database stores `"outlook"` and `"google_calendar"` (per the `IntegrationType` enum in `domain.py`). Fix the lookup, add a calendar sync-to-local-cache path, add a test endpoint, and enhance the draft prompt to include free/busy windows.

**Tech Stack:** Python/FastAPI, Supabase (PostgreSQL), Composio SDK, Anthropic Claude API

---

### Task 1: Fix `_get_calendar_integration` lookup to match actual DB values

**Files:**
- Modify: `backend/src/services/email_context_gatherer.py:1577-1610`

**Step 1: Read the current implementation**

Read `backend/src/services/email_context_gatherer.py` lines 1577-1610 to confirm the current code.

**Step 2: Replace the two sequential `.eq()` queries with a single `.in_()` query**

Replace the entire `_get_calendar_integration` method (lines 1577-1610) with:

```python
async def _get_calendar_integration(self, user_id: str) -> dict[str, Any] | None:
    """Get user's calendar integration.

    Checks all known calendar integration type variants. The 'outlook'
    integration provides both email AND calendar via Microsoft Graph OAuth.
    """
    try:
        result = (
            self._db.table("user_integrations")
            .select("*")
            .eq("user_id", user_id)
            .in_(
                "integration_type",
                [
                    "google_calendar",
                    "googlecalendar",
                    "outlook",
                    "outlook365calendar",
                    "microsoft_calendar",
                ],
            )
            .eq("status", "active")
            .limit(1)
            .execute()
        )
        record = result.data[0] if result and result.data else None
        if record:
            return record

        logger.warning("No active calendar integration for user %s", user_id)
        return None

    except Exception:
        return None
```

**Step 3: Verify the provider routing still works**

The caller at line 1539-1548 routes to Google vs Outlook based on `"google" in provider`. With `integration_type="outlook"`, `provider` will be `"outlook"`, so `"google" not in "outlook"` → falls through to the `else` branch which calls `_fetch_outlook_calendar_events`. This is correct.

For `integration_type="google_calendar"`, `provider` will be `"google_calendar"`, so `"google" in "google_calendar"` → calls `_fetch_google_calendar_events`. Also correct.

**Step 4: Commit**

```bash
git add backend/src/services/email_context_gatherer.py
git commit -m "fix(calendar): match all integration_type variants in calendar lookup

The _get_calendar_integration method was checking for 'googlecalendar' and
'outlook365calendar' but the DB stores 'outlook' and 'google_calendar' per
the IntegrationType enum. Calendar context always returned None."
```

---

### Task 2: Fix scheduler calendar integration lookup

**Files:**
- Modify: `backend/src/services/scheduler.py:72-78`

**Step 1: Read the current implementation**

Read `backend/src/services/scheduler.py` lines 63-90.

**Step 2: Replace `.eq("integration_type", "google_calendar")` with `.in_()` covering all variants**

Replace lines 72-78:

```python
# Find users with active calendar integrations (any provider)
result = (
    db.table("user_integrations")
    .select("user_id")
    .in_(
        "integration_type",
        [
            "google_calendar",
            "googlecalendar",
            "outlook",
            "outlook365calendar",
            "microsoft_calendar",
        ],
    )
    .eq("status", "active")
    .execute()
)
```

**Step 3: Commit**

```bash
git add backend/src/services/scheduler.py
git commit -m "fix(calendar): include all integration type variants in scheduler meeting check"
```

---

### Task 3: Add calendar test endpoint to email routes

**Files:**
- Modify: `backend/src/api/routes/email.py` (add endpoint after the bootstrap section, around line 496)

**Step 1: Read the current end of the email routes file**

Read `backend/src/api/routes/email.py` from line 460 to the end of file.

**Step 2: Add the test endpoint**

After the `_run_email_bootstrap` function (around line 496), add:

```python
# ---------------------------------------------------------------------------
# Calendar Integration Test
# ---------------------------------------------------------------------------


@router.get("/calendar/test")
async def test_calendar_integration(current_user: CurrentUser) -> dict[str, Any]:
    """Test endpoint to verify calendar integration fetches real events.

    Returns calendar events from the user's connected calendar provider
    for the next 7 days. Also syncs fetched events to the local
    calendar_events table.
    """
    from datetime import timedelta

    from src.db.supabase import SupabaseClient
    from src.integrations.oauth import get_oauth_client

    user_id = current_user.id
    db = SupabaseClient.get_client()

    # 1. Find active calendar integration
    result = (
        db.table("user_integrations")
        .select("*")
        .eq("user_id", user_id)
        .in_(
            "integration_type",
            [
                "google_calendar",
                "googlecalendar",
                "outlook",
                "outlook365calendar",
                "microsoft_calendar",
            ],
        )
        .eq("status", "active")
        .limit(1)
        .execute()
    )

    if not result.data:
        return {
            "success": False,
            "error": "No active calendar integration found",
            "events": [],
            "synced": 0,
        }

    integration = result.data[0]
    connection_id = integration.get("composio_connection_id")
    integration_type = integration.get("integration_type", "").lower()

    if not connection_id:
        return {
            "success": False,
            "error": "Integration found but no composio_connection_id",
            "events": [],
            "synced": 0,
        }

    # 2. Fetch calendar events from provider
    now = datetime.now(UTC)
    end = now + timedelta(days=7)
    oauth_client = get_oauth_client()

    try:
        if "google" in integration_type:
            response = await oauth_client.execute_action(
                connection_id=connection_id,
                action="GOOGLECALENDAR_GET_EVENTS",
                params={
                    "timeMin": now.isoformat() + "Z",
                    "timeMax": end.isoformat() + "Z",
                    "maxResults": 50,
                },
                user_id=user_id,
            )
            raw_events = response.get("data", {}).get("items", [])
            events = [
                {
                    "external_id": ev.get("id", ""),
                    "title": ev.get("summary", "No title"),
                    "start_time": ev.get("start", {}).get("dateTime", ""),
                    "end_time": ev.get("end", {}).get("dateTime", ""),
                    "attendees": [
                        a.get("email", "") for a in ev.get("attendees", [])
                    ],
                }
                for ev in raw_events
            ]
        else:
            # Outlook
            response = await oauth_client.execute_action(
                connection_id=connection_id,
                action="OUTLOOK_GET_CALENDAR_VIEW",
                params={
                    "startDateTime": now.isoformat() + "Z",
                    "endDateTime": end.isoformat() + "Z",
                    "$top": 50,
                },
                user_id=user_id,
            )
            raw_events = response.get("data", {}).get("value", [])
            events = [
                {
                    "external_id": ev.get("id", ""),
                    "title": ev.get("subject", "No title"),
                    "start_time": ev.get("start", {}).get("dateTime", ""),
                    "end_time": ev.get("end", {}).get("dateTime", ""),
                    "attendees": [
                        a.get("emailAddress", {}).get("address", "")
                        for a in ev.get("attendees", [])
                    ],
                }
                for ev in raw_events
            ]
    except Exception as e:
        logger.error("Calendar test fetch failed: %s", e, exc_info=True)
        return {
            "success": False,
            "error": str(e),
            "connection_id": connection_id,
            "integration_type": integration_type,
            "events": [],
            "synced": 0,
        }

    # 3. Sync events to local calendar_events table
    synced = 0
    source = "google" if "google" in integration_type else "outlook"
    for ev in events:
        if not ev.get("external_id"):
            continue
        try:
            db.table("calendar_events").upsert(
                {
                    "user_id": user_id,
                    "title": ev["title"],
                    "start_time": ev["start_time"],
                    "end_time": ev.get("end_time"),
                    "attendees": json.dumps(ev.get("attendees", [])),
                    "source": source,
                    "external_id": ev["external_id"],
                    "metadata": json.dumps(ev),
                },
                on_conflict="user_id,external_id",
            ).execute()
            synced += 1
        except Exception as e:
            logger.warning("Failed to sync calendar event %s: %s", ev.get("external_id"), e)

    return {
        "success": True,
        "connection_id": connection_id,
        "integration_type": integration_type,
        "events": events,
        "event_count": len(events),
        "synced": synced,
    }
```

Also add `import json` to the imports at the top of the file (line 10 area) if not already present.

**Step 3: Verify Python syntax**

```bash
python3 -c "import ast; ast.parse(open('backend/src/api/routes/email.py').read()); print('OK')"
```

Expected: `OK`

**Step 4: Commit**

```bash
git add backend/src/api/routes/email.py
git commit -m "feat(calendar): add /email/calendar/test endpoint for verifying calendar fetch and sync"
```

---

### Task 4: Add calendar sync service method to email_context_gatherer

**Files:**
- Modify: `backend/src/services/email_context_gatherer.py` (add method after `_fetch_outlook_calendar_events`, around line 1707)

**Step 1: Read context around line 1707**

Read `backend/src/services/email_context_gatherer.py` lines 1700-1710 to find insertion point.

**Step 2: Add sync-to-local-cache method**

After the `_fetch_outlook_calendar_events` method (before the CRM Context section), add:

```python
async def _sync_events_to_cache(
    self,
    user_id: str,
    events: list[dict[str, Any]],
    source: str,
) -> int:
    """Sync fetched calendar events to the local calendar_events table.

    Uses upsert on (user_id, external_id) to avoid duplicates.

    Args:
        user_id: The user's ID.
        events: List of event dicts with id, title, start, end keys.
        source: Provider name ('google' or 'outlook').

    Returns:
        Number of events synced.
    """
    import json

    synced = 0
    for event in events:
        ext_id = event.get("id")
        if not ext_id:
            continue
        try:
            attendees = event.get("attendees_list", [])
            self._db.table("calendar_events").upsert(
                {
                    "user_id": user_id,
                    "title": event.get("title", ""),
                    "start_time": event.get("start", ""),
                    "end_time": event.get("end", ""),
                    "attendees": json.dumps(attendees),
                    "source": source,
                    "external_id": ext_id,
                    "metadata": json.dumps(event),
                },
                on_conflict="user_id,external_id",
            ).execute()
            synced += 1
        except Exception as e:
            logger.warning(
                "CONTEXT_GATHERER: Failed to cache calendar event %s: %s",
                ext_id,
                e,
            )
    return synced
```

**Step 3: Wire the sync into `_get_calendar_context`**

In `_get_calendar_context` (around line 1548), after events are fetched and before the for-loop that sorts them into recent/upcoming, add the sync call. After the line `events = await self._fetch_outlook_calendar_events(...)` (the else branch at ~line 1546-1548), add:

```python
            # Sync fetched events to local cache
            source = "google" if "google" in provider else "outlook"
            synced = await self._sync_events_to_cache(user_id, events, source)
            if synced:
                logger.info(
                    "CONTEXT_GATHERER: Synced %d calendar events to cache for user %s",
                    synced,
                    user_id,
                )
```

Insert this AFTER line 1548 (`events = await self._fetch_outlook_calendar_events(...)`) and BEFORE line 1550 (`for event in events:`).

**Step 4: Update Google and Outlook fetch methods to include attendees_list**

In `_fetch_google_calendar_events` (around line 1645-1650), update the events.append to include attendees_list:

```python
                        events.append({
                            "id": event.get("id"),
                            "title": event.get("summary", ""),
                            "start": event.get("start", {}).get("dateTime", ""),
                            "end": event.get("end", {}).get("dateTime", ""),
                            "attendees_list": [
                                a.get("email", "") for a in attendees
                            ],
                        })
```

In `_fetch_outlook_calendar_events` (around line 1693-1698), update similarly:

```python
                        events.append({
                            "id": event.get("id"),
                            "title": event.get("subject", ""),
                            "start": event.get("start", {}).get("dateTime", ""),
                            "end": event.get("end", {}).get("dateTime", ""),
                            "attendees_list": [
                                a.get("emailAddress", {}).get("address", "")
                                for a in attendees
                            ],
                        })
```

**Step 5: Verify Python syntax**

```bash
python3 -c "import ast; ast.parse(open('backend/src/services/email_context_gatherer.py').read()); print('OK')"
```

Expected: `OK`

**Step 6: Commit**

```bash
git add backend/src/services/email_context_gatherer.py
git commit -m "feat(calendar): sync fetched calendar events to local cache table"
```

---

### Task 5: Enhance draft prompt with full calendar free/busy context

**Files:**
- Modify: `backend/src/services/autonomous_draft_engine.py:1202-1209` (calendar section in `_build_reply_prompt`)

**Step 1: Read current calendar section**

Read `backend/src/services/autonomous_draft_engine.py` lines 1195-1240 to see the current calendar prompt injection.

**Step 2: Replace the minimal calendar section with full free/busy context**

Replace the calendar context block (lines 1202-1209) with:

```python
        # Calendar context — full free/busy for scheduling emails
        if context.calendar_context and context.calendar_context.connected:
            from datetime import timedelta

            cal = context.calendar_context
            all_meetings = cal.upcoming_meetings + cal.recent_meetings

            if all_meetings:
                # Build busy blocks
                busy_lines = []
                for m in sorted(all_meetings, key=lambda x: x.get("start", "")):
                    start_str = m.get("start", "TBD")
                    end_str = m.get("end", "")
                    title = m.get("title") or m.get("summary") or "Meeting"
                    if end_str:
                        busy_lines.append(f"- {start_str} to {end_str}: {title}")
                    else:
                        busy_lines.append(f"- {start_str}: {title}")

                busy_block = "\n".join(busy_lines) if busy_lines else "No meetings found."

                sections.append(f"""=== YOUR CALENDAR (NEXT 7 DAYS) ===
BUSY:
{busy_block}

When suggesting meeting times, ONLY suggest times that do NOT conflict with the BUSY blocks above. Prefer suggesting 2-3 specific available windows.""")
            else:
                sections.append("""=== CALENDAR ===
Your calendar is connected but no upcoming meetings were found in the next 7 days.
You can suggest meeting times freely.""")
```

**Step 3: Update the calendar guardrail condition**

In the LLM call section (around line 1085-1091), the guardrail currently fires when scheduling intent is detected but no calendar context exists. Now that calendar context will actually be populated, the guardrail becomes a safety net for edge cases. No change needed — the existing `_has_calendar_context` check at line 805-820 will correctly return True when `calendar_context.upcoming_meetings` has data or `"calendar"` is in `sources_used`.

**Step 4: Verify Python syntax**

```bash
python3 -c "import ast; ast.parse(open('backend/src/services/autonomous_draft_engine.py').read()); print('OK')"
```

Expected: `OK`

**Step 5: Commit**

```bash
git add backend/src/services/autonomous_draft_engine.py
git commit -m "feat(calendar): inject full free/busy context into draft generation prompt

When calendar is connected and has events, the LLM now sees actual busy
blocks and can suggest real available times instead of hallucinating."
```

---

### Task 6: Final syntax validation and integration commit

**Step 1: Validate all modified files compile**

```bash
cd backend
python3 -c "
import ast
files = [
    'src/services/email_context_gatherer.py',
    'src/services/autonomous_draft_engine.py',
    'src/services/scheduler.py',
    'src/api/routes/email.py',
]
for f in files:
    ast.parse(open(f).read())
    print(f'OK: {f}')
print('All files valid.')
"
```

Expected: All files print `OK`, then `All files valid.`

**Step 2: Final squash commit (if not already committed per task)**

If individual commits were made per task, this step is a no-op. Otherwise:

```bash
git add backend/src/services/email_context_gatherer.py \
       backend/src/services/autonomous_draft_engine.py \
       backend/src/services/scheduler.py \
       backend/src/api/routes/email.py
git commit -m "fix(calendar): wire calendar integration end-to-end

Four-part fix:
A. Fixed integration_type lookup to match actual DB values ('outlook',
   'google_calendar') instead of non-existent variants
B. Added /email/calendar/test endpoint to verify Composio calendar fetch
C. Added calendar event sync to local calendar_events cache table
D. Enhanced draft prompt with full free/busy calendar context

The calendar integration code existed but never ran because of naming
mismatches between the code and the database."
```
