# Email Draft Pipeline — End-to-End Diagnostic Report

**Generated:** 2026-02-23T03:29Z
**User ID:** `41475700-c1fb-4f66-8c56-77bd90b73abb`
**Target email:** "RE: ARIA Design Partnership - Overview for Your Review" from Rob Douglas `<rdouglas@savillex.com>`

---

## Executive Summary

The pipeline runs end-to-end without crashing, but **the generated draft is generic and fails to address Rob's specific points**. The root cause is a chain of data quality issues that starve the LLM of context.

**Draft produced:**
> Hi Rob, Thanks for confirming receipt. Take your time with the review - I know these partnership discussions require proper internal alignment. Happy to answer any questions that come up during your review process. Just let me know when you're ready to discuss next steps. Dhruv

**What Rob actually wrote:**
> Thank you for the meeting yesterday and for the delivery of the development proposal and partnership. I will review this over the coming days, discuss with our leadership teams and return back to you within 2 weeks. Ideally, I would like to kickoff our AI utilization and tooling by March 1. I have the ZoomInfo Copilot trial currently running with my team that kicked off in early Feb. This, along with your tool and another "top of funnel" AI utilization will potentially complete the investment and exploration into such tools for Savillex and our partners. When is a good date for you the week of March 8th to meet again and review?

**What the draft SHOULD address but doesn't:**
1. Rob's 2-week review timeline commitment
2. March 1 kickoff goal
3. ZoomInfo Copilot context (competitive intelligence!)
4. The explicit meeting request for week of March 8th
5. "Top of funnel AI utilization" — positioning ARIA alongside other tools

---

## Final Diagnostic Report

```
╔═══════════════════════════════════════════════════════════════╗
║            EMAIL DRAFT PIPELINE — DIAGNOSTIC REPORT           ║
╠═══════════════════════════════════════════════════════════════╣
║                                                               ║
║  STEP 1 — Email Fetch                                         ║
║  Email fetched: YES                                           ║
║  Body readable: YES                                           ║
║  Body type: dict {content, contentType}                       ║
║  Body contentType: html                                       ║
║                                                               ║
║  STEP 2 — Already Replied                                     ║
║  User already replied: ERROR (account_email is None)          ║
║  Detection would catch it: NO — crashes on None.lower()       ║
║                                                               ║
║  STEP 3 — Body Cleaning                                       ║
║  Clean body has real content: YES                             ║
║  Clean body length: 3,407 chars                               ║
║  Contains Rob's full message: YES                             ║
║                                                               ║
║  STEP 4 — Thread Fetch                                        ║
║  Thread messages found: 10 — BUT WRONG MESSAGES!              ║
║  Thread is polluted with unrelated emails                     ║
║  Thread summary generated: YES — but about wrong emails       ║
║  Summary talks about: CoffeeSpace, Wellfound, Eventbrite     ║
║  Summary should be about: ARIA Design Partnership             ║
║                                                               ║
║  STEP 5 — Context Sources                                     ║
║  Thread summary: DATA (but wrong — polluted thread)           ║
║  Recipient research: DATA (Exa found Rob on LinkedIn)         ║
║  Recipient style: DATA (greeting=Hi Rob, formality=0.5)      ║
║  Relationship history: DATA (3 emails, external_peer)         ║
║  Relationship health: NULL (trend=new despite 3 emails)       ║
║  Corporate memory: DATA (but low quality — see below)         ║
║  Calendar context: NULL (not connected)                       ║
║  CRM context: NULL (not connected)                            ║
║  Score: 5/7                                                   ║
║                                                               ║
║  STEP 6 — Digital Twin                                        ║
║  Writing style exists: YES                                    ║
║  Style length: 360 chars (telegraphic, efficient)             ║
║  Formatting patterns: {} (empty dict — not populated)         ║
║                                                               ║
║  STEP 7 — Recipient Profile                                   ║
║  Profile exists: YES                                          ║
║  Email count with this contact: 3                             ║
║  Greeting: "Hi Rob,"                                          ║
║  Signoff: None (literal None — should be a string)            ║
║                                                               ║
║  STEP 8 — LLM Prompt                                          ║
║  Contains email body: NO ← PRIMARY ROOT CAUSE                 ║
║  Contains thread summary: YES (but wrong summary)             ║
║  Contains writing style: YES                                  ║
║  Contains recipient name: YES                                 ║
║  Output format requested: JSON {subject, body}                ║
║  Has anti-hallucination: YES (guardrails section)             ║
║  Prompt length: 7,879 chars                                   ║
║                                                               ║
║  STEP 9 — LLM Response                                        ║
║  Response format: Valid JSON parsed to Pydantic               ║
║  Contains real context: NO — generic acknowledgment           ║
║  Contains hallucinations: NO (but overly vague)               ║
║  Body has <p> tags: YES                                       ║
║                                                               ║
║  STEP 10 — Parsing                                            ║
║  Body extracted cleanly: YES                                  ║
║  JSON wrapper removed: N/A (clean parse)                      ║
║  Final body is HTML: YES                                      ║
║                                                               ║
║  STEP 11 — Save                                               ║
║  DB body is clean HTML: YES                                   ║
║  Outlook body is clean HTML: YES                              ║
║  is_html flag set: YES (hardcoded True)                       ║
║  JSON wrapper in body: NO                                     ║
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝
```

