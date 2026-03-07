# Draft Page Fixes + ARIA Reasoning Engine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix 6 broken interactions on the draft detail page and build the ARIA Reasoning Engine — a systemic LLM-powered capability that generates expert strategic reasoning for every ARIA work product.

**Architecture:** Part A fixes frontend bugs (tone buttons not updating display, style match percentage, edit mode body editing, dead "Ask ARIA" input, non-functional refinements). Part B creates a new `ReasoningEngine` class that makes a dedicated LLM call at work-product creation time, stores the narrative in a new `aria_reasoning` DB column, and surfaces it in the WhyIWroteThis module.

**Tech Stack:** React/TypeScript (frontend), Python/FastAPI (backend), Supabase (DB), Anthropic Claude API (LLM)

---

## Current State Analysis

After thorough codebase review, here's what actually works and what's broken:

### Already Working (no fix needed):
- **Tone buttons** (BUG 1): The `handleRegenerate` handler at `DraftDetailPage.tsx:96-105` already calls `regenerateDraft.mutateAsync`, and `useRegenerateDraft` at `useDrafts.ts:84-97` already updates both caches (`draftKeys.detail` and `intel-panel`). The handler at line 102-103 already syncs `editedBody`. The loading overlay at lines 342-354 already exists. **This flow works correctly.**
- **Style match percentage** (BUG 2): `DraftDetailPage.tsx:409` already uses `Math.round(draft.style_match_score * 100)`. `ToneModule.tsx:45` already uses `Math.round(draft.style_match_score * 100)`. `WhyIWroteThisModule.tsx:151` already uses `Math.round(draft.style_match_score * 100)`. **Already fixed.**
- **Edit mode body textarea** (BUG 3): `DraftDetailPage.tsx:355-366` already has a textarea for `editedBody`. `handleSave` at line 84 already includes `body: editedBody`. **Already works.**
- **"Ask ARIA about this"** (BUG 4): `ChatInputModule.tsx` exists but is **NOT rendered** in the draft detail route (see `IntelPanel.tsx:70-81` — it's not listed). **No dead UI element to remove.**
- **Suggested Refinements** (BUG 5/6): `SuggestedRefinementsModule.tsx:66-87` already has `handleRefinement` that calls `regenerateDraft.mutateAsync` with `additional_context`. Buttons at lines 102-144 already have `onClick` handlers and loading states. **Already wired and functional.**

### Actually Broken:
1. **Tone regeneration overwrites `aria_notes`** — `drafts.py:392-395` replaces the original strategic notes with generic "ARIA regenerated with X tone" text. This destroys the original reasoning.
2. **`aria_reasoning` column doesn't exist** — There's no dedicated column for the LLM-generated reasoning narrative. The existing `aria_notes` field stores LLM-generated strategy notes but gets overwritten on regeneration.
3. **No Reasoning Engine** — No dedicated LLM call generates strategic reasoning narratives at work-product creation time.
4. **WhyIWroteThis module uses hardcoded text** — `WhyIWroteThisModule.tsx:102-104` has hardcoded generic text instead of showing stored reasoning.
5. **Standard draft `style_match_score` in factors list** — `WhyIWroteThisModule.tsx:170` shows raw decimal (`0.85%`) instead of percentage for standard (non-intelligence) drafts.

---

## Task 1: Add `aria_reasoning` column to database

**Files:**
- Create: `backend/supabase/migrations/20260307000000_add_aria_reasoning.sql`

**Step 1: Create migration file**

```sql
-- Add aria_reasoning column to email_drafts for LLM-generated strategic reasoning
ALTER TABLE email_drafts ADD COLUMN IF NOT EXISTS aria_reasoning TEXT;

-- Add aria_reasoning column to aria_action_queue for proposal reasoning
ALTER TABLE aria_action_queue ADD COLUMN IF NOT EXISTS aria_reasoning TEXT;

-- Add aria_reasoning column to proactive_proposals
ALTER TABLE proactive_proposals ADD COLUMN IF NOT EXISTS aria_reasoning TEXT;
```

**Step 2: Run migration**

Run: `cd /Users/dhruv/aria/backend && PYTHONPATH=. python3 -c "from src.db.supabase import SupabaseClient; db = SupabaseClient.get_client(); db.rpc('exec_sql', {'sql': open('supabase/migrations/20260307000000_add_aria_reasoning.sql').read()}).execute(); print('Migration applied')"`

If the RPC doesn't work, apply directly via Supabase dashboard or:
```bash
cd /Users/dhruv/aria/backend && PYTHONPATH=. python3 -c "
from src.db.supabase import SupabaseClient
db = SupabaseClient.get_client()
# Test by selecting the column
result = db.table('email_drafts').select('aria_reasoning').limit(1).execute()
print('Column exists:', 'aria_reasoning' in str(result))
"
```

**Step 3: Commit**

```bash
git add backend/supabase/migrations/20260307000000_add_aria_reasoning.sql
git commit -m "feat: add aria_reasoning column to email_drafts, aria_action_queue, proactive_proposals"
```

---

## Task 2: Create the Reasoning Engine

**Files:**
- Create: `backend/src/intelligence/reasoning_engine.py`

**Step 1: Create the reasoning engine module**

Create `backend/src/intelligence/reasoning_engine.py` with the full `ReasoningEngine` class as specified in the user's prompt (the complete code is provided there). Key methods:
- `generate_email_reasoning()` — For competitive displacement emails
- `generate_proposal_reasoning()` — For proactive proposals/action cards
- `generate_conference_reasoning()` — For conference recommendations
- `_fallback_email_reasoning()` — Static fallback if LLM fails
- `_fallback_proposal_reasoning()` — Static fallback for proposals

Important implementation notes:
- The `generate_response` method on `LLMClient` returns a **plain string** (see `llm.py:662`), NOT a dict. So the response handling must be:
  ```python
  reasoning = str(response).strip()  # NOT response.get("content", "")
  ```
- Use `TaskType.ANALYST_RESEARCH` for email/proposal reasoning (high quality)
- Use `TaskType.CAUSAL_CLASSIFY` for conference reasoning (lighter model)
- The `task_type` parameter on `generate_response` is just called `task` (see signature at `llm.py:545-555`)

**Step 2: Verify it imports correctly**

Run: `cd /Users/dhruv/aria/backend && PYTHONPATH=. python3 -c "from src.intelligence.reasoning_engine import ReasoningEngine; print('OK')"`
Expected: `OK`

**Step 3: Commit**

```bash
git add backend/src/intelligence/reasoning_engine.py
git commit -m "feat: add ARIA Reasoning Engine for strategic narrative generation"
```

---

## Task 3: Wire ReasoningEngine into ActionExecutor

**Files:**
- Modify: `backend/src/intelligence/action_executor.py:119-228` (`_execute_displacement_outreach`)
- Modify: `backend/src/intelligence/action_executor.py:445-543` (`_save_email_draft`)

**Step 1: Add reasoning generation to `_execute_displacement_outreach`**

After line 212 (after `email_data = await self._generate_email_via_llm(...)`) and before line 214 (before `return await self._save_email_draft(...)`), add:

```python
        # 4b. Generate ARIA strategic reasoning narrative
        aria_reasoning = ""
        try:
            from src.intelligence.reasoning_engine import ReasoningEngine
            reasoning_engine = ReasoningEngine(self._db)

            # Get user's active goals for context
            goals_result = (
                self._db.table("goals")
                .select("title, goal_type, status")
                .eq("user_id", user_id)
                .in_("status", ["active", "in_progress", "plan_ready"])
                .limit(5)
                .execute()
            )

            aria_reasoning = await reasoning_engine.generate_email_reasoning(
                user_company=user_company,
                competitor_name=company_name,
                signal_context=insight_content[:500],
                competitive_positioning=competitive_context,
                email_body=email_data.get("body", ""),
                user_goals=goals_result.data if goals_result.data else [],
                digital_twin=writing_style,
            )
        except Exception as e:
            logger.warning("[ActionExecutor] Reasoning generation failed: %s", e)
```

**Step 2: Add `aria_reasoning` parameter to `_save_email_draft`**

Add `aria_reasoning: str = ""` parameter to the method signature.

In the `insert_data` dict (line 478-501), add:
```python
"aria_reasoning": aria_reasoning if aria_reasoning else None,
```

**Step 3: Pass `aria_reasoning` through the `_save_email_draft` call**

Update the call at line 215:
```python
        return await self._save_email_draft(
            user_id=user_id,
            email_data=email_data,
            purpose="competitive_displacement",
            draft_type="competitive_displacement",
            company_name=company_name,
            insight_id=insight_id,
            competitive_context=competitive_context,
            differentiation=differentiation,
            weaknesses=weaknesses,
            pricing=pricing,
            insight_content=insight_content,
            entity_type=payload.get("entity_type"),
            aria_reasoning=aria_reasoning,  # NEW
        )
```

**Step 4: Verify syntax**

Run: `cd /Users/dhruv/aria/backend && python3 -c "import ast; ast.parse(open('src/intelligence/action_executor.py').read()); print('Syntax OK')"`

**Step 5: Commit**

```bash
git add backend/src/intelligence/action_executor.py
git commit -m "feat: wire ReasoningEngine into email draft creation pipeline"
```

---

## Task 4: Wire ReasoningEngine into ActionRouter proposals

**Files:**
- Modify: `backend/src/intelligence/action_router.py:303-402` (`_create_proposal`)

**Step 1: Add reasoning generation to `_create_proposal`**

After building `comp_context` (after line 343) and before inserting into `proactive_proposals` (before line 345), add:

```python
            # Generate strategic reasoning narrative
            aria_reasoning = ""
            try:
                from src.intelligence.reasoning_engine import ReasoningEngine
                reasoning_engine = ReasoningEngine(self._db)

                # Get user's company name for context
                user_company_name = "our company"
                try:
                    profile = (
                        self._db.table("user_profiles")
                        .select("company_id")
                        .eq("id", user_id)
                        .limit(1)
                        .execute()
                    )
                    if profile.data and profile.data[0].get("company_id"):
                        company_result = (
                            self._db.table("companies")
                            .select("name")
                            .eq("id", profile.data[0]["company_id"])
                            .limit(1)
                            .execute()
                        )
                        if company_result.data:
                            user_company_name = company_result.data[0]["name"]
                except Exception:
                    pass

                aria_reasoning = await reasoning_engine.generate_proposal_reasoning(
                    user_company=user_company_name,
                    competitor_name=company,
                    entity_type=entity_type,
                    signal_context=context.get("event_text", "") or content[:300],
                    insight_content=content,
                    competitive_positioning=comp_context,
                )
            except Exception as e:
                logger.warning("[ActionRouter] Reasoning generation failed: %s", e)
```

**Step 2: Add `aria_reasoning` to both database inserts**

In the `proactive_proposals` insert (line 345-366), add to `proposal_data`:
```python
"aria_reasoning": aria_reasoning if aria_reasoning else None,
```

In the `aria_action_queue` insert (line 380-392), add:
```python
"aria_reasoning": aria_reasoning if aria_reasoning else None,
```

**Step 3: Verify syntax**

Run: `cd /Users/dhruv/aria/backend && python3 -c "import ast; ast.parse(open('src/intelligence/action_router.py').read()); print('Syntax OK')"`

**Step 4: Commit**

```bash
git add backend/src/intelligence/action_router.py
git commit -m "feat: wire ReasoningEngine into proactive proposal creation"
```

---

## Task 5: Fix tone regeneration to preserve `aria_reasoning` and `aria_notes`

**Files:**
- Modify: `backend/src/api/routes/drafts.py:389-396` (the DB update in `_regenerate_intelligence_draft`)

**Step 1: Fix the DB update to preserve original notes and reasoning**

Replace the update at lines 389-396:

```python
    # Build update data - preserve aria_reasoning across tone changes
    update_data = {
        "body": new_body,
        "tone": db_tone,
    }

    # Append tone change info to aria_notes instead of replacing
    existing_notes = draft_data.get("aria_notes", "")
    tone_note = f" | Regenerated with {tone_value} tone."
    if additional_context:
        tone_note += f" Refinement: {additional_context[:100]}"

    # Only append if not already appended (idempotent)
    if "Regenerated with" not in existing_notes:
        update_data["aria_notes"] = existing_notes + tone_note
    else:
        # Replace just the regeneration suffix
        base_notes = existing_notes.split(" | Regenerated with")[0]
        update_data["aria_notes"] = base_notes + tone_note

    # Never overwrite aria_reasoning - it's about WHY the email was written, not what tone it's in

    db.table("email_drafts").update(update_data).eq("id", draft_id).execute()
```

**Step 2: Also add `aria_reasoning` to the select in the draft_check query**

At line 214, add `aria_reasoning` to the select:
```python
.select("draft_type, competitive_positioning, context, body, aria_notes, insight_id, aria_reasoning")
```

**Step 3: Verify syntax**

Run: `cd /Users/dhruv/aria/backend && python3 -c "import ast; ast.parse(open('src/api/routes/drafts.py').read()); print('Syntax OK')"`

**Step 4: Commit**

```bash
git add backend/src/api/routes/drafts.py
git commit -m "fix: preserve aria_reasoning and aria_notes across tone regeneration"
```

---

## Task 6: Add `aria_reasoning` to backend response model

**Files:**
- Modify: `backend/src/models/email_draft.py:156-165` (EmailDraftResponse)

**Step 1: Add `aria_reasoning` field to EmailDraftResponse**

After line 165 (`insight_id` field), add:

```python
    aria_reasoning: str | None = Field(
        None, description="LLM-generated strategic reasoning narrative explaining ARIA's decisions"
    )
```

**Step 2: Verify syntax**

Run: `cd /Users/dhruv/aria/backend && python3 -c "import ast; ast.parse(open('src/models/email_draft.py').read()); print('Syntax OK')"`

**Step 3: Commit**

```bash
git add backend/src/models/email_draft.py
git commit -m "feat: add aria_reasoning field to EmailDraftResponse model"
```

---

## Task 7: Add `aria_reasoning` to frontend TypeScript types

**Files:**
- Modify: `frontend/src/api/drafts.ts:30-59` (EmailDraft interface)

**Step 1: Add `aria_reasoning` to EmailDraft interface**

After line 58 (`insight_id?: string;`), add:
```typescript
  aria_reasoning?: string;
```

**Step 2: Verify TypeScript compiles**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit 2>&1 | head -20`

**Step 3: Commit**

```bash
git add frontend/src/api/drafts.ts
git commit -m "feat: add aria_reasoning field to EmailDraft TypeScript interface"
```

---

## Task 8: Update WhyIWroteThisModule to display `aria_reasoning`

**Files:**
- Modify: `frontend/src/components/shell/intel-modules/WhyIWroteThisModule.tsx:66-155`

**Step 1: Add `aria_reasoning` display as primary reasoning**

The intelligence draft section (starting at line 66) should check for `aria_reasoning` first. Replace the entire intelligence draft rendering block (lines 66-155) with:

```tsx
  if (isIntelligenceDraft && draft) {
    // If aria_reasoning exists (LLM-generated narrative), show it as primary
    if ((draft as any).aria_reasoning) {
      return (
        <div data-aria-id="intel-why-wrote" className="space-y-3">
          <h3
            className="font-sans text-[11px] font-medium uppercase tracking-wider"
            style={{ color: 'var(--text-secondary)' }}
          >
            Why I Wrote This
          </h3>
          <div className="text-sm text-slate-700 leading-relaxed whitespace-pre-line">
            {(draft as any).aria_reasoning}
          </div>
          {draft.style_match_score !== undefined && (
            <div className="flex items-center gap-2 text-xs text-slate-500 pt-1 border-t border-slate-200">
              <span>Written in your voice</span>
              <span className="font-medium">{Math.round(draft.style_match_score * 100)}% style match</span>
            </div>
          )}
        </div>
      );
    }

    // Fallback: structured sections for drafts created before reasoning engine
    const competitivePositioning = draft.competitive_positioning as CompetitivePositioning | undefined;
    // ... (keep existing structured code for lines 67-155)
```

Note: Since the `EmailDraft` type from `@/api/drafts` now includes `aria_reasoning` (from Task 7), we can use `draft.aria_reasoning` directly instead of `(draft as any).aria_reasoning`. But the intel panel queries use `useIntelDraft` which returns the same type — so once the TS type is updated, it will work directly.

**Step 2: Fix standard draft style_match_score display**

At line 170, the standard draft factors list shows `Style match: ${draft.style_match_score}%` which displays the raw decimal. Fix:

```typescript
...(draft.style_match_score ? [`Style match: ${Math.round(draft.style_match_score * 100)}%`] : []),
```

**Step 3: Verify TypeScript compiles**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit 2>&1 | head -20`

**Step 4: Commit**

```bash
git add frontend/src/components/shell/intel-modules/WhyIWroteThisModule.tsx
git commit -m "feat: display aria_reasoning narrative in WhyIWroteThis module"
```

---

## Task 9: Verify full build

**Files:** None (verification only)

**Step 1: Backend syntax check**

Run: `cd /Users/dhruv/aria/backend && python3 -c "
import ast
for f in ['src/intelligence/reasoning_engine.py', 'src/intelligence/action_executor.py', 'src/intelligence/action_router.py', 'src/api/routes/drafts.py', 'src/models/email_draft.py']:
    ast.parse(open(f).read())
    print(f'OK: {f}')
"`

**Step 2: Frontend TypeScript check**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit 2>&1 | tail -5`

**Step 3: Frontend build check**

Run: `cd /Users/dhruv/aria/frontend && npm run build 2>&1 | tail -10`

---

## Summary of What's Actually Being Changed

| Bug/Feature | Status Before | Action Taken |
|---|---|---|
| BUG 1: Tone buttons | Already working (handler + cache sync + overlay exist) | No change needed |
| BUG 2: Style match 0.85% | Already fixed in all 3 locations (Math.round * 100) | Fix in WhyIWroteThis standard draft factors (line 170) |
| BUG 3: Edit body | Already has textarea + save includes body | No change needed |
| BUG 4: Ask ARIA | ChatInputModule not rendered in draft route | No change needed |
| BUG 5/6: Refinements | Already wired with onClick + loading states | No change needed |
| Tone overwrites aria_notes | Broken — replaces original notes | Fixed to append instead |
| ARIA Reasoning Engine | Doesn't exist | New module created |
| aria_reasoning DB column | Doesn't exist | Migration added |
| WhyIWroteThis narrative | Hardcoded generic text | Shows LLM reasoning when available |
| Standard draft style_match | Shows raw decimal in factors | Fixed to show percentage |
