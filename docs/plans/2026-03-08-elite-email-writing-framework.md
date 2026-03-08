# Elite Email Writing Framework - Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a universal email writing framework injected into ALL email generation LLM calls, systemically improving email quality across every draft type.

**Architecture:** Single constant `ELITE_EMAIL_FRAMEWORK` in a new `backend/src/prompts/email_writing_framework.py` module, imported and prepended to every LLM prompt that generates email content. No type-specific templates — one framework for all emails.

**Tech Stack:** Python (new module + imports into existing services/agents)

---

### Task 1: Create the email writing framework module

**Files:**
- Create: `backend/src/prompts/__init__.py`
- Create: `backend/src/prompts/email_writing_framework.py`

**Step 1: Create the prompts directory**

```bash
mkdir -p backend/src/prompts
```

**Step 2: Create empty `__init__.py`**

Create `backend/src/prompts/__init__.py` with empty content.

**Step 3: Create `email_writing_framework.py`**

Create `backend/src/prompts/email_writing_framework.py` with:

```python
"""
Universal email writing principles. Applied to ALL emails.
Edit here to improve all email output globally.
"""

ELITE_EMAIL_FRAMEWORK = """
## ARIA Email Writing Principles

You will receive context about the recipient, their company, relevant market signals, relationship history, and the sender's writing style. This context is the foundation of the email. Build the email around it.

Apply ALL of these principles:

1. LEAD WITH RELEVANCE
The first sentence must make the recipient think "this is about MY situation." Use the signal, event, or context you've been given to open with something specific to them. Generic openers get deleted.

2. RECIPIENT IS THE HERO
Frame everything around the recipient's world. Minimize "we/our" language. Maximize "you/your" language. The sender's capabilities only matter in terms of what they mean for the recipient.

3. EVIDENCE, NOT ADJECTIVES
Replace every vague claim with a specific fact from the context you've been given. Instead of "superior performance," cite an actual metric. Instead of "industry-leading support," cite an actual response time. CRITICAL: Only use data points, customer references, or metrics that appear in your context. If the context does not include a specific number, DO NOT invent one. No vague superlatives: never use "superior", "best-in-class", "industry-leading", "next-generation", "cutting-edge".

4. EARN EVERY SENTENCE
Senior professionals scan, not read. Default to short. If removing a sentence doesn't weaken the email, remove it. One ask per email. When replying, match the length of what you're replying to.

5. OFFER VALUE BEFORE ASKING FOR TIME
Lead with something useful: a relevant resource, a specific insight, a comparison. Then make the ask easy. "I put together X for this -- happy to send it over" beats "Can we schedule a call?"

6. SUBJECT LINES
Make subject lines specific and relevant. If a subject line is already provided or this is a reply in an existing thread, do not change the subject line.

7. SOUND HUMAN
Write like a knowledgeable peer. No marketing buzzwords (synergy, leverage, optimize, solution, partnership). Match the sender's writing style -- their greeting, sign-off, sentence length, formality level. If a style profile is provided, follow it closely. Never use em dashes.

8. CONTEXTUAL EMPATHY
When referencing disruptions or competitor issues, lead with understanding of the impact on the recipient. Never appear opportunistic.
"""
```

**Step 4: Verify file exists**

```bash
python -c "from src.prompts.email_writing_framework import ELITE_EMAIL_FRAMEWORK; print('OK:', len(ELITE_EMAIL_FRAMEWORK), 'chars')"
```

Expected: `OK: <number> chars`

**Step 5: Commit**

```bash
git add backend/src/prompts/__init__.py backend/src/prompts/email_writing_framework.py
git commit -m "feat: add universal elite email writing framework"
```

---

### Task 2: Inject framework into DraftService

**Files:**
- Modify: `backend/src/services/draft_service.py`

**Step 1: Add import**

At the top of `draft_service.py`, add:

```python
from src.prompts.email_writing_framework import ELITE_EMAIL_FRAMEWORK
```

**Step 2: Inject into `EMAIL_GENERATION_PROMPT`**

Find the `EMAIL_GENERATION_PROMPT` constant (around line 23) and prepend the framework. Change:

```python
EMAIL_GENERATION_PROMPT = """You are ARIA, an AI assistant helping a sales professional draft emails.
Generate a professional email based on the following parameters.
...
```

To:

```python
EMAIL_GENERATION_PROMPT = ELITE_EMAIL_FRAMEWORK + """
You are ARIA, an AI assistant helping a sales professional draft emails.
Generate a professional email based on the following parameters.
...
```

**Step 3: Inject into `EMAIL_REGENERATION_PROMPT`**

Find `EMAIL_REGENERATION_PROMPT` (around line 485) and similarly prepend:

```python
EMAIL_REGENERATION_PROMPT = ELITE_EMAIL_FRAMEWORK + """
You are ARIA, an AI assistant helping a sales professional draft emails.
Rewrite the email draft based on the parameters below.
...
```

**Step 4: Commit**

```bash
git add backend/src/services/draft_service.py
git commit -m "feat: inject elite email framework into DraftService"
```

---

### Task 3: Inject framework into AutonomousDraftEngine

**Files:**
- Modify: `backend/src/services/autonomous_draft_engine.py`

**Step 1: Add import**

At the top of `autonomous_draft_engine.py`, add:

```python
from src.prompts.email_writing_framework import ELITE_EMAIL_FRAMEWORK
```

**Step 2: Inject into `_FALLBACK_REPLY_PROMPT`**

Find `_FALLBACK_REPLY_PROMPT` (around line 118) and prepend. Change:

```python
_FALLBACK_REPLY_PROMPT = """You are ARIA, an AI assistant drafting an email reply."""
```

To:

```python
_FALLBACK_REPLY_PROMPT = ELITE_EMAIL_FRAMEWORK + """
You are ARIA, an AI assistant drafting an email reply."""
```

**Step 3: Inject into PersonaBuilder path**

In `_generate_reply_draft()`, find where the `system_prompt` is built from PersonaBuilder (around lines 1121-1133). After the persona builder returns the system prompt, prepend the framework. Look for the code that sets `system_prompt` from persona builder and add:

```python
system_prompt = ELITE_EMAIL_FRAMEWORK + "\n\n" + system_prompt
```

This ensures the framework is applied regardless of whether PersonaBuilder or the fallback prompt is used.

**Step 4: Commit**

```bash
git add backend/src/services/autonomous_draft_engine.py
git commit -m "feat: inject elite email framework into AutonomousDraftEngine"
```

---

### Task 4: Inject framework into ProactiveFollowupEngine

**Files:**
- Modify: `backend/src/services/proactive_followup_engine.py`

**Step 1: Add import**

At the top of `proactive_followup_engine.py`, add:

```python
from src.prompts.email_writing_framework import ELITE_EMAIL_FRAMEWORK
```

**Step 2: Inject into system prompt**

In `_generate_followup_body()` (around line 377), find the system prompt construction and prepend. Change:

```python
system_prompt = (
    "You are ARIA, an AI assistant drafting emails on behalf of a user. "
    "Match their writing style. Output HTML email body only."
)
```

To:

```python
system_prompt = ELITE_EMAIL_FRAMEWORK + (
    "\n\nYou are ARIA, an AI assistant drafting emails on behalf of a user. "
    "Match their writing style. Output HTML email body only."
)
```

**Step 3: Also inject when PersonaBuilder provides prompt**

If PersonaBuilder returns a prompt (around lines 382-394), prepend the framework there too:

```python
system_prompt = ELITE_EMAIL_FRAMEWORK + "\n\n" + persona_prompt
```

**Step 4: Commit**

```bash
git add backend/src/services/proactive_followup_engine.py
git commit -m "feat: inject elite email framework into ProactiveFollowupEngine"
```

---

### Task 5: Inject framework into ScribeAgent

**Files:**
- Modify: `backend/src/agents/scribe.py`

**Step 1: Add import**

At the top of `scribe.py`, add:

```python
from src.prompts.email_writing_framework import ELITE_EMAIL_FRAMEWORK
```

**Step 2: Inject into `_draft_email()` hardcoded fallback prompt**

In `_draft_email()`, find the hardcoded fallback system prompt (around lines 575-580) and prepend. Change:

```python
hardcoded_prompt = (
    "You are a professional email writer for life sciences commercial teams. "
    ...
)
```

To:

```python
hardcoded_prompt = ELITE_EMAIL_FRAMEWORK + (
    "\n\nYou are a professional email writer for life sciences commercial teams. "
    ...
)
```

**Step 3: Inject into PersonaBuilder path**

In `_draft_email()`, where PersonaBuilder provides the system prompt (around lines 583-589), prepend the framework:

```python
system_prompt = ELITE_EMAIL_FRAMEWORK + "\n\n" + persona_prompt
```

**Step 4: Commit**

```bash
git add backend/src/agents/scribe.py
git commit -m "feat: inject elite email framework into ScribeAgent"
```

---

### Task 6: Verify all injection points

**Step 1: Grep for framework import across all files**

```bash
grep -rn "ELITE_EMAIL_FRAMEWORK\|email_writing_framework" backend/src/
```

Expected: Hits in all 5 files:
- `backend/src/prompts/email_writing_framework.py` (definition)
- `backend/src/services/draft_service.py` (import + usage)
- `backend/src/services/autonomous_draft_engine.py` (import + usage)
- `backend/src/services/proactive_followup_engine.py` (import + usage)
- `backend/src/agents/scribe.py` (import + usage)

**Step 2: Verify import works**

```bash
cd backend && python -c "from src.prompts.email_writing_framework import ELITE_EMAIL_FRAMEWORK; print('Import OK')"
```

**Step 3: Run typecheck**

```bash
cd backend && python -m py_compile src/prompts/email_writing_framework.py && echo "Compile OK"
cd backend && python -m py_compile src/services/draft_service.py && echo "Compile OK"
cd backend && python -m py_compile src/services/autonomous_draft_engine.py && echo "Compile OK"
cd backend && python -m py_compile src/services/proactive_followup_engine.py && echo "Compile OK"
cd backend && python -m py_compile src/agents/scribe.py && echo "Compile OK"
```

**Step 4: Final commit (if any verification fixes needed)**

```bash
git add -A && git commit -m "fix: address any verification issues"
```

---

## Notes

### Files NOT modified (intentionally):

- **HunterAgent** (`hunter.py`): Does company research and contact finding via LLM, but does NOT generate email drafts. Its prompts request JSON data (company info, contacts), not email content.
- **EmailAnalyzer** (`email_analyzer.py`): Classifies incoming emails, does NOT generate draft content.
- **Scribe `_draft_document()`**: Generates documents (briefs, reports, proposals), not emails. The framework is email-specific.

### Injection strategy:

The framework is prepended to the **system prompt** in all cases, which means it takes precedence over specific task instructions. The existing context (recipient info, relationship data, style profile, etc.) flows through the user prompt and remains untouched.

### Single edit point:

To improve all email quality globally, edit `backend/src/prompts/email_writing_framework.py`. Every email generation path reads from this one constant.