---

## Broken Links Identified (9 total)

### BL-1: EmailCategory has no `body` field — CRITICAL
**Severity:** CRITICAL — Root cause of generic drafts
**File:** `backend/src/services/email_analyzer.py:33-47`
**File:** `backend/src/services/autonomous_draft_engine.py:1373`

`EmailCategory` model only stores `snippet` (first 200 chars of body). The full body from Composio is discarded during categorization. When `_build_reply_prompt` does:
```python
email_body = getattr(email, "body", None) or email.snippet
```
It gets `None` from `body` and falls back to `snippet` — only 200 characters. The LLM sees:

> Hi Dhruv, Thank you for the meeting yesterday and for the delivery of the development proposal and partnership. I will review this over the coming days, discuss with our leadership teams and return

It **never sees** the March 1 kickoff, ZoomInfo Copilot mention, or the March 8 meeting request. This is the single biggest reason drafts are generic.

**Fix:** Add `body: str = ""` to `EmailCategory` and populate it during categorization.

---

### BL-2: Thread fetch returns WRONG messages — CRITICAL
**Severity:** CRITICAL — Thread context is polluted
**File:** `backend/src/services/email_context_gatherer.py:583-671`

The `_fetch_outlook_thread()` call with `$filter=conversationId eq '...'` returned **10 messages from different senders** (Startup Boston, Eventbrite, CoffeeSpace, Wellfound, Rob Douglas). Only 1 of those 10 is actually from the Rob Douglas conversation.

The Outlook API `OUTLOOK_LIST_MESSAGES` action may not be properly filtering by conversationId, or the Composio action is ignoring the `$filter` parameter and returning the most recent inbox messages instead.

**Impact:**
- Thread summary describes "CoffeeSpace matches and Wellfound notifications" instead of the ARIA Design Partnership
- Thread messages in the prompt are raw HTML from unrelated emails, wasting ~4000 tokens
- Commitment extraction finds nothing because it's scanning the wrong emails

---

### BL-3: Thread message bodies are raw HTML — HIGH
**Severity:** HIGH — Token waste + confused LLM
**File:** `backend/src/services/email_context_gatherer.py:643-655`
**File:** `backend/src/services/autonomous_draft_engine.py:1406-1420`

Thread messages from `_fetch_outlook_thread` contain full HTML with `<html>`, `<head>`, `<style>`, CSS rules, etc. These are passed directly into the prompt:
```
- Rob Douglas: <html><head><meta http-equiv="Content-Type"...><style>@font-face{font-family:"Cambria Math"}...
```

The bodies are not cleaned/stripped before being put in the prompt. This wastes tokens and confuses the LLM's understanding of the thread.

**Fix:** Strip HTML tags from thread message bodies in `_fetch_outlook_thread()` before creating `ThreadMessage` objects.

---

### BL-4: `account_email` is None — HIGH
**Severity:** HIGH — Breaks reply detection and user identification
**File:** `backend/src/services/email_context_gatherer.py:724-763`
**DB:** `user_integrations` table

The `user_integrations` record for this user has `account_email: None`. This causes:
1. **Step 2 crash:** `account_email.lower()` throws `AttributeError: 'NoneType' object has no attribute 'lower'`
2. **`is_from_user` always False:** Every thread message shows `is_from_user: False`, so the system can't distinguish the user's own messages from received ones
3. **User-already-replied detection fails:** Can't detect if user replied because it can't identify user's messages

**Fix:** Populate `account_email` in `user_integrations` during OAuth connection. Add a fallback to fetch the user's email from the Outlook profile via Composio if not stored.

---

### BL-5: Corporate memory facts are generic contact stubs — MEDIUM
**Severity:** MEDIUM — Context noise, not intelligence
**File:** `backend/src/services/email_context_gatherer.py:1304+`

