# ARIA Email Intelligence Pipeline — Forensic Audit Report

**Date:** 2026-03-03
**Auditor:** Claude Code (Opus 4.6)
**Status:** Complete — code path tracing with evidence; database queries FAILED (Supabase MCP connection error)

---

## 1. DATABASE STATE

**All 12 Supabase queries returned: `MCP error -32603: Tenant or user not found`**

This means the Supabase MCP tool is misconfigured or the project reference is invalid. No database evidence was gathered. All findings below are from code analysis only. Database-dependent conclusions are marked 🔍.

**Tables referenced but unverifiable:**
- `email_processing_runs` — run tracking
- `email_scan_log` — categorization decisions
- `email_drafts` — generated drafts
- `draft_context` — context metadata
- `recipient_style_profiles` — per-contact style (referenced in code but never queried by context gatherer — see Section 4)
- `deferred_email_drafts` — active conversation deferrals
- `user_settings` — preferences, fingerprint, calibration
- `user_integrations` — OAuth connections
- `digital_twin_profiles` — fallback style data
- `calendar_events` — local calendar cache (used by urgency detector)

---

## 2. PIPELINE MAP — Actual Runtime Flow

### Entry Points (4 triggers identified)

| # | Trigger | File:Line | Interval | Concurrency Guard? | Creates Run? |
|---|---------|-----------|----------|-------------------|-------------|
| 1 | **API endpoint** `POST /email/scan-now` | `api/routes/email.py:65` | User-initiated | 60-second rate limit + `_is_run_active()` | Yes |
| 2 | **Periodic scheduler** via APScheduler | `services/scheduler.py:1602-1607` | Every **15 minutes** | 30-min watermark gap check + `_is_run_active()` | Yes (indirect via `process_inbox`) |
| 3 | **Composio webhook** `POST /webhooks/composio` | `api/routes/composio_webhooks.py:58` | On each new email | ❌ **NO** — creates Pulse signal only, does NOT trigger draft pipeline | No |
| 4 | **Deferred draft retry** via APScheduler | `services/scheduler.py:1617-1621` | Every **15 minutes** | 🔍 Unknown — need to read `deferred_draft_retry_job.py` | 🔍 |

**Critical Finding:** Trigger #3 (Composio webhook) does NOT trigger `process_inbox()`. The `EmailEventHandler` at `services/event_handlers/email_handler.py:11` only creates a Pulse signal — it does NOT call `AutonomousDraftEngine.process_inbox()`. Email drafting is triggered ONLY by triggers #1 and #2.

### Complete Pipeline Flow

