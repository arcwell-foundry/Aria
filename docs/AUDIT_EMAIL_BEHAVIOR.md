# ARIA Email Behavior Audit

**Date:** 2026-02-22 00:30 EST
**Auditor:** Claude Opus 4.6 (read-only)
**User:** 41475700-c1fb-4f66-8c56-77bd90b73abb
**Supabase Project:** asqcmailhanhmyoaujje

---

## Executive Summary

ARIA's email intelligence pipeline has real infrastructure — it scans inboxes via Composio, classifies emails with a rules+LLM hybrid, gathers context from 7 sources (Exa, memory, calendar, CRM, style profiles), and generates drafts using PersonaBuilder. **However, the rules-based filter chain has critical gaps:** there are no pre-LLM checks for calendar invite responses (Declined/Accepted/Tentative), junk/spam system notifications, or bounce-back messages. The LLM classifier inconsistently catches these — it correctly identified calendar declines as FYI on a second scan but classified them as NEEDS_REPLY on the first scan, and it completely missed a "Not junk" Outlook system notification. As a result, 3 out of 3 current drafts (100%) are inappropriate: replies to a junk reclassification notification and two calendar decline notifications.

---

## Part 1: Current Drafts Analysis

### All Drafts in Database (3 total)

| # | Draft ID | Recipient | Subject | Appropriate? | Why Not |
|---|----------|-----------|---------|-------------|---------|
| 1 | `0f3685c9` | hello@luminone.com | Re: Not junk:91595f46-5324-47e1-17e3-08de6fd4e61b\|investmentteam@launch.co\|(ARIA // LAUNCH - First Meeting) | **NO** | Outlook "Not junk" reclassification notification — system-generated, no human wrote this |
| 2 | `89879fe3` | d.pat@live.co.uk | Re: Declined: Strategy Session: Guest x ARIA | **NO** | Calendar decline auto-notification — no human expects a reply |
| 3 | `e3766114` | d.pat@live.co.uk | Re: Declined: Strategy Session: Guest x ARIA | **NO** | Duplicate calendar decline — same thread, same inappropriate draft |

**False positive rate: 3/3 (100%) — every draft is inappropriate.**

### Draft Body Text

**Draft 1 (Not junk notification):**
> Hi there,
>
> I received your message but it appears to contain only email header information and technical routing details. I'm not seeing the actual content you intended to send.
>
> Could you resend your message? I want to make sure I don't miss anything important.
>
> Thanks,
> Dhruv Patwardhan

Analysis: ARIA recognized the email body was gibberish (routing metadata) but instead of flagging this as a system notification, it drafted a confused reply asking the "sender" to resend. The email was from `hello@luminone.com` — the user's own domain — making this even worse (ARIA is drafting a reply to the user's own system notification).

**Draft 2 (Calendar decline):**
> Hi there,
>
> I see you declined the strategy session meeting. No problem at all.
>
> Would you prefer to reschedule for a different time, or are you not interested in moving forward with the ARIA discussion right now?
>
> Just let me know either way so I can plan accordingly.
>
> Best,
> Dhruv

**Draft 3 (Calendar decline duplicate):**
> Hi there,
>
> I see you declined the strategy session invite. No problem at all.
>
> Would you like to reschedule for a different time that works better for you? I'm flexible on timing and can work around your schedule.
>
> Let me know what you think.
>
> Best,
> Dhruv

Analysis: These are nearly identical. Both are replies to automated calendar decline notifications — nobody sends these manually, and nobody expects a reply. The recipient `d.pat@live.co.uk` is the user's own personal email, making this doubly wrong.

### Draft Context Analysis

All 3 drafts share these context characteristics:

| Context Source | Status | Detail |
|---------------|--------|--------|
| thread_summary | **null** | Thread fetching failed or returned no data |
| recipient_research | **REAL but wrong** | Exa returned company data for the wrong entity (LIVE! Incorporated for `d.pat@live.co.uk` — it's a personal domain, not a company) |
| relationship_history | 0 emails, "unknown" | No prior relationship data |
| calendar_context | connected: false | Calendar integration not wired |
| crm_context | connected: false | CRM not connected |
| corporate_memory_used | null | No corporate memory |
| exa_sources_used | null at top level | Exa data is embedded in recipient_research JSON, not in this field |
| confidence_reason | empty string | Not populated |
| draft_id | **null** | Foreign key to email_drafts not set — broken join |

All drafts: confidence_level=0.825, style_match_score=0.50, saved_to_client=true, user_action=pending.

**Key finding:** `draft_id` is null in all `draft_context` rows, meaning the JOIN between `email_drafts` and `draft_context` is broken. The context data exists but cannot be linked back to its draft.

---

## Part 2: Email Analyzer Behavior

**File:** `backend/src/services/email_analyzer.py` (1182 lines)

### scan_inbox() — How Emails Are Fetched

- **Location:** Lines 97-186
- **Date range:** Configurable `since_hours` parameter (default: 24 hours)
- **Folder:** INBOX only (no Spam, Junk, Sent, or other folders)
- **Outlook:** Uses `OUTLOOK_LIST_MESSAGES` with `$filter=receivedDateTime ge {since_date}`, `$top=200`
- **Gmail:** Uses `GMAIL_FETCH_EMAILS` with `label='INBOX'`, `max_results=200` — **no date filter** (the `since_hours` parameter is effectively ignored for Gmail users)
- **Privacy exclusions:** Loaded from `user_settings.integrations.email.privacy_exclusions` before iteration

### categorize_email() — The Full Classification Pipeline

**Location:** Lines 187-327

#### Rules-Based Fast Path (no LLM needed)

The analyzer applies 4 rule-based checks, in order:

| Check | What It Does | Returns | Line |
|-------|-------------|---------|------|
| 1. Privacy exclusion | `_is_excluded()` — matches sender against user's exclusion list | SKIP/LOW | 218 |
| 2. No-reply/automated | `_is_noreply()` — matches against 7 regex patterns | SKIP/LOW | 234 |
| 3. Newsletter/mailing list | Checks headers for `list-unsubscribe`, `list-id`, `x-mailchimp-id`, `x-campaign-id` | FYI/LOW | 250 |
| 4. CC-only | `_is_only_cc()` — checks if user is in CC but not in To | FYI/LOW | 269 |

**The 7 no-reply patterns** (line 62-70):
```
^no[-_.]?reply@
^do[-_.]?not[-_.]?reply@
^notifications?@
^mailer[-_.]?daemon@
^postmaster@
^bounce[s]?@
^auto[-_.]?confirm@
```

#### MISSING Rules-Based Checks

| Filter | Status | Impact |
|--------|--------|--------|
| **Calendar invite/response** (Accepted/Declined/Tentative in subject) | **MISSING** | Calendar declines classified as NEEDS_REPLY |
| **Junk/spam system notification** (subject contains "Not junk", "Junk Email", system routing IDs) | **MISSING** | Outlook "Not junk" notification classified as NEEDS_REPLY |
| **Bounce/delivery failure** (subject contains "Undeliverable", "Delivery Status Notification") | **MISSING** | Caught by LLM on this scan, but no rules guarantee |
| **Read receipts** | **MISSING** | Would depend on LLM to catch |
| **Internal auto-forwarded messages** | **MISSING** | Would depend on LLM to catch |
| **Self-sent emails** (sender = user's own email/domain) | **MISSING** | "Not junk" notification from hello@luminone.com was the user's own domain |
| **Content-type: text/calendar or .ics attachment** | **MISSING** | Would catch calendar invites the subject check misses |

#### LLM Classification (fallback)

**Location:** Lines 922-1083

When no rule-based check matches, the email goes to Claude:

- **Model:** Claude Sonnet (via `LLMClient.generate_response()` default)
- **Temperature:** 0.2
- **Max tokens:** 500
- **System prompt:** None (no PersonaBuilder — violates CLAUDE.md requirement)
- **CostGovernor check:** None (violates CLAUDE.md requirement)

**Full LLM prompt** (lines 968-1010):
```
Classify this email for a life sciences commercial professional.

From: {sender_name} <{sender_email}>
Subject: {subject}
Recipients: To: {to_list}, CC: {cc_list}
{relationship_context}

Body:
{body_truncated (first 2000 chars)}

Classify as exactly one JSON object with these fields:
{
  "category": "NEEDS_REPLY" | "FYI" | "SKIP",
  "urgency": "URGENT" | "NORMAL" | "LOW",
  "topic_summary": "1-sentence summary",
  "needs_draft": true/false,
  "reason": "1-sentence explanation"
}

Classification guidelines:
- NEEDS_REPLY: Direct question, action requested, from a real person...
- FYI: Informational, no action needed...
- SKIP: Spam, automated notifications, promotional, system-generated alerts
- needs_draft=true only if NEEDS_REPLY and a substantive response is expected
- URGENT only for time-sensitive items with explicit deadlines
```

**LLM prompt problem:** The prompt does not explicitly list calendar responses, junk notifications, or bounce-backs as SKIP. The guidelines mention "automated notifications" and "system-generated alerts" but the LLM is inconsistent in applying these to calendar decline subjects.

### detect_urgency() — Urgency Detection

**Location:** Lines 329-392

Checks (in order):
1. Keyword scan: 17 keywords in subject+body (urgent, asap, by eod, deadline, etc.)
2. VIP sender: checks `user_settings.preferences.vip_contacts` or 10+ interactions
3. Calendar proximity: meetings in next 2 hours with sender as attendee
4. Overdue response: reply to a sent email older than 48 hours
5. Rapid thread: 3+ messages from 2+ senders in last hour
6. Default: NORMAL (never returns LOW)

### Email Scan Log Analysis

**30 most recent entries** for this user:

| # | Sender | Subject | Category | needs_draft | LLM Reason | Correct? |
|---|--------|---------|----------|-------------|------------|----------|
| 1 | system | Draft skipped: existing_draft | SKIP | false | existing_draft | N/A (system) |
| 2 | system | Draft skipped: already_replied | SKIP | false | already_replied | N/A (system) |
| 3 | system | Draft skipped: already_replied | SKIP | false | already_replied | N/A (system) |
| 4 | hello@luminone.com | Not junk:91595f46-5324... | **NEEDS_REPLY** | **true** | "meeting invitation or follow-up from investment team" | **WRONG** — junk reclassification notification |
| 5 | notifications@calendly.com | New Event: Dave Stephens... | SKIP | false | "automated no-reply address" | Correct (caught by rules) |
| 6 | d.pat@live.co.uk | Declined: Strategy Session | FYI | false | "automated calendar decline notification" | Correct (on 2nd scan) |
| 7 | d.pat@live.co.uk | Declined: Strategy Session | FYI | false | "automated calendar decline notification" | Correct (on 2nd scan) |
| 8 | john.barker@approcess.com | RE: Catchup and ARIA Intro | FYI | false | "polite acknowledgment, no questions" | Correct |
| 9 | microsoftexchange329e71ec88ae4615bbc36ab6ce41109e@luminone.com | Undeliverable: Follow-up | SKIP | false | "system-generated bounce-back" | Correct |
| 10 | keith@venturefizz.com | Re: Following up from yesterday's event | NEEDS_REPLY | true | "asked a direct question about Pillar" | Correct |
| 11 | rdouglas@savillex.com | RE: ARIA Design Partnership | NEEDS_REPLY (URGENT) | true | "scheduling a follow-up meeting" | Correct |
| 12 | team@hi.wellfound.com | Dhruv has invited you to recruit | SKIP | false | "automated promotional email" | Correct |
| 13 | team@wellfound.com | Important: verify your email | SKIP | false | "system-generated email verification" | Correct |

**Earlier scan (22:57 — the one that produced the drafts):**

| # | Sender | Subject | Category | needs_draft | LLM Reason | Correct? |
|---|--------|---------|----------|-------------|------------|----------|
| 1 | hello@luminone.com | Not junk:91595f46... | **NEEDS_REPLY** | **true** | "meeting request from investment team" | **WRONG** |
| 2 | notifications@calendly.com | New Event: Dave Stephens | SKIP | false | Caught by rules | Correct |
| 3 | d.pat@live.co.uk | Declined: Strategy Session | **NEEDS_REPLY** | **true** | "meeting decline requiring acknowledgment" | **WRONG** |
| 4 | d.pat@live.co.uk | Declined: Strategy Session | **NEEDS_REPLY** | **true** | "meeting decline requiring rescheduling" | **WRONG** |
| 5 | john.barker@approcess.com | RE: Catchup and ARIA Intro | FYI | false | Correct | Correct |
| 6 | microsoftexchange329e71ec88ae4615bbc36ab6ce41109e@luminone.com | Undeliverable | SKIP | false | Correct | Correct |

**Key finding:** The LLM is **inconsistent**. On the first scan (22:57), it classified calendar declines as NEEDS_REPLY. On the second scan (04:34), it correctly classified them as FYI. The "Not junk" email was classified as NEEDS_REPLY on ALL scans — the LLM was fooled by the embedded subject line `(ARIA // LAUNCH - First Meeting)` into thinking it was a meeting request.

**False positive rate in scan log:** 3/8 real emails incorrectly flagged as NEEDS_REPLY on the scan that produced drafts (37.5%).

---

## Part 3: Smart Non-Drafting Filter Chain

The filtering that happens BEFORE draft generation is split between `email_analyzer.py` (scan-time) and `autonomous_draft_engine.py` (draft-time).

### Scan-Time Filters (email_analyzer.py categorize_email)

| Filter | Spec Requires | Code Has It? | Where |
|--------|--------------|-------------|-------|
| Newsletter/mailing list (List-Unsubscribe) | YES | **YES** | `email_analyzer.py:250-266` |
| no-reply/noreply sender | YES | **YES** | `email_analyzer.py:234-247` (7 patterns) |
| User is CC only (not in TO) | YES | **YES** | `email_analyzer.py:268-283` |
| Sender in user's exclusion list | YES | **YES** | `email_analyzer.py:218-231` |
| Calendar invite/response (Accepted/Declined/Tentative) | YES | **NO** | Not implemented anywhere |
| Automated/system notification | YES | **PARTIAL** | Only via LLM prompt, not rules |
| Spam/junk folder messages | YES | **NO** | Only fetches INBOX, so junk folder emails shouldn't appear — but junk *notifications* do |
| Bounce/delivery failure | YES | **NO** | Caught by LLM but not rules |
| Read receipts | SHOULD | **NO** | Not implemented |
| Internal auto-forwarded messages | SHOULD | **NO** | Not implemented |

### Draft-Time Filters (autonomous_draft_engine.py process_inbox)

| Filter | Spec Requires | Code Has It? | Where |
|--------|--------------|-------------|-------|
| User already replied to thread | YES | **YES** | `autonomous_draft_engine.py:274-285` (sent folder + DB check) |
| Existing draft for this thread | YES | **YES** | `autonomous_draft_engine.py:260-272` (cross-run dedup) |
| Learning mode top contacts only | YES | **YES** | `autonomous_draft_engine.py:303-317` |
| Active conversation deferral | YES | **YES** | `autonomous_draft_engine.py:290-301` |
| Self-sent email detection | SHOULD | **NO** | Not implemented |

---

## Part 4: Context Gathering Reality

**File:** `backend/src/services/email_context_gatherer.py` (1372 lines)

| # | Context Source | Status | Detail |
|---|---------------|--------|--------|
| 1 | **Thread reading** | **REAL but FAILING** | Uses `GMAIL_FETCH_MESSAGE_BY_THREAD_ID` or `OUTLOOK_LIST_MESSAGES` with conversationId filter. All `thread_summary` values are null in production data — suggests Composio call is failing silently or returning empty |
| 2 | **Recipient research (Exa)** | **REAL but LOW QUALITY** | `ExaEnrichmentProvider.search_person()` + `search_company()` — returns results but misidentifies personal email domains as companies (d.pat@live.co.uk → "LIVE! Incorporated") |
| 3 | **Recipient writing style** | **REAL** | Queries `recipient_writing_profiles` table — returns empty for all 3 drafts (no profiles built yet) |
| 4 | **Relationship history** | **REAL but EMPTY** | Queries `memory_semantic` with `ilike("%{sender_email}%")` — 0 emails for all contacts (memory not populated) |
| 5 | **Calendar context** | **REAL but DISCONNECTED** | Queries `user_integrations` for calendar type — shows `connected: false` for all drafts |
| 6 | **CRM context** | **REAL but DISCONNECTED** | Queries `user_integrations` for salesforce/hubspot — shows `connected: false` for all drafts |
| 7 | **Corporate memory** | **REAL but EMPTY** | Queries `memory_semantic` for company facts — returns null (no corporate memory stored) |

**Summary: 2/7 sources return real data (Exa research + thread fetch code is real). But thread fetch is silently failing, Exa is producing wrong company matches for personal domains, and 4/7 sources have no data to return.**

---

## Part 5: Draft Generation

**File:** `backend/src/services/autonomous_draft_engine.py` (1532 lines)

### LLM Configuration
- **Model:** Claude Sonnet (`claude-sonnet-4-20250514` via LLMClient default)
- **Temperature:** 0.7 (higher than classification — appropriate for creative writing)
- **Max tokens:** LLMClient default (not explicitly set)
- **PersonaBuilder:** Attempted via try/except with fallback to `_FALLBACK_REPLY_PROMPT` — logs warning on failure
- **CostGovernor:** Not checked before LLM call

### System Prompt
PersonaBuilder is used with `agent_name="draft_engine"`, falling back to:
```
You are ARIA, an AI assistant drafting an email reply.
```
Plus task instructions requiring JSON output with `subject` and `body` fields.

### Context Variables Injected
Up to 9 sections assembled in `_build_reply_prompt()`:
1. Original email (sender, subject, urgency, body snippet)
2. Conversation thread (summary + last 3 messages) — **currently null**
3. About the recipient (title, company, bio from Exa) — **working but inaccurate**
4. Relationship history (email count, key facts) — **currently empty**
5. Recipient communication style (formality, tone) — **currently empty**
6. User writing style (from digital_twin) — **working**
7. Tone guidance (from personality calibrator) — **status unknown**
8. Upcoming meetings (from calendar) — **disconnected**
9. CRM status (lead stage, deal value) — **disconnected**

### Quality Assessment
- **Style integration:** Digital twin style guidelines injected; post-generation style scoring produces `style_match_score` (all drafts scored 0.50 — low, triggering the "Review recommended" warning)
- **Thread context:** Supposed to be included but all `thread_summary` values are null, so drafts are generated without conversation history
- **Guardrails:** Deduplication, already-replied, active conversation deferral, learning mode — all functional. But no guardrail against drafting replies to system-generated emails
- **Confidence scoring:** Dynamic based on context richness (0.4 base + 0.06/source × 7 + 0.1 known contact + 0.08 thread depth). All 3 drafts scored 0.825 because only Exa research was available as a source

---

## Part 6: Spec Compliance

| Spec Requirement | Implemented? | Details |
|-----------------|-------------|---------|
| Full inbox access (read all emails) | **PARTIAL** | Reads INBOX only (Outlook + Gmail). No access to Sent, Drafts, or other folders. Gmail has no date filter. |
| Proactive overnight draft generation | **YES** | `process_inbox()` is called by scheduler. Ran at 22:53 and 04:44 UTC on this day. |
| Draft ONLY, never send | **YES** | No send capability in the code. Only saves drafts. |
| Drafts saved to email client Drafts folder | **YES** | `saved_to_client: true` for all 3 drafts. Uses Composio `OUTLOOK_SAVE_DRAFT` / `GMAIL_CREATE_EMAIL_DRAFT`. |
| Writing style learned from past emails | **PARTIAL** | Digital twin has style data. Per-recipient profiles exist in schema but are empty for current drafts. |
| Morning briefing includes email section | **UNKNOWN** | Not audited — separate code path |
| Email Analyzer categorizes: NEEDS_REPLY, FYI, SKIP | **YES** | Working. Both rules-based and LLM classification. |
| Priority: URGENT, NORMAL, LOW | **YES** | `detect_urgency()` with 5 signal types + LLM urgency. |
| Context Gatherer pulls 7 sources | **YES (code)** | All 7 sources are implemented with real API calls. But 5/7 return empty data in production. |
| Per-recipient style adaptation | **YES (code)** | `recipient_writing_profiles` queried and injected. Empty for all current contacts. |
| ARIA notes explain reasoning | **YES** | All drafts have `aria_notes` with context sources, relationship status, style warning, confidence. |
| Confidence scoring based on context richness | **YES** | Dynamic calculation from 7 sources + known contact + thread depth. Not hardcoded. |
| Learning mode (first 7 days, top 10 contacts) | **YES (code)** | `LearningModeService` exists with full implementation. May not be active for this user. |
| Draft feedback tracking | **PARTIAL** | `user_action` field exists (all "pending"). Feedback loop code exists but no user has taken action yet. |
| 15-30 min periodic inbox scan | **YES** | Scheduler triggered scans at 22:57, 04:34, and 04:44 UTC. |
| Urgency → real-time WebSocket notification | **UNKNOWN** | Not audited — separate code path |
| Privacy exclusions respected | **YES** | `_load_exclusions()` + `_is_excluded()` implemented and checked first. |
| Already-replied check | **YES** | Two-tier: pre-fetched sent folder thread IDs + DB check for approved drafts. |

---

## Part 7: Why ARIA Drafted Replies to Junk Emails

### Draft 1: "Re: Not junk:91595f46-5324..."

**What happened, step by step:**

1. **Fetch:** Outlook API returned this email from INBOX. The email is a system-generated Outlook "Not junk" reclassification notification. Its subject is: `Not junk:91595f46-5324-47e1-17e3-08de6fd4e61b|investmentteam@launch.co|(ARIA // LAUNCH - First Meeting) 2/20/2026 1:36:00 PM`

2. **Rules check:** Sender is `hello@luminone.com` — this is the user's own domain. It does not match any no-reply pattern (`_NOREPLY_PATTERNS`). It has no mailing list headers. User is not CC-only. **All 4 rules pass → falls through to LLM.**

3. **LLM classification:** The LLM saw the embedded subject line `(ARIA // LAUNCH - First Meeting)` and classified it as: `NEEDS_REPLY` with reason "meeting invitation or follow-up from investment team requiring acknowledgment." The LLM was **fooled by the embedded meeting subject within the junk notification subject line.**

4. **Scan log entry:** `email_scan_log` records: category=NEEDS_REPLY, urgency=NORMAL, needs_draft=true. **This was the same across all 3 scans.**

5. **Draft engine:** `process_inbox()` iterated `scan_result.needs_reply`, found this email, checked for existing draft (none), checked already-replied (no), generated a draft.

6. **Context gathering:** Thread summary: null. Exa research found LuminOne company info (correct but irrelevant — it's the user's own company). Relationship: unknown, 0 emails. Calendar/CRM: disconnected.

7. **Draft generation:** LLM produced a confused response acknowledging "header information and technical routing details" and asking to resend.

8. **Saved:** Draft saved to Outlook Drafts folder with `saved_to_client: true`.

**Root cause:** No rules-based filter for:
- Subjects starting with "Not junk:" (Outlook system notification pattern)
- Sender matching the user's own email/domain
- Emails whose body is only system metadata with no human-written content

### Drafts 2 & 3: "Re: Declined: Strategy Session: Guest x ARIA"

**What happened, step by step:**

1. **Fetch:** Two separate Outlook emails from `d.pat@live.co.uk` with subject "Declined: Strategy Session: Guest x ARIA" arrived in INBOX. These are automated calendar decline notifications generated by Outlook when an invitee declines a meeting.

2. **Rules check:** Sender `d.pat@live.co.uk` doesn't match no-reply patterns (it's a real personal email address — the calendar system sends the decline notification FROM the invitee's address). No list headers. Not CC-only. **All 4 rules pass → falls through to LLM.**

3. **LLM classification (first scan, 22:57):** The LLM classified both as `NEEDS_REPLY` with `needs_draft: true`, reasoning "meeting decline that requires acknowledgment and likely rescheduling discussion." **The LLM treated calendar declines as requiring a human response.**

4. **LLM classification (second scan, 04:34):** The LLM correctly classified both as `FYI` with `needs_draft: false`, reasoning "automated calendar decline notification with no body content requiring action." **The LLM was inconsistent across scans.**

5. **Drafts generated:** On the first scan (22:57), both emails produced drafts. On the second scan (04:34), the existing_draft dedup check prevented new drafts.

6. **Context gathering:** For both drafts, Exa searched for "d.pat@live.co.uk" and returned "LIVE! Incorporated" — an entertainment company unrelated to the actual person. This is because Exa extracts the domain `live.co.uk` and matches it to a company, not understanding it's a personal Microsoft email address.

**Root cause:** No rules-based filter for subjects matching `^(Accepted|Declined|Tentative):`.

---

## Critical Issues (Priority Order)

### 1. MISSING: Calendar Response Filter (CRITICAL)
**Impact:** Calendar declines, acceptances, and tentative responses are not caught by rules. The LLM is inconsistent (caught on 2nd scan, missed on 1st).
**File:** `backend/src/services/email_analyzer.py:215-284`
**Fix:** Add regex check for subjects matching `^(Accepted|Declined|Tentative|Cancelled|Updated):` before the LLM fallback.

### 2. MISSING: Junk/Spam System Notification Filter (CRITICAL)
**Impact:** Outlook "Not junk:" notifications pass all rules and confuse the LLM.
**File:** `backend/src/services/email_analyzer.py:215-284`
**Fix:** Add regex check for subjects matching `^(Not junk:|Junk Email:)` or containing Outlook routing IDs (pipe-delimited UUIDs).

### 3. MISSING: Self-Sent Email Filter (HIGH)
**Impact:** Emails from the user's own address/domain (hello@luminone.com) are treated as external emails requiring replies.
**File:** `backend/src/services/email_analyzer.py:215-284`
**Fix:** Compare sender_email domain against user's known domains. Skip or classify as FYI.

### 4. MISSING: Bounce/Undeliverable Rules Filter (MEDIUM)
**Impact:** Currently caught by LLM but not guaranteed. The `microsoftexchange329e71ec88ae4615bbc36ab6ce41109e@luminone.com` sender was caught by LLM, not rules.
**File:** `backend/src/services/email_analyzer.py:62-70`
**Fix:** Add `^microsoftexchange[a-f0-9]+@` to `_NOREPLY_PATTERNS`. Add subject check for `^Undeliverable:` or `^Delivery Status Notification`.

### 5. Thread Fetching Silently Failing (HIGH)
**Impact:** All `thread_summary` values are null. Drafts are generated without conversation context, producing generic replies that don't reference the actual thread content.
**File:** `backend/src/services/email_context_gatherer.py:340-528`
**Investigation needed:** The Composio thread fetch calls may be failing silently or returning empty data.

### 6. Exa Company Research Wrong for Personal Domains (MEDIUM)
**Impact:** `d.pat@live.co.uk` → "LIVE! Incorporated". `hello@luminone.com` → Lumine Group acquisition news. Wasted Exa API calls producing misleading context.
**File:** `backend/src/services/email_context_gatherer.py:568-663`
**Fix:** Add personal email domain allowlist (live.co.uk, gmail.com, outlook.com, hotmail.com, yahoo.com, etc.) and skip company research for those domains. Also distinguish `luminone.com` from `lumine` in company search.

### 7. draft_context.draft_id Is Always Null (MEDIUM)
**Impact:** The JOIN between `email_drafts` and `draft_context` is broken. Context data cannot be traced back to its draft.
**File:** `backend/src/services/email_context_gatherer.py:1247-1276` (the `_save_context` method)
**Fix:** Ensure draft_id is set when saving context, or save context after the draft is created and link back.

### 8. No PersonaBuilder/CostGovernor in Email Analyzer (LOW)
**Impact:** Violates CLAUDE.md requirements for all LLM calls. Classification LLM call has no system prompt and no cost tracking.
**File:** `backend/src/services/email_analyzer.py:922-1083`
**Fix:** Add PersonaBuilder system prompt and CostGovernor check/record to `_llm_classify()`.

### 9. Gmail Date Filter Missing (LOW)
**Impact:** Gmail users get their latest 200 emails regardless of `since_hours`, potentially re-scanning old emails.
**File:** `backend/src/services/email_analyzer.py:590-742`
**Fix:** Add `after:{epoch_timestamp}` to the Gmail fetch query parameter.

### 10. Confidence Score Artificially Uniform (LOW)
**Impact:** All 3 very different drafts received identical confidence (0.825). The confidence formula only counts binary source availability, not source quality or relevance.
**File:** `backend/src/services/autonomous_draft_engine.py:837-871`
**Fix:** Weight confidence by source quality (e.g., Exa returning wrong company should reduce confidence).

---

## Recommended Fixes (Priority Order)

### Fix 1: Add 6 Missing Rules-Based Filters

Add these checks to `email_analyzer.py:categorize_email()` between the CC-only check (line 283) and the LLM fallback (line 285):

```python
# Calendar response check (Accepted/Declined/Tentative/Cancelled)
_CALENDAR_RESPONSE_PATTERN = re.compile(
    r"^(Accepted|Declined|Tentative|Canceled|Cancelled|Updated|New Time Proposed):",
    re.IGNORECASE,
)

# Junk/spam notification check
_JUNK_NOTIFICATION_PATTERN = re.compile(
    r"^(Not junk|Junk Email|Junk E-Mail):",
    re.IGNORECASE,
)

# Bounce/undeliverable check
_BOUNCE_PATTERN = re.compile(
    r"^(Undeliverable|Delivery Status Notification|Mail delivery failed|Returned mail):",
    re.IGNORECASE,
)

# Read receipt check
_READ_RECEIPT_PATTERN = re.compile(
    r"^(Read|Delivered):\s",
    re.IGNORECASE,
)
```

### Fix 2: Add Self-Sent Email Detection

In `categorize_email()`, after loading user email, check if sender matches:
```python
if user_email and sender_email.lower() == user_email.lower():
    return EmailCategory(category="SKIP", reason="Self-sent email")
```

### Fix 3: Add Personal Domain Skip for Exa Research

In `email_context_gatherer.py:_research_recipient()`, expand the skip list:
```python
_PERSONAL_DOMAINS = {
    "gmail.com", "outlook.com", "hotmail.com", "yahoo.com",
    "live.com", "live.co.uk", "icloud.com", "aol.com",
    "protonmail.com", "mail.com", "msn.com",
}
```

### Fix 4: Debug Thread Fetching

The thread fetch via Composio is silently returning empty data. Add logging to `_fetch_thread()` to capture the raw Composio response before parsing.

### Fix 5: Link draft_context to email_drafts

Ensure `_save_context()` receives and stores the `draft_id` foreign key after the draft row is created in `email_drafts`.

---

## Appendix: Full Email Processing Pipeline

```
User's Outlook/Gmail Inbox
         ↓
[EmailAnalyzer.scan_inbox()]
    ├── Fetch last 24h emails via Composio (200 max)
    ├── For each email:
    │   ├── Rule 1: Privacy exclusion check → SKIP
    │   ├── Rule 2: No-reply sender pattern → SKIP
    │   ├── Rule 3: Mailing list headers → FYI
    │   ├── Rule 4: CC-only check → FYI
    │   ├── ⚠️ MISSING: Calendar response → should be SKIP/FYI
    │   ├── ⚠️ MISSING: Junk notification → should be SKIP
    │   ├── ⚠️ MISSING: Bounce/undeliverable → should be SKIP
    │   ├── ⚠️ MISSING: Self-sent → should be SKIP
    │   └── LLM Classification (Claude Sonnet, temp=0.2)
    │       ├── Returns: NEEDS_REPLY | FYI | SKIP
    │       └── Urgency: detect_urgency() signals + LLM urgency
    └── Log to email_scan_log
         ↓
[AutonomousDraftEngine.process_inbox()]
    ├── Group NEEDS_REPLY emails by thread
    ├── For each thread:
    │   ├── Dedup: existing draft? → skip
    │   ├── Already-replied? → skip
    │   ├── Active conversation? → defer 30min
    │   ├── Learning mode: sender in top 10? → skip if not
    │   ├── [EmailContextGatherer.gather_context()]
    │   │   ├── 1. Thread fetch (Composio) → currently NULL
    │   │   ├── 2. Exa recipient research → WORKING but inaccurate
    │   │   ├── 3. Recipient style profile → EMPTY
    │   │   ├── 4. Relationship history → EMPTY
    │   │   ├── 5. Corporate memory → EMPTY
    │   │   ├── 6. Calendar context → DISCONNECTED
    │   │   └── 7. CRM context → DISCONNECTED
    │   ├── [_generate_reply_draft()]
    │   │   ├── PersonaBuilder system prompt (with fallback)
    │   │   ├── Full context injected into user prompt
    │   │   ├── Claude Sonnet, temp=0.7
    │   │   └── JSON response: {subject, body}
    │   ├── Style scoring (digital_twin.score_style_match)
    │   ├── Confidence calculation (context richness)
    │   ├── ARIA notes generation
    │   ├── Save to email_drafts table
    │   └── Save to client (Outlook/Gmail Drafts folder)
    └── Update processing_run status
```