All 7 corporate memory facts for this contact are identical stubs:
```
Contact: rdouglas@savillex.com (unknown) - 2 interactions
```

These are email bootstrap artifacts, not actual corporate intelligence. The prompt's "Relevant company knowledge" section contains 5 copies of this same stub, contributing no useful context. It should contain facts like:
- "Savillex is evaluating AI tools including ZoomInfo Copilot"
- "Rob Douglas is VP Sales at Savillex, Eden Prairie, MN"
- "Savillex manufactures fluoropolymer solutions for life sciences"

---

### BL-6: Commitment extraction finds nothing — MEDIUM
**Severity:** MEDIUM — Misses actionable items
**File:** `backend/src/services/email_context_gatherer.py:1883+`

Despite Rob's email containing clear commitments:
- "I will review this over the coming days"
- "return back to you within 2 weeks"
- "Ideally, I would like to kickoff... by March 1"
- "When is a good date for you the week of March 8th?"

The commitments section shows: "No commitments detected."

**Root cause:** Likely because the thread fetch returned wrong messages (BL-2), so the commitment extractor analyzed unrelated emails.

---

### BL-7: Recipient signoff is literal "None" — LOW
**Severity:** LOW — Confusing instruction to LLM
**File:** `backend/src/services/autonomous_draft_engine.py:1355`

The prompt contains:
```
- Signoff style: None
```

This is a literal Python `None` rendered as string. The LLM interprets this as "no signoff specified" which is ambiguous. Should be "Use global style above" (the fallback text for greeting).

---

### BL-8: Relationship health shows "new" despite 3 emails — LOW
**Severity:** LOW — Incorrect relationship signal
**File:** `backend/src/services/email_context_gatherer.py:1232+`

The `_get_relationship_health()` method returns `trend=new` for Rob Douglas despite having 3 recorded email interactions and a recipient_writing_profile. The health calculation either isn't querying the right data or has a threshold that's too high.

---

### BL-9: CostGovernor `increment_usage_tracking` function signature mismatch — MEDIUM
**Severity:** MEDIUM — Usage tracking silently fails
**File:** `backend/src/core/cost_governor.py:190`

The code calls `increment_usage_tracking` with parameters `(p_cache_creation_tokens, p_cache_read_tokens, p_date, p_estimated_cost, p_input_tokens, p_output_tokens, p_thinking_tokens, p_user_id)` but the database function expects `(p_agent, p_date, p_estimated_cost_cents, p_extended_thinking_tokens, p_input_tokens, p_model, p_output_tokens, p_request_count, p_user_id)`. This means all LLM usage tracking silently fails with `PGRST202` error.

---

## Root Cause Chain

```
1. EmailCategory drops full body → only 200-char snippet survives
                 ↓
2. Thread fetch returns wrong messages → thread summary is about wrong emails
                 ↓
3. Thread bodies are raw HTML → wasted tokens on CSS/styles
                 ↓
4. account_email is None → can't identify user's messages in thread
                 ↓
5. Corporate memory is generic stubs → no real business intel
                 ↓
6. LLM receives: 200-char truncated email + wrong thread summary + generic facts
                 ↓
7. LLM produces: generic "thanks for confirming, take your time" response
                 ↓
8. Draft misses: March 1 kickoff, ZoomInfo context, March 8 meeting request
```

**Primary fix needed:** Add `body` field to `EmailCategory` and pass the full email body through the pipeline. This alone would dramatically improve draft quality.

**Secondary fixes:** Fix the thread fetch filter, strip HTML from thread messages, populate `account_email`.

---

## Raw Diagnostic Output

<details>
<summary>Click to expand full step-by-step output</summary>

### STEP 1 — Fetch Recent Emails from Outlook

```
Integration found: provider=outlook, connection_id=ca_8zqXsI5EEFPu..., account_email=None
Fetched 10 emails

Email 10 (SELECTED):
  Subject: RE: ARIA Design Partnership - Overview for Your Review
  Sender: Rob Douglas <rdouglas@savillex.com>
  Received: 2026-02-20T21:18:24Z
  ConversationId: AAQkADY2YzM4ZjIxLWRlOGYtNGFjZC04MDgwLTJmNDdiMDhhN2VjNgAQANpj2xEEpPtHqCZRwFvwd5k=
  hasAttachments: False
  Body type: dict {content: html, contentType: html}
```

### STEP 2 — Already Replied Check

```
ConversationId: AAQkADY2YzM4ZjIxLWRlOGYtNGFjZC04MDgwLTJmNDdiMDhhN2VjNgAQANpj2xEEpPtHqCZRwFvwd5k=
Thread messages found: 10
ERROR: account_email is None → crashes on None.lower()
```