```
[Trigger #1: POST /email/scan-now OR Trigger #2: APScheduler every 15 min]
  │
  ├── Rate limit check (60s window, API only)                    ✅ Confirmed: email.py:109-142
  │
  ├── engine.process_inbox(user_id, since_hours)                 ✅ Confirmed: autonomous_draft_engine.py:147
  │   │
  │   ├── _cleanup_stale_runs(user_id)                           ✅ Confirmed: :1033 — marks >10min running → failed
  │   │
  │   ├── _is_run_active(user_id)                                ✅ Confirmed: :999 — checks status='running'
  │   │   └── If active run exists → return "skipped"            ✅ Confirmed: :174-184
  │   │
  │   ├── _create_processing_run(run_id, user_id)                ✅ Confirmed: :1051
  │   │
  │   ├── EmailAnalyzer.scan_inbox(user_id, since_hours)         ✅ Confirmed: :198
  │   │   │
  │   │   ├── _load_exclusions(user_id)                          ✅ Confirmed: email_analyzer.py:183-184
  │   │   │
  │   │   ├── _fetch_inbox_emails(user_id, since_hours)          ✅ Confirmed: :192
  │   │   │   │
  │   │   │   ├── Query user_integrations for outlook/gmail      ✅ Confirmed: :785-806
  │   │   │   │   └── Checks status='active'                     ✅ Confirmed: :789, :802
  │   │   │   │
  │   │   │   ├── Outlook: OUTLOOK_GET_MAIL_DELTA                ✅ Confirmed: :848
  │   │   │   │   └── $filter: receivedDateTime ge {since_date}  ✅ Confirmed: :851
  │   │   │   │
  │   │   │   └── Gmail: GMAIL_FETCH_EMAILS                      ✅ Confirmed: :887
  │   │   │       └── query: after:{since_epoch}                 ✅ Confirmed: :891
  │   │   │
  │   │   └── For each email → categorize_email()                ✅ Confirmed: :207
  │   │       │
  │   │       ├── Filter 1: Privacy exclusions                   ✅ Confirmed: :283
  │   │       ├── Filter 2: No-reply/automated sender            ✅ Confirmed: :300
  │   │       ├── Filter 3: Newsletter/mailing list headers      ✅ Confirmed: :317
  │   │       ├── Filter 4: CC-only (user not in To:)            ✅ Confirmed: :337
  │   │       ├── Filter 5: Self-sent detection                  ✅ Confirmed: :357
  │   │       ├── Filter 6: Calendar responses                   ✅ Confirmed: :374
  │   │       ├── Filter 7: Junk/spam notifications              ✅ Confirmed: :391
  │   │       ├── Filter 8: Bounce/undeliverable                 ✅ Confirmed: :408
  │   │       ├── Filter 9: Read receipts                        ✅ Confirmed: :425
  │   │       ├── Filter 10: Auto-generated messages             ✅ Confirmed: :442
  │   │       │
  │   │       ├── _lookup_sender_relationship()                  ✅ Confirmed: :461
  │   │       ├── _llm_classify() → JSON {category, urgency...}  ✅ Confirmed: :465
  │   │       ├── detect_urgency() signal override               ✅ Confirmed: :481
  │   │       └── _log_scan_decision() → email_scan_log          ✅ Confirmed: :220
  │   │
  │   ├── _group_emails_by_thread(needs_reply)                   ✅ Confirmed: :258
  │   │
  │   └── For each thread_id → thread_emails:
  │       │
  │       ├── _check_existing_draft(user_id, thread_id, ids)     ✅ Confirmed: :270
  │       │   └── Checks email_drafts for thread_id OR           ✅ Confirmed: :1157-1174
  │       │       original_email_id, status IN [draft,saved],
  │       │       user_action IS NULL
  │       │   └── If exists → SKIP thread                        ✅ Confirmed: :273-281
  │       │
  │       ├── _get_latest_email_in_thread()                      ✅ Confirmed: :284
  │       │
  │       ├── _is_active_conversation(user_id, thread_id)        ✅ Confirmed: :287
  │       │   └── 3+ messages from 2+ senders in last hour       ✅ Confirmed: :1236-1275
  │       │   └── If active → _defer_draft() + SKIP              ✅ Confirmed: :290-297
  │       │
  │       ├── Learning mode filter (if active)                   ✅ Confirmed: :301-313
  │       │
  │       └── _process_single_email(user_id, email...)           ✅ Confirmed: :328
  │           │
  │           ├── (a) EmailContextGatherer.gather_context()      ✅ Confirmed: :434
  │           │   │
  │           │   ├── Source 1: _fetch_thread() via Composio     ✅ Confirmed: ECG:274
  │           │   ├── Source 1b: _extract_commitments()          ✅ Confirmed: ECG:281
  │           │   ├── Source 2: _research_recipient() via Exa    ✅ Confirmed: ECG:300
  │           │   ├── Source 3: _get_recipient_style()           ✅ Confirmed: ECG:307
  │           │   ├── Source 4: _get_relationship_history()      ✅ Confirmed: ECG:312
  │           │   ├── Source 4b: _get_relationship_health()      ✅ Confirmed: ECG:335
  │           │   ├── Source 5: _get_corporate_memory()          ✅ Confirmed: ECG:342
  │           │   ├── Source 6: _get_calendar_context()          ✅ Confirmed: ECG:349
  │           │   │   └── Queries googlecalendar/outlook365calendar ✅ Confirmed: ECG:1584/1597
  │           │   │   └── Fetches ±30 day events via Composio    ✅ Confirmed: ECG:1536-1537
  │           │   │   └── Filters events with sender as attendee ✅ Confirmed: (implied by sender_email param)
  │           │   ├── Source 7: _get_crm_context()               ✅ Confirmed: ECG:354
  │           │   └── _save_context() to draft_context table     ✅ Confirmed: ECG:361
  │           │
  │           ├── (b) DigitalTwin.get_style_guidelines()         ✅ Confirmed: :470
  │           │   ├── Try 1: user_settings fingerprint (21 fields) ✅ digital_twin.py:1008-1012
  │           │   ├── Try 2: Graphiti knowledge graph            ✅ digital_twin.py:1022-1024
  │           │   ├── Try 3: digital_twin_profiles table         ✅ digital_twin.py:1037
  │           │   └── Try 4: Default generic guidelines          ✅ digital_twin.py:1041
  │           │
  │           ├── (c) PersonalityCalibrator.get_calibration()    ✅ Confirmed: :473
  │           │   ├── Try 1: user_settings.personality_calibration ✅ personality_calibrator.py:537-552
  │           │   └── Try 2: Synthesize from digital_twin_profiles ✅ personality_calibrator.py:556-561
  │           │
  │           ├── (d) _generate_reply_draft() via LLM            ✅ Confirmed: :481
  │           │   ├── _build_reply_prompt() assembles context     ✅ Confirmed: :652-654
  │           │   │   ├── ORIGINAL EMAIL section                  ✅ Confirmed: :722-726
  │           │   │   ├── CONVERSATION THREAD section (if msgs)   ✅ Confirmed: :729-741
  │           │   │   ├── ABOUT THE RECIPIENT section (if research) ✅ Confirmed: :744-754
  │           │   │   ├── RELATIONSHIP HISTORY section (if facts) ✅ Confirmed: :757-763
  │           │   │   ├── RECIPIENT'S COMMUNICATION STYLE section ✅ Confirmed: :766-770
  │           │   │   ├── YOUR WRITING STYLE section (always)     ✅ Confirmed: :773-774
  │           │   │   ├── TONE GUIDANCE section (if exists)       ✅ Confirmed: :777-779
  │           │   │   ├── UPCOMING MEETINGS section (if meetings) ✅ Confirmed: :782-788
  │           │   │   ├── CRM STATUS section (if connected)       ✅ Confirmed: :791-798
  │           │   │   └── YOUR INFO + TASK section                ✅ Confirmed: :801-808
  │           │   │
  │           │   ├── PersonaBuilder system prompt (primary)      ✅ Confirmed: :658-669
  │           │   ├── Fallback reply prompt (if PersonaBuilder fails) ✅ Confirmed: :657
  │           │   │
  │           │   ├── LLM call: temperature=0.7, no explicit model ✅ Confirmed: :673-677
  │           │   │
  │           │   ├── Strip markdown code fences from response    ✅ Confirmed: :680-688
  │           │   ├── json.loads(text) → {subject, body}          ✅ Confirmed: :690-695
  │           │   └── FALLBACK: json.JSONDecodeError → raw text   ⚠️ BUG: :696-705
  │           │       └── body = text (raw LLM output as-is)
  │           │
  │           ├── (e) DigitalTwin.score_style_match()             ✅ Confirmed: :486
  │           ├── (f) _calculate_confidence()                     ✅ Confirmed: :489
  │           ├── (g) _generate_aria_notes()                      ✅ Confirmed: :499
  │           │
  │           ├── (h) _save_draft_with_metadata() → email_drafts  ✅ Confirmed: :504
  │           │   └── Sets: thread_id, original_email_id, status='draft',
  │           │       style_match_score, confidence_level, aria_notes,
  │           │       processing_run_id
  │           │
  │           ├── (i) EmailClientWriter.save_draft_to_client()    ✅ Confirmed: :530
  │           │   ├── Gmail: GMAIL_CREATE_EMAIL_DRAFT             ✅ email_client_writer.py:224
  │           │   │   └── Passes thread_id for threading          ✅ :211-212
  │           │   ├── Outlook: OUTLOOK_CREATE_DRAFT               ✅ email_client_writer.py:279
  │           │   │   └── Does NOT pass conversationId            ⚠️ BUG: :264-269
  │           │   └── Updates email_drafts: saved_to_client=True  ✅ :354-374
  │           │
  │           └── (j) ActivityService.record() → aria_activity    ✅ Confirmed: :561
  │
  └── _update_processing_run(result) in finally block            ✅ Confirmed: :396
```

