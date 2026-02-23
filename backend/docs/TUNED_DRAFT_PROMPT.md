# Tuned Draft Prompt — Voice Fidelity & Anti-Hallucination

**Date:** 2026-02-23
**Target:** `autonomous_draft_engine.py` → `_build_reply_prompt()`

---

## Changes Made

### 1. Anti-Hallucination Rule (placed early in prompt)

```
## CRITICAL: Anti-Hallucination Rule
ONLY reference information present in the email and thread below.
Do NOT invent topics, projects, details, or context the sender didn't mention.
If the sender mentioned something specific, address it directly.
If you don't have information about something, do NOT make it up — either
skip it or suggest following up.
```

### 2. Banned Filler Phrases

```
## Banned Phrases — Do NOT use any of these:
- "I hope this email finds you well"
- "I hope this finds you well"
- "Thank you for reaching out"
- "Thanks for reaching out"
- "Please don't hesitate to"
- "Don't hesitate to reach out"
- "Looking forward to your response"
- "I appreciate your time"
- "Per our conversation"
- "As per my last email"
- "Just circling back"
- "Just following up"
- "I wanted to touch base"
- "Let's circle back on this"
- "At your earliest convenience"
- "Synergy", "leverage" (as verb), "alignment", "bandwidth"
- "Moving forward"
- Any variation of these corporate filler phrases.
Write like a real person, not a template.
```

### 3. Raw Writing Style from Digital Twin

The raw `writing_style` text from `digital_twin_profiles` is now fetched and appended to the style guidelines section as a "Voice profile" description. This gives the LLM a prose description of the user's writing style in addition to the structured guidelines.

```python
voice_section = f"## Writing Style Guide\n{style_guidelines}"
if raw_writing_style:
    voice_section += f"\n\nVoice profile: {raw_writing_style}"
```

### 4. Reference Extraction Step (Chain-of-Thought)

```
## Step 1: Extract Key Points (do this mentally before writing)
Before writing the reply, identify every specific point, question, date,
request, or commitment from the sender's email above. Your reply MUST
address each one. Do not skip any.

## Step 2: Write the Reply
Write a reply that:
1. Addresses EVERY specific point the sender raised — dates, requests, questions, proposals
2. Sounds EXACTLY like {user_name} — same greeting, tone, length, signoff
3. References specific details from the sender's email (names, dates, topics they mentioned)
4. Is direct and action-oriented — include next steps, dates, or asks where appropriate
5. Is ready to send with minimal editing
6. Uses clean HTML formatting as described in the Email Formatting section
```

### 5. New Helper Method: `_get_raw_writing_style`

Added `_get_raw_writing_style(user_id)` to fetch the prose `writing_style` field from `digital_twin_profiles`, complementing the structured `get_style_guidelines()` from DigitalTwin.

---

## Prompt Structure (section order)

1. Identity — "You are drafting an email reply AS {user_name}"
2. **Anti-Hallucination Rule** ← NEW
3. **Banned Phrases** ← NEW
4. Writing Style Guide + **Voice Profile** ← ENHANCED
5. Recipient-specific style (greeting, signoff, formality)
6. Tone guidance
7. Email formatting instructions
8. **The email being replied to** (full body)
9. Earlier messages (if consolidation)
10. Attachments
11. Full conversation thread
12. Recipient research
13. Relationship history
14. Outstanding commitments
15. Calendar context
16. CRM context
17. Corporate memory
18. Special instructions (if any)
19. Strategic guardrails
20. **Step 1: Extract Key Points** ← NEW
21. **Step 2: Write the Reply** ← ENHANCED

---

## Evaluation Results

### Before Tuning (from diagnostic report)
```
Draft: "Hi Rob, Thanks for confirming receipt. Take your time with the
review - I know these partnership discussions require proper internal
alignment. Happy to answer any questions that come up during your review
process. Just let me know when you're ready to discuss next steps. Dhruv"

Score: 0/8 — Generic, misses all specific content
```

### After Tuning
```
Draft: "Hi Rob, Perfect. Two weeks works well for the review timeline.
March 1 kickoff aligns with our capacity. Good to know about the ZoomInfo
trial running since early Feb. Would be useful to understand how you're
evaluating the different tools - happy to discuss positioning when we
reconnect. Week of March 8th works. I'll send some time slots that work
on my end. Best, Dhruv"

Score: 7/8 — Addresses all key points, no filler, direct tone
```

| Criterion | Before | After |
|-----------|--------|-------|
| Rob's 2-week review timeline | FAIL | PASS |
| March 1 kickoff goal | FAIL | PASS |
| ZoomInfo Copilot context | FAIL | PASS |
| March 8 meeting request | FAIL | PASS |
| No filler phrases | FAIL | PASS |
| References specific content | FAIL | PASS (natural) |
| Has greeting | PASS | PASS |
| Has signoff | PASS | PASS |