### STEP 3 — Body Cleaning

```
Raw body type: dict
Body contentType: html
Cleaned body (3,407 chars):
  Hi Dhruv, Thank you for the meeting yesterday and for the delivery of the
  development proposal and partnership. I will review this over the coming days,
  discuss with our leadership teams and return back to you within 2 weeks.
  Ideally, I would like to kickoff our AI utilization and tooling by March 1.
  I have the ZoomInfo Copilot trial currently running with my team that kicked
  off in early Feb. This, along with your tool and another "top of funnel"
  AI utilization will potentially complete the investment and exploration into
  such tools for Savillex and our partners. When is a good date for you the
  week of March 8th to meet again and review?

  Regards, Rob
```

### STEP 4 — Thread Fetch

```
Thread messages: 10 (POLLUTED — includes emails from 8 different senders)
  [1] Startup Boston <calendar-invite@lu.ma> — NOT part of this thread
  [2] Stephanie Roulic <noreply@luma-mail.com> — NOT part of this thread
  [3] Eventbrite <marketing@plans.eventbrite.com> — NOT part of this thread
  ...
  [10] Rob Douglas <rdouglas@savillex.com> — ACTUAL thread message

Thread summary (WRONG): "This appears to be a collection of automated notification
emails rather than a conversation... CoffeeSpace match notification..."
```

### STEP 5 — Context Sources

```
Source 1 (Thread):        DATA (but polluted with wrong messages)
Source 2 (Recipient):     DATA — Rob Douglas, VP Sales at Savillex (from Exa/LinkedIn)
Source 3 (Recipient Style): DATA — "Hi Rob,", formality 0.5, 3 emails
Source 4 (Relationship):  DATA — 3 emails, external_peer
Source 5 (Health):        NULL — trend="new" (incorrect)
Source 6 (Corporate):     DATA — 7 generic stubs ("Contact: rdouglas@... - 2 interactions")
Source 7 (Calendar):      NULL — not connected
Source 8 (CRM):           NULL — not connected
Score: 5/7
```

### STEP 6 — Digital Twin

```
Writing style: "The writer employs a highly functional, telegraphic style typical
of technical communication, prioritizing efficiency and clarity over elaboration."
Tone: simple
Formality: business
Formatting patterns: {} (empty)
```

### STEP 7 — Recipient Profile

```
Greeting: Hi Rob,
Signoff: None
Formality: 0.5
Tone: balanced
Email count: 3
```

### STEP 8 — LLM Prompt

```
CRITICAL CHECK:
  getattr(email, 'body', None) = None
  email.snippet = "Hi Dhruv, Thank you for the meeting yesterday..." (200 chars)
  → Prompt uses SNIPPET only (200 chars, truncated before March 1/ZoomInfo/meeting request)

Prompt length: 7,879 chars
"The email you're replying to" section shows only 200-char snippet.
Thread messages section shows raw HTML from wrong emails.
```

### STEP 9 — LLM Response

```
Subject: Re: ARIA Design Partnership - Overview for Your Review
Body: <p>Hi Rob,</p><p>Thanks for confirming receipt. Take your time with the
review - I know these partnership discussions require proper internal alignment.
</p><p>Happy to answer any questions that come up during your review process.
Just let me know when you're ready to discuss next steps.</p><p>Dhruv</p>

→ Generic. Misses ZoomInfo, March 1, March 8, all specific content.
```

### STEP 10-11 — Parse & Save

```
Body is clean HTML: YES
is_html flag: TRUE
JSON wrapper: NONE
Parse and save steps work correctly.
```

</details>

---

## Priority Fix Order

| # | Fix | Severity | Impact | Effort |
|---|-----|----------|--------|--------|
| 1 | Add `body` field to `EmailCategory` | CRITICAL | Draft quality jumps dramatically | Low |
| 2 | Fix thread fetch `$filter` for Outlook | CRITICAL | Thread summary becomes relevant | Medium |
| 3 | Strip HTML from thread message bodies | HIGH | Saves tokens, cleaner prompt | Low |
| 4 | Populate `account_email` in integrations | HIGH | Enables reply detection | Low |
| 5 | Fix `increment_usage_tracking` signature | MEDIUM | Usage tracking works again | Low |
| 6 | Enrich corporate memory beyond stubs | MEDIUM | Better business context | Medium |
| 7 | Fix signoff `None` → fallback string | LOW | Cleaner prompt instruction | Trivial |
| 8 | Fix relationship health "new" threshold | LOW | Accurate relationship signals | Low |