---

## 3. ROOT CAUSES — Bug-by-Bug Analysis

### Bug 1: Duplicate Drafts (6+ for same thread in 2 minutes)

**Root Cause: Time-window overlap, NOT missing dedup**

The deduplication check at `autonomous_draft_engine.py:1135-1184` IS called and IS functional. It checks `email_drafts` for existing drafts with matching `thread_id` OR `original_email_id` in statuses `[draft, saved_to_client]` where `user_action IS NULL`.

**Why duplicates still occur:**

1. **Watermark is time-based, not message-ID-based.** The `since_hours` parameter at `email_analyzer.py:163` defaults to 24 hours. Every scan fetches ALL emails from the last 24 hours via `$filter: receivedDateTime ge {since_date}` (Outlook, :851) or `query: after:{since_epoch}` (Gmail, :891). There is **no advancing watermark** — the same emails are fetched on every run.

2. **Dedup protects within a single run but has a race window.** The check at `:1165-1174` queries `email_drafts` before generating. If two runs overlap (trigger #1 and #2 fire near-simultaneously), both can pass the dedup check before either inserts the draft.

3. **The periodic job runs every 15 minutes** (`scheduler.py:1604`), but `_calculate_hours_since_last_run()` in `periodic_email_check.py:213` only skips if last run was <30 minutes ago. With a 15-minute interval and a 30-minute threshold, this should gate correctly — but the API endpoint has only a 60-second gate. If a user hits "scan now" twice within the 60-second window's edge case, and the scheduler also fires, overlapping runs are possible.

4. **The `_is_run_active()` check at `:999-1031` prevents truly concurrent runs** by checking for `status='running'`. However, if a run completes quickly and another starts immediately, both may process the same emails from the same 24-hour window.

**Evidence needed (requires DB):** 🔍 Query `email_drafts` for duplicate `thread_id` values with `created_at` gap <2 minutes. Query `email_processing_runs` for overlapping `started_at` timestamps.

**Verdict:** The dedup IS wired up. The root cause is that every run re-fetches the same 24-hour window of emails. After a draft is saved, subsequent runs should (and do) skip that thread via the dedup check. Duplicates would only occur from race conditions between concurrent triggers or if `user_action` gets set unexpectedly.

### Bug 2: Raw JSON in Draft Bodies

**Root Cause: Confirmed at `autonomous_draft_engine.py:696-705`**

```python
except json.JSONDecodeError:
    # Fallback: use raw response as body
    logger.warning(...)
    return ReplyDraftContent(
        subject=f"Re: {email.subject}",
        body=text,  # ← raw LLM text (may still contain JSON-like content)
    )
```

The code at `:680-688` strips markdown fences (```` ```json ... ``` ````), but if the LLM returns malformed JSON that partially looks like JSON (e.g., missing a closing brace, or extra text before/after the JSON), `json.loads()` fails and the **entire raw text becomes the draft body**.

**The Feb 28 fix** (markdown fence stripping at `:681-688`) only handles the ```` ``` ```` wrapper. If the LLM returns `Here is the reply: {"subject": "Re:...", "body": "..."}`, the fence stripping does nothing, `json.loads` fails on the prefix text, and the entire string (including the JSON envelope) becomes the body.

**Additional code path:** The prompt at `:807` says `Respond with JSON: {"subject": "...", "body": "..."}` and `_REPLY_TASK_INSTRUCTIONS` at `:115-129` says `Your response MUST be valid JSON`. But with `temperature=0.7` (`:676`), the LLM occasionally wraps the JSON in explanation text.

### Bug 3: Hallucinated Calendar Availability

**Root Cause: Missing explicit guidance when calendar data is absent**

Calendar integration IS implemented at `email_context_gatherer.py:1500-1575`. It:
1. Queries `user_integrations` for `googlecalendar` or `outlook365calendar` (`:1584, :1597`)
2. Fetches ±30 day events via Composio
3. Filters events where sender is an attendee
4. Populates `context.calendar_context.upcoming_meetings`

**The problem is what happens when calendar is NOT connected:**
- `_get_calendar_integration()` returns `None` (`:1521`)
- `context.calendar_context` stays at defaults: `connected=False`, `upcoming_meetings=[]`
- The `UPCOMING MEETINGS` section is **omitted entirely** from the prompt (`:782-788`)
- The LLM prompt has **no explicit instruction** to say "I don't have calendar access" when asked about availability
- A helpful LLM will invent times to answer "When are you free?"

**Also:** The integration type query checks `googlecalendar` and `outlook365calendar` — but the scheduler at `scheduler.py:77` checks `google_calendar`. This naming inconsistency means the calendar meeting brief job and the email context gatherer may disagree about whether calendar is connected.

### Bug 4: Drafts for Already-Replied Emails

**Root Cause: NO sent-folder reply check exists in the pipeline**

The pipeline has **no tier for checking if the user already replied**. There is:

1. **No sent-folder scan** — There is no code in `AutonomousDraftEngine` or `EmailAnalyzer` that calls Composio to check the sent folder for replies. The `_find_in_sent_folder()` method exists in `draft_feedback_tracker.py:283` but it's used for post-hoc draft feedback, NOT for pre-draft reply checking.

2. **No thread message scan for user replies** — The `EmailContextGatherer._fetch_thread()` fetches thread messages and marks `is_from_user=True` on `ThreadMessage` objects, but this information is used for **context** only, not to prevent drafting.

3. **The dedup check only prevents duplicate ARIA drafts** — `_check_existing_draft()` at `:1135` checks `email_drafts` for existing ARIA-generated drafts. It does NOT check whether the user manually sent a reply.

The entire "3-tier reply check" described in the audit prompt **does not exist**. The only protection is: if a user replied and ARIA already drafted for that thread, the dedup check prevents a second ARIA draft. But if the user replied WITHOUT ARIA having drafted first, ARIA will still generate a draft for a thread the user already handled.

---

## 4. MISSING WIRING — Code Exists But Not Called

| Component | File | Status |
|-----------|------|--------|
| `DraftFeedbackTracker._find_in_sent_folder()` | `services/draft_feedback_tracker.py:283` | Exists for feedback polling, NOT used for pre-draft checks |
| `ThreadMessage.is_from_user` | `services/email_context_gatherer.py:43` | Set during thread fetch, but never checked to prevent drafting |
| `_PERSONAL_DOMAINS` set | `services/email_context_gatherer.py:207-227` | Used for company research filtering, NOT for draft decisions |
| `EmailEventHandler.process()` | `services/event_handlers/email_handler.py:18` | Creates Pulse signal only — does NOT trigger draft pipeline |
| `recipient_style_profiles` table | referenced in `CLAUDE.md` | `_get_recipient_style()` queries `recipient_writing_profiles` — name may differ from actual table |

---

## 5. MISSING COMPONENTS — Don't Exist Yet

| Feature | Status | Impact |
|---------|--------|--------|
| **Sent-folder reply check** | ❌ Does not exist | Drafts generated for already-replied threads |
| **Message-ID-based watermark** | ❌ Only time-based `since_hours` | Same emails re-fetched every run |
| **Calendar unavailable guidance** | ❌ No prompt instruction | LLM hallucinates times |
| **Scheduling intent detection** | ❌ Not implemented | No special handling for "when are you free?" emails |
| **JSON extraction with regex fallback** | ❌ Only `json.loads()` + raw fallback | Raw JSON in draft bodies |
| **Outlook thread linking** | ❌ `conversationId` not passed to `OUTLOOK_CREATE_DRAFT` | Outlook drafts don't thread correctly |

---

## 6. STYLE SYSTEM STATUS

**Verdict: Fully connected, but dependent on data existing**

### Style Injection Chain

```
user_settings.preferences.digital_twin.writing_style (21-field fingerprint)
  ↓ _get_full_fingerprint_from_db()          [digital_twin.py:1008-1012]
  ↓ _build_full_style_guidelines()           [digital_twin.py:596-676]
  ↓ Returns multi-line style string
  ↓ Injected into prompt as "=== YOUR WRITING STYLE (MATCH THIS) ===" [autonomous_draft_engine.py:773-774]
```

**4-tier fallback chain:**
1. `user_settings.preferences.digital_twin.writing_style` → 21-field fingerprint → comprehensive guidelines
2. Graphiti knowledge graph → 13-field `WritingStyleFingerprint` → partial guidelines
3. `digital_twin_profiles` table → 3 fields (tone, writing_style, formality) → minimal guidelines
4. `_DEFAULT_STYLE_GUIDELINES` → generic professional tone

**Personality calibration also injected:**
```
user_settings.preferences.digital_twin.personality_calibration
  ↓ PersonalityCalibrator.get_calibration()  [personality_calibrator.py:522-561]
  ↓ Returns PersonalityCalibration with tone_guidance string
  ↓ Injected into prompt as "=== TONE GUIDANCE ===" [autonomous_draft_engine.py:777-779]
```

**Per-recipient style also injected:**
```
recipient_writing_profiles table
  ↓ _get_recipient_style()                   [email_context_gatherer.py:307]
  ↓ Returns RecipientWritingStyle
  ↓ Injected into prompt as "=== RECIPIENT'S COMMUNICATION STYLE ===" [autonomous_draft_engine.py:766-770]
```

**Root cause of "no style matching":** If email bootstrap hasn't completed, there's no fingerprint → all 3 fallback tiers may be empty → default generic guidelines used → all drafts sound the same.

**To verify:** 🔍 Query `user_settings` for `preferences->'digital_twin'->'writing_style'` — if NULL, email bootstrap never ran.

---

## 7. CALENDAR INTEGRATION STATUS

**Verdict: Implemented and wired, with naming inconsistency risk**

| Aspect | Status | Evidence |
|--------|--------|----------|
| Calendar context gathering | ✅ Implemented | `email_context_gatherer.py:1500-1575` |
| Google Calendar events | ✅ Queries via Composio | ECG: `_fetch_google_calendar_events()` |
| Outlook Calendar events | ✅ Queries via Composio | ECG: `_fetch_outlook_calendar_events()` |
| Integration detection | ⚠️ Naming mismatch | ECG checks `googlecalendar` and `outlook365calendar` |
| Scheduler checks | ⚠️ Naming mismatch | `scheduler.py:77` checks `google_calendar` (with underscore) |
| Prompt injection | ✅ When data exists | `autonomous_draft_engine.py:782-788` |
| Missing data guidance | ❌ No instruction | LLM not told to say "check my calendar" when data is absent |

**Calendar urgency detection** also exists: `email_analyzer.py:568-628` checks `calendar_events` table (local cache, not Composio) for upcoming meetings with the sender within 2 hours.

---

## 8. CONCURRENCY STATUS

### Guards in Place

| Guard | Location | Mechanism | Effectiveness |
|-------|----------|-----------|---------------|
| API 60-second rate limit | `email.py:109-142` | Checks `email_processing_runs.started_at >= (now - 60s)` | ✅ Prevents rapid re-triggers |
| Global per-user lock | `autonomous_draft_engine.py:999-1031` | Checks `status='running'` on `email_processing_runs` | ✅ Prevents truly concurrent runs |
| Stale run cleanup | `autonomous_draft_engine.py:1033-1049` | Marks `running` runs >10min old as `failed` | ✅ Prevents permanent lockout |
| Periodic job 30-min gap | `periodic_email_check.py:82` | `_calculate_hours_since_last_run()` skips if <30min | ✅ But scheduler fires every 15min |
| Thread-level dedup | `autonomous_draft_engine.py:1135-1184` | Checks `email_drafts` for thread_id/email_id match | ✅ Prevents same-thread duplicates within a run |

### Idempotency

**Verdict: NOT idempotent**

Every run re-fetches the same 24-hour window of emails. The dedup check prevents re-drafting for threads that already have an ARIA draft, but:
- The categorization step re-runs for ALL emails (wasteful)
- `email_scan_log` gets duplicate entries for the same email across runs
- There is no message-ID-based watermark that advances after processing

The periodic job at `periodic_email_check.py:80` calculates `since_hours` from `email_processing_runs.completed_at`, which provides a dynamic window. But `scan_inbox()` in `email_analyzer.py:192` passes this as `since_hours` to `_fetch_inbox_emails()`, which converts it to a `datetime` offset — this means the window shrinks based on when the last run completed, not based on which emails were actually processed.

---

## 9. SPECIFIC BUG EVIDENCE

### Bug 1: Duplicate Drafts
- **Dedup check exists:** `autonomous_draft_engine.py:1135-1184` ✅
- **Race condition possible:** Two triggers (API + scheduler) could pass dedup before either inserts
- **Re-fetch window:** 24-hour default means same emails seen on every run
- **Mitigation:** Dedup should catch most cases. True duplicates require overlapping runs.
- **Verify:** 🔍 Count `email_drafts` rows grouped by `thread_id` with `HAVING COUNT(*) > 1`

### Bug 2: Raw JSON in Body
- **JSON fallback at `:696-705`** uses raw text as body ✅ Confirmed
- **Fence stripping at `:680-688`** handles ``` ``` ``` only, not embedded JSON with surrounding text
- **Temperature 0.7** increases likelihood of LLM adding explanation text around JSON
- **Verify:** 🔍 `SELECT id, LEFT(body, 200) FROM email_drafts WHERE body LIKE '%"subject":%' OR body LIKE '%```json%'`

### Bug 3: Hallucinated Availability
- **Calendar IS queried** during context gathering ✅
- **When calendar is not connected** or has no events, the `UPCOMING MEETINGS` section is simply omitted
- **The LLM prompt does NOT instruct** "If you have no calendar data, say you'll need to check"
- **Verify:** 🔍 Check `draft_context.calendar_context` for drafts mentioning specific times

### Bug 4: Already-Replied Drafts
- **No sent-folder check exists** in the draft pipeline ❌
- **Thread context IS fetched** but `is_from_user` flag is not used to prevent drafting
- **The dedup check only prevents duplicate ARIA drafts**, not drafts for human-replied threads
- **Verify:** 🔍 Cross-reference `email_drafts.thread_id` with sent-folder messages

---

## 10. CRITICAL PATH — Minimum Fixes for Correct Behavior

### P0: Must Fix (one email in → one correct draft out)

| # | Fix | File | Complexity |
|---|-----|------|------------|
| **P0-1** | **JSON extraction with regex fallback** — Before falling back to raw text, try regex: `r'\{[^{}]*"subject"[^{}]*"body"[^{}]*\}'` to extract JSON from LLM response | `autonomous_draft_engine.py:690-705` | Low |
| **P0-2** | **Sent-folder reply check** — Before drafting, check if user already replied. Use `thread_context.messages` + `is_from_user` flag: if the latest message in thread is from the user, skip drafting | `autonomous_draft_engine.py` (add before `:328`) | Medium |
| **P0-3** | **Calendar unavailable prompt guidance** — Add to `_build_reply_prompt()`: "If no UPCOMING MEETINGS section is shown, do NOT invent times or availability. Instead say you'll check your calendar." | `autonomous_draft_engine.py:_build_reply_prompt()` | Low |

### P1: Should Fix (reliability and efficiency)

| # | Fix | File | Complexity |
|---|-----|------|------------|
| **P1-1** | **Message-ID watermark** — After processing, store the latest `email_id` or `receivedDateTime` in `email_processing_runs`. On next run, use this as the `since` boundary instead of `since_hours` | `email_analyzer.py`, `autonomous_draft_engine.py` | Medium |
| **P1-2** | **Outlook thread linking** — Pass `conversationId` to `OUTLOOK_CREATE_DRAFT` so drafts appear in the correct thread in Outlook | `email_client_writer.py:264-269` | Low |
| **P1-3** | **Calendar integration type normalization** — Standardize on `googlecalendar`/`outlook365calendar` everywhere, or create a mapping function | `scheduler.py:77`, `email_context_gatherer.py:1584` | Low |
| **P1-4** | **Lower LLM temperature for drafts** — Reduce from 0.7 to 0.3 to reduce JSON format violations and hallucinated content | `autonomous_draft_engine.py:676` | Trivial |

### P2: Nice to Have (robustness)

| # | Fix | Description |
|---|-----|-------------|
| **P2-1** | Structured output (tool_use) | Use Claude's tool_use to force JSON output instead of relying on prompt instructions |
| **P2-2** | Dedup with distributed lock | Use Redis or pg advisory lock to prevent race conditions between API and scheduler |
| **P2-3** | Skip duplicate scan_log entries | Before logging to `email_scan_log`, check if this `email_id` was already logged recently |

---

## APPENDIX: File Reference Table

| File | Lines | Role |
|------|-------|------|
| `backend/src/services/email_analyzer.py` | 1632 | Inbox fetching + 10-filter categorization + LLM classification |
| `backend/src/services/autonomous_draft_engine.py` | 1386 | Pipeline orchestrator: scan → dedup → context → draft → save |
| `backend/src/services/email_context_gatherer.py` | ~2449 | 8-source context aggregation (thread, Exa, memory, calendar, CRM, corporate, style, health) |
| `backend/src/services/email_client_writer.py` | 397 | Save drafts to Gmail/Outlook via Composio |
| `backend/src/jobs/periodic_email_check.py` | 262 | Scheduled urgent-email scanner with watermark |
| `backend/src/api/routes/email.py` | ~700 | API endpoints: scan-now, scan-status, decisions |
| `backend/src/api/routes/composio_webhooks.py` | ~150 | Webhook ingestion (creates Pulse signals, NOT drafts) |
| `backend/src/services/event_handlers/email_handler.py` | ~60 | Email event → Pulse signal conversion |
| `backend/src/memory/digital_twin.py` | 1389 | Writing style fingerprint + style scoring + 4-tier fallback guidelines |
| `backend/src/onboarding/personality_calibrator.py` | 592 | Tone calibration from fingerprint → 5 personality traits |
| `backend/src/services/scheduler.py` | ~1650 | APScheduler: email check every 15min, deferred retry every 15min, feedback poll every 30min |
| `backend/src/services/draft_feedback_tracker.py` | ~370 | Post-hoc sent-folder checking for learning mode (NOT used pre-draft) |
