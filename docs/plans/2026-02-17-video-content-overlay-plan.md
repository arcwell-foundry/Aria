# Video Content Overlay Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Display visual tool results (lead cards, battle cards, pipeline charts, research results, email drafts) alongside the Tavus avatar during video calls, using a hybrid approach of transcript cards + floating toast indicators.

**Architecture:** Extend the existing `VideoToolExecutor` to return structured `rich_content` alongside spoken text. The webhook handler emits it via WebSocket `aria.message`. The frontend `RichContentRenderer` renders 5 new card types in the transcript, while `DialogueMode` overlays floating toast pills on the avatar pane.

**Tech Stack:** React 18, TypeScript, Tailwind CSS, Python/FastAPI, WebSocket (`ws_manager`)

**Design Document:** `docs/plans/2026-02-17-video-content-overlay-design.md`

---

### Task 1: Backend — ToolResult dataclass and executor refactor

**Files:**
- Modify: `backend/src/integrations/tavus_tool_executor.py`

**Step 1: Add ToolResult dataclass and update execute() return type**

At the top of the file (after imports, before the class), add:

```python
from dataclasses import dataclass, field


@dataclass
class ToolResult:
    """Result of a video tool execution.

    Attributes:
        spoken_text: Natural-language result for the avatar to speak.
        rich_content: Optional structured card data for frontend display.
    """
    spoken_text: str
    rich_content: dict[str, Any] | None = None
```

Update the `execute()` method signature from `-> str` to `-> ToolResult`. Update the three return paths in `execute()`:

1. Unknown tool name (line 78):
```python
return ToolResult(spoken_text=f"I don't have a tool called {tool_name}. Let me help you another way.")
```

2. Missing handler (line 81):
```python
return ToolResult(spoken_text="That capability isn't available right now.")
```

3. Success path (line 84-87): Each `_handle_*` method now returns `ToolResult`, so `result` is already a `ToolResult`:
```python
try:
    result = await handler(arguments)
    await self._log_activity(tool_name, arguments, success=True)
    return result
```

4. Exception path (line 88-100):
```python
except Exception:
    logger.exception(
        "Video tool execution failed",
        extra={
            "tool_name": tool_name,
            "user_id": self._user_id,
        },
    )
    await self._log_activity(tool_name, arguments, success=False)
    return ToolResult(
        spoken_text=(
            f"I ran into an issue executing {tool_name.replace('_', ' ')}. "
            "Let me try a different approach."
        )
    )
```

**Step 2: Update _handle_search_companies to return ToolResult with lead_card rich_content**

Change return type and build rich_content:

```python
async def _handle_search_companies(self, args: dict[str, Any]) -> ToolResult:
    from src.agents import HunterAgent

    agent = HunterAgent(llm_client=self.llm, user_id=self._user_id)
    results = await agent._call_tool(
        "search_companies",
        query=args["query"],
        limit=5,
    )

    if not results:
        return ToolResult(
            spoken_text=f"I searched for companies matching '{args['query']}' but didn't find any results. Want me to broaden the search?",
        )

    companies = results if isinstance(results, list) else results.get("companies", [])
    if not companies:
        return ToolResult(
            spoken_text=f"No companies found matching '{args['query']}'. Would you like me to try different criteria?",
        )

    lines = [f"I found {len(companies)} companies matching your search."]
    for i, company in enumerate(companies[:5], 1):
        name = company.get("name") or company.get("company_name", "Unknown")
        description = company.get("description", "")
        snippet = description[:80] + "..." if len(description) > 80 else description
        lines.append(f"{i}. {name}" + (f" — {snippet}" if snippet else ""))

    lines.append("Would you like me to dig deeper into any of these, or add them to your pipeline?")

    # Build lead_card rich content from first result
    top = companies[0]
    rich_content = {
        "type": "lead_card",
        "data": {
            "company_name": top.get("name") or top.get("company_name", "Unknown"),
            "contacts": [
                {"name": c.get("name", ""), "title": c.get("title", "")}
                for c in (top.get("contacts") or [])[:3]
            ],
            "fit_score": top.get("fit_score"),
            "signals": [
                s.get("headline", str(s)) if isinstance(s, dict) else str(s)
                for s in (top.get("signals") or top.get("recent_signals") or [])[:3]
            ],
            "total_results": len(companies),
        },
    }

    return ToolResult(spoken_text=" ".join(lines), rich_content=rich_content)
```

**Step 3: Update _handle_search_leads similarly**

```python
async def _handle_search_leads(self, args: dict[str, Any]) -> ToolResult:
    from src.agents import HunterAgent

    agent = HunterAgent(llm_client=self.llm, user_id=self._user_id)
    results = await agent._call_tool(
        "search_companies",
        query=args["icp_criteria"],
        limit=5,
    )

    if not results:
        return ToolResult(
            spoken_text="I couldn't find leads matching that profile right now. Can you refine the criteria?",
        )

    leads = results if isinstance(results, list) else results.get("companies", [])
    if not leads:
        return ToolResult(
            spoken_text="No leads matched your ICP criteria. Would you like to adjust the search?",
        )

    lines = [f"I found {len(leads)} potential leads matching your ideal customer profile."]
    for i, lead in enumerate(leads[:5], 1):
        name = lead.get("name") or lead.get("company_name", "Unknown")
        fit = lead.get("fit_score")
        fit_str = f" with a {fit}% fit score" if fit else ""
        lines.append(f"{i}. {name}{fit_str}")

    lines.append("Want me to add any of these to your pipeline?")

    top = leads[0]
    rich_content = {
        "type": "lead_card",
        "data": {
            "company_name": top.get("name") or top.get("company_name", "Unknown"),
            "contacts": [
                {"name": c.get("name", ""), "title": c.get("title", "")}
                for c in (top.get("contacts") or [])[:3]
            ],
            "fit_score": top.get("fit_score"),
            "signals": [],
            "total_results": len(leads),
        },
    }

    return ToolResult(spoken_text=" ".join(lines), rich_content=rich_content)
```

**Step 4: Update _handle_get_lead_details**

```python
async def _handle_get_lead_details(self, args: dict[str, Any]) -> ToolResult:
    company_name = args["company_name"]

    result = (
        self.db.table("lead_memories")
        .select("company_name, health_score, lifecycle_stage, last_activity_at, status, website, metadata")
        .eq("user_id", self._user_id)
        .ilike("company_name", f"%{company_name}%")
        .limit(1)
        .execute()
    )

    if not result.data:
        return ToolResult(
            spoken_text=f"I don't have {company_name} in your pipeline. Would you like me to research them and add them?",
        )

    lead = result.data[0]
    name = lead.get("company_name", company_name)
    score = lead.get("health_score", 0)
    stage = lead.get("lifecycle_stage", "unknown")
    status = lead.get("status", "unknown")
    last_activity = lead.get("last_activity_at", "")

    parts = [f"Here's what I have on {name}."]
    parts.append(f"They're currently in the {stage} stage with a health score of {score} out of 100.")
    parts.append(f"Status is {status}.")
    if last_activity:
        parts.append(f"Last activity was on {last_activity[:10]}.")

    rich_content = {
        "type": "lead_card",
        "data": {
            "company_name": name,
            "contacts": [],
            "fit_score": score,
            "signals": [f"Stage: {stage}", f"Status: {status}"],
            "lifecycle_stage": stage,
        },
    }

    return ToolResult(spoken_text=" ".join(parts), rich_content=rich_content)
```

**Step 5: Update _handle_get_battle_card**

```python
async def _handle_get_battle_card(self, args: dict[str, Any]) -> ToolResult:
    competitor_name = args["competitor_name"]

    result = (
        self.db.table("battle_cards")
        .select("*")
        .eq("user_id", self._user_id)
        .ilike("competitor_name", f"%{competitor_name}%")
        .limit(1)
        .execute()
    )

    if not result.data:
        return ToolResult(
            spoken_text=f"I don't have a battle card for {competitor_name} yet. Would you like me to create one?",
        )

    card = result.data[0]
    name = card.get("competitor_name", competitor_name)
    parts = [f"Here's the battle card for {name}."]

    strengths = card.get("strengths")
    if strengths:
        s = strengths if isinstance(strengths, str) else ", ".join(strengths[:3])
        parts.append(f"Their key strengths are: {s}.")

    weaknesses = card.get("weaknesses")
    if weaknesses:
        w = weaknesses if isinstance(weaknesses, str) else ", ".join(weaknesses[:3])
        parts.append(f"Their weaknesses include: {w}.")

    differentiators = card.get("our_differentiators") or card.get("differentiators")
    if differentiators:
        d = differentiators if isinstance(differentiators, str) else ", ".join(differentiators[:3])
        parts.append(f"Our key differentiators: {d}.")

    win_strategy = card.get("win_strategy")
    if win_strategy:
        parts.append(f"Recommended win strategy: {win_strategy[:150]}.")

    # Build comparison rows
    rows = []
    if strengths:
        rows.append({"label": "Strengths", "competitor": strengths if isinstance(strengths, str) else ", ".join(strengths[:3]), "us": (differentiators if isinstance(differentiators, str) else ", ".join(differentiators[:3])) if differentiators else ""})
    if weaknesses:
        rows.append({"label": "Weaknesses", "competitor": weaknesses if isinstance(weaknesses, str) else ", ".join(weaknesses[:3]), "us": ""})
    if win_strategy:
        rows.append({"label": "Win Strategy", "competitor": "", "us": win_strategy[:150]})

    rich_content = {
        "type": "battle_card",
        "data": {
            "competitor_name": name,
            "our_company": "Your Team",
            "rows": rows,
        },
    }

    return ToolResult(spoken_text=" ".join(parts), rich_content=rich_content)
```

**Step 6: Update _handle_search_pubmed**

```python
async def _handle_search_pubmed(self, args: dict[str, Any]) -> ToolResult:
    from src.agents import AnalystAgent

    agent = AnalystAgent(llm_client=self.llm, user_id=self._user_id)
    max_results = min(args.get("max_results", 5), 10)

    results = await agent._call_tool(
        "pubmed_search",
        query=args["query"],
        max_results=max_results,
    )

    count = results.get("count", 0) if isinstance(results, dict) else 0
    pmids = results.get("pmids", []) if isinstance(results, dict) else []

    if count == 0:
        return ToolResult(
            spoken_text=f"I didn't find any PubMed articles for '{args['query']}'. Try broadening your search terms.",
        )

    # Fetch article details for the PMIDs
    try:
        details = await agent._call_tool(
            "pubmed_fetch_details",
            pmids=pmids[:5],
        )
        articles = details.get("articles", []) if isinstance(details, dict) else []
    except Exception:
        articles = []

    parts = [f"I found {count} articles on PubMed for '{args['query']}'."]

    if articles:
        parts.append("Here are the top results:")
        for i, article in enumerate(articles[:3], 1):
            title = article.get("title", "Untitled")
            year = article.get("year", "")
            journal = article.get("journal", "")
            parts.append(f"{i}. {title[:100]}" + (f", published in {journal} {year}" if journal else ""))
    else:
        parts.append(f"I found {len(pmids)} article IDs but couldn't fetch the details right now.")

    # Build research results card
    card_results = []
    source_articles = articles if articles else []
    for article in source_articles[:3]:
        pmid = article.get("pmid", "")
        card_results.append({
            "title": article.get("title", "Untitled"),
            "authors": article.get("authors", ""),
            "date": article.get("year", ""),
            "excerpt": article.get("abstract", "")[:200] if article.get("abstract") else "",
            "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
            "source": "PubMed",
        })

    rich_content = {
        "type": "research_results",
        "data": {
            "query": args["query"],
            "total_count": count,
            "results": card_results,
            "source": "pubmed",
        },
    } if card_results else None

    return ToolResult(spoken_text=" ".join(parts), rich_content=rich_content)
```

**Step 7: Update _handle_search_clinical_trials**

```python
async def _handle_search_clinical_trials(self, args: dict[str, Any]) -> ToolResult:
    from src.agents import AnalystAgent

    agent = AnalystAgent(llm_client=self.llm, user_id=self._user_id)

    query_parts = []
    if args.get("condition"):
        query_parts.append(args["condition"])
    if args.get("intervention"):
        query_parts.append(args["intervention"])
    if args.get("sponsor"):
        query_parts.append(args["sponsor"])
    query = " ".join(query_parts) if query_parts else "clinical trial"

    results = await agent._call_tool(
        "clinical_trials_search",
        query=query,
        max_results=5,
    )

    total = results.get("total_count", 0) if isinstance(results, dict) else 0
    studies = results.get("studies", []) if isinstance(results, dict) else []

    if total == 0:
        return ToolResult(
            spoken_text=f"No clinical trials found for {query}. Want me to try different search terms?",
        )

    parts = [f"I found {total} clinical trials related to {query}."]
    for i, study in enumerate(studies[:3], 1):
        title = study.get("title", study.get("brief_title", "Untitled"))
        phase = study.get("phase", "")
        status = study.get("status", study.get("overall_status", ""))
        sponsor = study.get("sponsor", study.get("lead_sponsor", ""))
        desc = title[:80]
        if phase:
            desc += f", Phase {phase}"
        if status:
            desc += f", {status}"
        if sponsor:
            desc += f", sponsored by {sponsor}"
        parts.append(f"{i}. {desc}")

    card_results = []
    for study in studies[:3]:
        nct_id = study.get("nct_id", "")
        card_results.append({
            "title": study.get("title", study.get("brief_title", "Untitled")),
            "authors": study.get("sponsor", study.get("lead_sponsor", "")),
            "date": study.get("start_date", ""),
            "excerpt": f"Phase {study.get('phase', 'N/A')} — {study.get('status', study.get('overall_status', 'Unknown'))}",
            "url": f"https://clinicaltrials.gov/study/{nct_id}" if nct_id else "",
            "source": "ClinicalTrials.gov",
        })

    rich_content = {
        "type": "research_results",
        "data": {
            "query": query,
            "total_count": total,
            "results": card_results,
            "source": "clinicaltrials",
        },
    } if card_results else None

    return ToolResult(spoken_text=" ".join(parts), rich_content=rich_content)
```

**Step 8: Update _handle_get_pipeline_summary**

```python
async def _handle_get_pipeline_summary(self, _args: dict[str, Any]) -> ToolResult:
    result = (
        self.db.table("lead_memories")
        .select("lifecycle_stage, health_score, status")
        .eq("user_id", self._user_id)
        .eq("status", "active")
        .execute()
    )

    if not result.data:
        return ToolResult(
            spoken_text="Your pipeline is empty right now. Would you like me to find some leads to get started?",
        )

    leads = result.data
    total = len(leads)

    stages: dict[str, int] = {}
    health_sum = 0
    for lead in leads:
        stage = lead.get("lifecycle_stage", "unknown")
        stages[stage] = stages.get(stage, 0) + 1
        health_sum += lead.get("health_score", 0)

    avg_health = round(health_sum / total) if total > 0 else 0

    parts = [f"Here's your pipeline summary. You have {total} active leads."]

    stage_order = ["prospect", "qualified", "proposal", "negotiation", "won"]
    for stage in stage_order:
        count = stages.get(stage, 0)
        if count > 0:
            parts.append(f"{count} in {stage}.")

    for stage, count in stages.items():
        if stage not in stage_order and count > 0:
            parts.append(f"{count} in {stage}.")

    parts.append(f"Average health score is {avg_health} out of 100.")

    hot = sum(1 for lead in leads if lead.get("health_score", 0) >= 70)
    if hot > 0:
        parts.append(f"{hot} leads are hot with a health score above 70.")

    # Build pipeline chart data
    chart_stages = []
    for stage in stage_order:
        count = stages.get(stage, 0)
        chart_stages.append({"stage": stage, "count": count})

    rich_content = {
        "type": "pipeline_chart",
        "data": {
            "stages": chart_stages,
            "total": total,
            "avg_health": avg_health,
        },
    }

    return ToolResult(spoken_text=" ".join(parts), rich_content=rich_content)
```

**Step 9: Update _handle_draft_email**

```python
async def _handle_draft_email(self, args: dict[str, Any]) -> ToolResult:
    from src.agents import ScribeAgent

    agent = ScribeAgent(llm_client=self.llm, user_id=self._user_id)

    recipient = {"name": args["to"]}
    if "@" in args["to"]:
        recipient = {"email": args["to"]}

    tone = args.get("tone", "formal")

    result = await agent._call_tool(
        "draft_email",
        recipient=recipient,
        context=args["subject_context"],
        goal=args["subject_context"],
        tone=tone,
    )

    if not result:
        return ToolResult(
            spoken_text="I wasn't able to draft that email. Can you give me more context?",
        )

    subject = result.get("subject", "")
    body = result.get("body", "")
    word_count = result.get("word_count", 0)
    draft_id = result.get("draft_id", "")

    parts = [f"I've drafted an email to {args['to']}."]
    if subject:
        parts.append(f"Subject line: {subject}.")
    if word_count:
        parts.append(f"It's {word_count} words.")
    parts.append("The draft is saved and ready for your review. Would you like me to read it, adjust the tone, or send it?")

    rich_content = {
        "type": "email_draft",
        "data": {
            "to": args["to"],
            "subject": subject,
            "body": body,
            "draft_id": draft_id,
            "tone": tone,
        },
    }

    return ToolResult(spoken_text=" ".join(parts), rich_content=rich_content)
```

**Step 10: Update remaining handlers to return ToolResult (spoken-only)**

These 4 handlers return `ToolResult` with `rich_content=None` (no visual card). For each, change the return type annotation to `-> ToolResult` and wrap every `return "..."` with `return ToolResult(spoken_text="...")`:

- `_handle_get_meeting_brief`
- `_handle_schedule_meeting`
- `_handle_get_market_signals`
- `_handle_add_lead_to_pipeline`

The pattern is mechanical: find each `return "..."` or `return " ".join(parts)` and replace with `return ToolResult(spoken_text=...)`.

**Step 11: Run backend linting**

Run: `cd /Users/dhruv/aria/backend && ruff check src/integrations/tavus_tool_executor.py`
Expected: No new errors (existing errors may remain)

**Step 12: Commit**

```bash
git add backend/src/integrations/tavus_tool_executor.py
git commit -m "feat(backend): return ToolResult with rich_content from VideoToolExecutor"
```

---

### Task 2: Backend — Webhook handler WebSocket emission

**Files:**
- Modify: `backend/src/api/routes/webhooks.py`

**Step 1: Update _execute_tool_with_timeout to return ToolResult**

The function currently returns `str`. Update it to return the `ToolResult` object instead. At the top of the function, update the import:

```python
async def _execute_tool_with_timeout(
    tool_name: str,
    arguments: dict[str, Any],
    user_id: str,
) -> "ToolResult":
    """Execute a video tool with timeout and retry."""
    from src.integrations.tavus_tool_executor import ToolResult, VideoToolExecutor

    executor = VideoToolExecutor(user_id=user_id)

    for attempt in range(2):
        try:
            result = await asyncio.wait_for(
                executor.execute(tool_name=tool_name, arguments=arguments),
                timeout=TOOL_EXECUTION_TIMEOUT,
            )
            return result
        except TimeoutError:
            if attempt == 0:
                logger.warning(
                    "Tool execution timed out, retrying",
                    extra={
                        "tool_name": tool_name,
                        "user_id": user_id,
                        "attempt": attempt + 1,
                    },
                )
                continue
            logger.warning(
                "Tool execution timed out after retry",
                extra={"tool_name": tool_name, "user_id": user_id},
            )
            return ToolResult(
                spoken_text=(
                    f"I'm having trouble completing the {tool_name.replace('_', ' ')} "
                    "request right now. Let me try a different approach or come back "
                    "to this in a moment."
                )
            )

    return ToolResult(spoken_text="I wasn't able to complete that request.")
```

**Step 2: Update handle_tool_call to emit WebSocket event**

In `handle_tool_call`, the `result` variable is now a `ToolResult`. Update the code after the lock block:

```python
async def handle_tool_call(
    conversation_id: str,
    payload: dict[str, Any],
    db: Any,
) -> dict[str, Any] | None:
    # ... (existing code up to the lock block) ...

    lock = _conversation_locks[conversation_id]

    start_time = time.monotonic()
    async with lock:
        tool_result = await _execute_tool_with_timeout(tool_name, arguments, user_id)
    duration_ms = int((time.monotonic() - start_time) * 1000)

    spoken_text = tool_result.spoken_text
    success = not spoken_text.startswith("I ran into an issue") and not spoken_text.startswith(
        "I'm having trouble"
    )

    result_summary = spoken_text[:200] + "..." if len(spoken_text) > 200 else spoken_text

    # Log to aria_activity
    try:
        db.table("aria_activity").insert({
            "user_id": user_id,
            "activity_type": "video_tool_call",
            "description": f"Tool '{tool_name}' executed during video session",
            "metadata": {
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "arguments": arguments,
                "result_summary": result_summary,
                "duration_ms": duration_ms,
                "conversation_id": conversation_id,
                "success": success,
            },
        }).execute()
    except Exception as e:
        logger.warning(
            "Failed to log tool call activity",
            extra={"conversation_id": conversation_id, "error": str(e)},
        )

    # Emit rich_content to frontend via WebSocket
    if tool_result.rich_content is not None:
        try:
            from src.core.ws import ws_manager

            await ws_manager.send_aria_message(
                user_id=user_id,
                message="",
                rich_content=[tool_result.rich_content],
            )
        except Exception as e:
            logger.warning(
                "Failed to send rich content via WebSocket",
                extra={"conversation_id": conversation_id, "error": str(e)},
            )

    logger.info(
        "Video tool call executed",
        extra={
            "conversation_id": conversation_id,
            "tool_name": tool_name,
            "duration_ms": duration_ms,
            "success": success,
        },
    )

    return {
        "tool_call_id": tool_call_id,
        "tool_name": tool_name,
        "result": spoken_text,
    }
```

**Step 3: Run backend linting**

Run: `cd /Users/dhruv/aria/backend && ruff check src/api/routes/webhooks.py`
Expected: No new errors

**Step 4: Commit**

```bash
git add backend/src/api/routes/webhooks.py
git commit -m "feat(backend): emit rich_content via WebSocket after video tool execution"
```

---

### Task 3: Frontend — LeadCard component

**Files:**
- Create: `frontend/src/components/rich/LeadCard.tsx`

**Step 1: Create the LeadCard component**

```typescript
import { useState } from 'react';
import { Building2, User, TrendingUp, Plus, Loader2 } from 'lucide-react';

export interface LeadCardData {
  company_name: string;
  contacts?: { name: string; title: string }[];
  fit_score?: number | null;
  signals?: string[];
  total_results?: number;
  lifecycle_stage?: string;
}

export function LeadCard({ data }: { data: LeadCardData }) {
  const [adding, setAdding] = useState(false);
  const [added, setAdded] = useState(false);

  const handleAddToPipeline = async () => {
    setAdding(true);
    try {
      const { apiClient } = await import('@/api/client');
      await apiClient.post('/leads/pipeline', {
        company_name: data.company_name,
      });
      setAdded(true);
    } catch {
      setAdding(false);
    }
  };

  return (
    <div
      className="rounded-lg border border-[var(--border)] overflow-hidden"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id={`lead-card-${data.company_name.toLowerCase().replace(/\s+/g, '-')}`}
    >
      {/* Header */}
      <div
        className="flex items-center gap-2 px-4 py-2.5"
        style={{
          borderBottom: '1px solid var(--border)',
          backgroundColor: 'rgba(46,102,255,0.05)',
        }}
      >
        <Building2 className="w-3.5 h-3.5" style={{ color: 'var(--accent)' }} />
        <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
          {data.company_name}
        </span>
        {data.lifecycle_stage && (
          <span className="ml-auto text-[10px] font-mono uppercase tracking-wider" style={{ color: 'var(--text-secondary)' }}>
            {data.lifecycle_stage}
          </span>
        )}
      </div>

      <div className="px-4 py-3 space-y-2.5">
        {/* Fit Score */}
        {data.fit_score != null && (
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: 'var(--text-secondary)' }}>
                Fit Score
              </span>
              <span className="text-xs font-mono" style={{ color: 'var(--accent)' }}>
                {data.fit_score}%
              </span>
            </div>
            <div className="h-1.5 rounded-full" style={{ backgroundColor: 'var(--bg-subtle)' }}>
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${Math.min(data.fit_score, 100)}%`,
                  backgroundColor: 'var(--accent)',
                }}
              />
            </div>
          </div>
        )}

        {/* Contacts */}
        {data.contacts && data.contacts.length > 0 && (
          <div className="space-y-1">
            {data.contacts.map((contact, i) => (
              <div key={i} className="flex items-center gap-2">
                <User className="w-3 h-3 shrink-0" style={{ color: 'var(--text-secondary)' }} />
                <span className="text-xs" style={{ color: 'var(--text-primary)' }}>
                  {contact.name}
                </span>
                {contact.title && (
                  <span className="text-[10px]" style={{ color: 'var(--text-secondary)' }}>
                    {contact.title}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Signals */}
        {data.signals && data.signals.length > 0 && (
          <div className="space-y-1">
            {data.signals.map((signal, i) => (
              <div key={i} className="flex items-start gap-2">
                <TrendingUp className="w-3 h-3 mt-0.5 shrink-0 text-emerald-400" />
                <span className="text-xs" style={{ color: 'var(--text-primary)' }}>
                  {signal}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Action */}
        {!added ? (
          <button
            type="button"
            disabled={adding}
            onClick={handleAddToPipeline}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded text-[10px] font-mono uppercase tracking-wider transition-colors"
            style={{
              color: 'var(--accent)',
              border: '1px solid rgba(46,102,255,0.3)',
            }}
          >
            {adding ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <Plus className="w-3 h-3" />
            )}
            Add to Pipeline
          </button>
        ) : (
          <span className="text-[10px] font-mono uppercase tracking-wider text-emerald-400">
            Added to pipeline
          </span>
        )}
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/rich/LeadCard.tsx
git commit -m "feat(frontend): add LeadCard rich content component"
```

---

### Task 4: Frontend — BattleCard component

**Files:**
- Create: `frontend/src/components/rich/BattleCard.tsx`

**Step 1: Create the BattleCard component**

```typescript
import { Swords } from 'lucide-react';

export interface BattleCardData {
  competitor_name: string;
  our_company?: string;
  rows: { label: string; competitor: string; us: string }[];
}

export function BattleCard({ data }: { data: BattleCardData }) {
  return (
    <div
      className="rounded-lg border border-[var(--border)] overflow-hidden"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id={`battle-card-${data.competitor_name.toLowerCase().replace(/\s+/g, '-')}`}
    >
      {/* Header */}
      <div
        className="flex items-center gap-2 px-4 py-2.5"
        style={{
          borderBottom: '1px solid var(--border)',
          backgroundColor: 'rgba(245,158,11,0.05)',
        }}
      >
        <Swords className="w-3.5 h-3.5 text-amber-400" />
        <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
          {data.our_company || 'Your Team'} vs {data.competitor_name}
        </span>
      </div>

      {/* Table */}
      {data.rows.length > 0 && (
        <table className="w-full text-xs">
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              <th className="px-4 py-2 text-left font-mono text-[10px] uppercase tracking-wider" style={{ color: 'var(--text-secondary)', width: '25%' }} />
              <th className="px-4 py-2 text-left font-mono text-[10px] uppercase tracking-wider" style={{ color: 'var(--accent)', width: '37.5%' }}>
                {data.our_company || 'Us'}
              </th>
              <th className="px-4 py-2 text-left font-mono text-[10px] uppercase tracking-wider" style={{ color: 'var(--text-secondary)', width: '37.5%' }}>
                {data.competitor_name}
              </th>
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row, i) => (
              <tr
                key={i}
                style={{ borderBottom: i < data.rows.length - 1 ? '1px solid var(--border)' : undefined }}
              >
                <td className="px-4 py-2 font-mono text-[10px] uppercase tracking-wider" style={{ color: 'var(--text-secondary)' }}>
                  {row.label}
                </td>
                <td className="px-4 py-2 font-mono" style={{ color: 'var(--text-primary)' }}>
                  {row.us}
                </td>
                <td className="px-4 py-2 font-mono" style={{ color: 'var(--text-primary)' }}>
                  {row.competitor}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/rich/BattleCard.tsx
git commit -m "feat(frontend): add BattleCard rich content component"
```

---

### Task 5: Frontend — PipelineChart component

**Files:**
- Create: `frontend/src/components/rich/PipelineChart.tsx`

**Step 1: Create the PipelineChart component**

```typescript
import { BarChart3 } from 'lucide-react';

export interface PipelineChartData {
  stages: { stage: string; count: number }[];
  total: number;
  avg_health?: number;
}

const STAGE_LABELS: Record<string, string> = {
  prospect: 'Prospect',
  qualified: 'Qualified',
  proposal: 'Proposal',
  negotiation: 'Negotiation',
  won: 'Won',
};

export function PipelineChart({ data }: { data: PipelineChartData }) {
  const maxCount = Math.max(...data.stages.map((s) => s.count), 1);

  return (
    <div
      className="rounded-lg border border-[var(--border)] overflow-hidden"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id="pipeline-chart"
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-2.5"
        style={{
          borderBottom: '1px solid var(--border)',
          backgroundColor: 'rgba(46,102,255,0.05)',
        }}
      >
        <div className="flex items-center gap-2">
          <BarChart3 className="w-3.5 h-3.5" style={{ color: 'var(--accent)' }} />
          <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
            Pipeline Summary
          </span>
        </div>
        <span className="text-[10px] font-mono" style={{ color: 'var(--text-secondary)' }}>
          {data.total} leads
        </span>
      </div>

      {/* Bars */}
      <div className="px-4 py-3 space-y-2">
        {data.stages.map((stage) => (
          <div key={stage.stage} className="flex items-center gap-3">
            <span
              className="text-[10px] font-mono uppercase tracking-wider w-20 shrink-0 text-right"
              style={{ color: 'var(--text-secondary)' }}
            >
              {STAGE_LABELS[stage.stage] || stage.stage}
            </span>
            <div className="flex-1 h-5 rounded" style={{ backgroundColor: 'var(--bg-subtle)' }}>
              <div
                className="h-full rounded flex items-center justify-end pr-2 transition-all"
                style={{
                  width: `${Math.max((stage.count / maxCount) * 100, stage.count > 0 ? 15 : 0)}%`,
                  backgroundColor: 'var(--accent)',
                  opacity: stage.count > 0 ? 1 : 0.2,
                }}
              >
                {stage.count > 0 && (
                  <span className="text-[10px] font-mono text-white">
                    {stage.count}
                  </span>
                )}
              </div>
            </div>
          </div>
        ))}

        {data.avg_health != null && (
          <div className="pt-2 mt-1" style={{ borderTop: '1px solid var(--border)' }}>
            <span className="text-[10px] font-mono" style={{ color: 'var(--text-secondary)' }}>
              Avg Health: <span style={{ color: 'var(--accent)' }}>{data.avg_health}/100</span>
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/rich/PipelineChart.tsx
git commit -m "feat(frontend): add PipelineChart rich content component"
```

---

### Task 6: Frontend — ResearchResultsCard component

**Files:**
- Create: `frontend/src/components/rich/ResearchResultsCard.tsx`

**Step 1: Create the ResearchResultsCard component**

```typescript
import { BookOpen, ExternalLink, Bookmark, Loader2 } from 'lucide-react';
import { useState } from 'react';

export interface ResearchResult {
  title: string;
  authors?: string;
  date?: string;
  excerpt?: string;
  url?: string;
  source?: string;
}

export interface ResearchResultsData {
  query: string;
  total_count: number;
  results: ResearchResult[];
  source?: string;
}

export function ResearchResultsCard({ data }: { data: ResearchResultsData }) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    try {
      const { apiClient } = await import('@/api/client');
      await apiClient.post('/intelligence/save', {
        type: 'research',
        query: data.query,
        results: data.results,
        source: data.source,
      });
      setSaved(true);
    } catch {
      setSaving(false);
    }
  };

  const remaining = data.total_count - data.results.length;

  return (
    <div
      className="rounded-lg border border-[var(--border)] overflow-hidden"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id="research-results-card"
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-2.5"
        style={{
          borderBottom: '1px solid var(--border)',
          backgroundColor: 'rgba(139,92,246,0.05)',
        }}
      >
        <div className="flex items-center gap-2">
          <BookOpen className="w-3.5 h-3.5 text-violet-400" />
          <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
            Research Results
          </span>
        </div>
        <span className="text-[10px] font-mono" style={{ color: 'var(--text-secondary)' }}>
          {data.total_count} found
        </span>
      </div>

      {/* Results */}
      <div className="divide-y" style={{ borderColor: 'var(--border)' }}>
        {data.results.map((result, i) => (
          <div key={i} className="px-4 py-2.5">
            <div className="flex items-start justify-between gap-2">
              <p className="text-xs font-medium leading-snug" style={{ color: 'var(--text-primary)' }}>
                {result.title}
              </p>
              {result.url && (
                <a
                  href={result.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="shrink-0 mt-0.5"
                >
                  <ExternalLink className="w-3 h-3" style={{ color: 'var(--text-secondary)' }} />
                </a>
              )}
            </div>
            <div className="flex items-center gap-2 mt-1 text-[10px] font-mono" style={{ color: 'var(--text-secondary)' }}>
              {result.authors && <span>{result.authors}</span>}
              {result.date && <span>{result.date}</span>}
              {result.source && (
                <span className="px-1 py-0.5 rounded bg-violet-500/10 text-violet-400">
                  {result.source}
                </span>
              )}
            </div>
            {result.excerpt && (
              <p className="text-[11px] mt-1 leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                {result.excerpt}
              </p>
            )}
          </div>
        ))}
      </div>

      {/* Footer */}
      <div
        className="flex items-center justify-between px-4 py-2"
        style={{ borderTop: '1px solid var(--border)' }}
      >
        {remaining > 0 && (
          <span className="text-[10px] font-mono" style={{ color: 'var(--text-secondary)' }}>
            +{remaining} more
          </span>
        )}
        <div className="ml-auto">
          {!saved ? (
            <button
              type="button"
              disabled={saving}
              onClick={handleSave}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded text-[10px] font-mono uppercase tracking-wider transition-colors"
              style={{
                color: 'var(--accent)',
                border: '1px solid rgba(46,102,255,0.3)',
              }}
            >
              {saving ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <Bookmark className="w-3 h-3" />
              )}
              Save to Intelligence
            </button>
          ) : (
            <span className="text-[10px] font-mono uppercase tracking-wider text-emerald-400">
              Saved
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/rich/ResearchResultsCard.tsx
git commit -m "feat(frontend): add ResearchResultsCard rich content component"
```

---

### Task 7: Frontend — EmailDraftCard component

**Files:**
- Create: `frontend/src/components/rich/EmailDraftCard.tsx`

**Step 1: Create the EmailDraftCard component**

```typescript
import { useState } from 'react';
import { Mail, Send, Pencil, ChevronDown, ChevronUp, Loader2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export interface EmailDraftData {
  to: string;
  subject: string;
  body: string;
  draft_id?: string;
  tone?: string;
}

export function EmailDraftCard({ data }: { data: EmailDraftData }) {
  const [expanded, setExpanded] = useState(false);
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const navigate = useNavigate();

  const previewLines = data.body.split('\n').slice(0, 4).join('\n');
  const hasMore = data.body.split('\n').length > 4;

  const handleSend = async () => {
    setSending(true);
    try {
      const { apiClient } = await import('@/api/client');
      await apiClient.post('/communications/send', {
        draft_id: data.draft_id,
        to: data.to,
        subject: data.subject,
        body: data.body,
      });
      setSent(true);
    } catch {
      setSending(false);
    }
  };

  const handleEdit = () => {
    navigate(`/communications?draft=${data.draft_id || ''}`);
  };

  return (
    <div
      className="rounded-lg border border-[var(--border)] overflow-hidden"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id="email-draft-card"
    >
      {/* Header */}
      <div
        className="flex items-center gap-2 px-4 py-2.5"
        style={{
          borderBottom: '1px solid var(--border)',
          backgroundColor: 'rgba(46,102,255,0.05)',
        }}
      >
        <Mail className="w-3.5 h-3.5" style={{ color: 'var(--accent)' }} />
        <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
          Email Draft
        </span>
        {data.tone && (
          <span className="ml-auto text-[10px] font-mono uppercase tracking-wider" style={{ color: 'var(--text-secondary)' }}>
            {data.tone}
          </span>
        )}
      </div>

      {/* Fields */}
      <div className="px-4 py-3 space-y-2">
        <div className="flex gap-2 text-xs">
          <span className="font-mono text-[10px] uppercase tracking-wider shrink-0 pt-0.5" style={{ color: 'var(--text-secondary)' }}>
            To
          </span>
          <span style={{ color: 'var(--text-primary)' }}>{data.to}</span>
        </div>
        <div className="flex gap-2 text-xs">
          <span className="font-mono text-[10px] uppercase tracking-wider shrink-0 pt-0.5" style={{ color: 'var(--text-secondary)' }}>
            Re
          </span>
          <span className="font-medium" style={{ color: 'var(--text-primary)' }}>{data.subject}</span>
        </div>

        {/* Body preview */}
        <div
          className="mt-2 pt-2 text-xs whitespace-pre-wrap leading-relaxed"
          style={{
            borderTop: '1px solid var(--border)',
            color: 'var(--text-primary)',
          }}
        >
          {expanded ? data.body : previewLines}
        </div>

        {hasMore && (
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider"
            style={{ color: 'var(--accent)' }}
          >
            {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {expanded ? 'Collapse' : 'Show full email'}
          </button>
        )}
      </div>

      {/* Actions */}
      <div
        className="flex items-center gap-2 px-4 py-2.5"
        style={{ borderTop: '1px solid var(--border)' }}
      >
        {!sent ? (
          <>
            <button
              type="button"
              disabled={sending}
              onClick={handleSend}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
              style={{ backgroundColor: 'var(--accent)' }}
            >
              {sending ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <Send className="w-3 h-3" />
              )}
              Send
            </button>
            <button
              type="button"
              onClick={handleEdit}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium border transition-opacity hover:opacity-90"
              style={{
                borderColor: 'var(--border)',
                color: 'var(--text-secondary)',
                backgroundColor: 'transparent',
              }}
            >
              <Pencil className="w-3 h-3" />
              Edit
            </button>
          </>
        ) : (
          <span className="text-xs text-emerald-400 flex items-center gap-1.5">
            <Send className="w-3 h-3" />
            Sent
          </span>
        )}
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/rich/EmailDraftCard.tsx
git commit -m "feat(frontend): add EmailDraftCard rich content component"
```

---

### Task 8: Frontend — Wire cards into RichContentRenderer and exports

**Files:**
- Modify: `frontend/src/components/rich/RichContentRenderer.tsx`
- Modify: `frontend/src/components/rich/index.ts`

**Step 1: Add imports and cases to RichContentRenderer**

Add these imports at the top of `RichContentRenderer.tsx` (after existing imports):

```typescript
import { LeadCard, type LeadCardData } from './LeadCard';
import { BattleCard, type BattleCardData } from './BattleCard';
import { PipelineChart, type PipelineChartData } from './PipelineChart';
import { ResearchResultsCard, type ResearchResultsData } from './ResearchResultsCard';
import { EmailDraftCard, type EmailDraftData } from './EmailDraftCard';
```

Add these cases to the `switch` in `RichContentItem` (before the `default` case):

```typescript
case 'lead_card':
  return <LeadCard data={item.data as unknown as LeadCardData} />;
case 'battle_card':
  return <BattleCard data={item.data as unknown as BattleCardData} />;
case 'pipeline_chart':
  return <PipelineChart data={item.data as unknown as PipelineChartData} />;
case 'research_results':
  return <ResearchResultsCard data={item.data as unknown as ResearchResultsData} />;
case 'email_draft':
  return <EmailDraftCard data={item.data as unknown as EmailDraftData} />;
```

**Step 2: Update index.ts exports**

Add to `frontend/src/components/rich/index.ts`:

```typescript
export { LeadCard, type LeadCardData } from './LeadCard';
export { BattleCard, type BattleCardData } from './BattleCard';
export { PipelineChart, type PipelineChartData } from './PipelineChart';
export { ResearchResultsCard, type ResearchResultsData } from './ResearchResultsCard';
export { EmailDraftCard, type EmailDraftData } from './EmailDraftCard';
```

**Step 3: Run typecheck**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit`
Expected: No new errors from the new card files

**Step 4: Commit**

```bash
git add frontend/src/components/rich/RichContentRenderer.tsx frontend/src/components/rich/index.ts
git commit -m "feat(frontend): wire 5 new card types into RichContentRenderer"
```

---

### Task 9: Frontend — VideoContentToast and VideoToastStack components

**Files:**
- Create: `frontend/src/components/video/VideoContentToast.tsx`
- Create: `frontend/src/components/video/VideoToastStack.tsx`
- Modify: `frontend/src/components/video/index.ts`

**Step 1: Create VideoContentToast**

```typescript
import { useEffect, useRef } from 'react';
import { X, Building2, Swords, BarChart3, BookOpen, Mail } from 'lucide-react';

const CONTENT_ICONS: Record<string, typeof Building2> = {
  lead_card: Building2,
  battle_card: Swords,
  pipeline_chart: BarChart3,
  research_results: BookOpen,
  email_draft: Mail,
};

export interface ToastItem {
  id: string;
  contentType: string;
  title: string;
}

interface VideoContentToastProps {
  toast: ToastItem;
  onDismiss: (id: string) => void;
  onClick: (id: string) => void;
}

export function VideoContentToast({ toast, onDismiss, onClick }: VideoContentToastProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Trigger slide-in animation
    requestAnimationFrame(() => {
      if (ref.current) ref.current.style.transform = 'translateX(0)';
      if (ref.current) ref.current.style.opacity = '1';
    });
  }, []);

  const Icon = CONTENT_ICONS[toast.contentType] || Building2;

  return (
    <div
      ref={ref}
      className="flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer backdrop-blur-sm transition-all duration-200 ease-out"
      style={{
        backgroundColor: 'rgba(15,17,23,0.85)',
        border: '1px solid rgba(46,102,255,0.2)',
        transform: 'translateX(100%)',
        opacity: '0',
      }}
      onClick={() => onClick(toast.id)}
    >
      <Icon className="w-3.5 h-3.5 shrink-0" style={{ color: 'var(--accent)' }} />
      <span className="text-xs text-white/90 truncate max-w-[180px]">
        {toast.title}
      </span>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onDismiss(toast.id);
        }}
        className="shrink-0 p-0.5 rounded hover:bg-white/10 transition-colors"
      >
        <X className="w-3 h-3 text-white/50" />
      </button>
    </div>
  );
}
```

**Step 2: Create VideoToastStack**

```typescript
import { useEffect, useRef, useCallback } from 'react';
import { VideoContentToast, type ToastItem } from './VideoContentToast';

interface VideoToastStackProps {
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
  onToastClick: (id: string) => void;
}

const MAX_VISIBLE = 3;
const AUTO_DISMISS_MS = 8000;

export function VideoToastStack({ toasts, onDismiss, onToastClick }: VideoToastStackProps) {
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const scheduleAutoDismiss = useCallback(
    (id: string) => {
      if (timersRef.current.has(id)) return;
      const timer = setTimeout(() => {
        timersRef.current.delete(id);
        onDismiss(id);
      }, AUTO_DISMISS_MS);
      timersRef.current.set(id, timer);
    },
    [onDismiss],
  );

  // Schedule auto-dismiss for each toast
  useEffect(() => {
    for (const toast of toasts) {
      scheduleAutoDismiss(toast.id);
    }
  }, [toasts, scheduleAutoDismiss]);

  // Cleanup timers on unmount
  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      for (const timer of timers.values()) clearTimeout(timer);
      timers.clear();
    };
  }, []);

  const visible = toasts.slice(-MAX_VISIBLE);

  if (visible.length === 0) return null;

  return (
    <div className="absolute bottom-4 right-4 z-20 flex flex-col gap-2">
      {visible.map((toast) => (
        <VideoContentToast
          key={toast.id}
          toast={toast}
          onDismiss={onDismiss}
          onClick={onToastClick}
        />
      ))}
    </div>
  );
}
```

**Step 3: Update video index.ts**

Add to `frontend/src/components/video/index.ts`:

```typescript
export { VideoContentToast, type ToastItem } from "./VideoContentToast";
export { VideoToastStack } from "./VideoToastStack";
```

**Step 4: Commit**

```bash
git add frontend/src/components/video/VideoContentToast.tsx frontend/src/components/video/VideoToastStack.tsx frontend/src/components/video/index.ts
git commit -m "feat(frontend): add VideoContentToast and VideoToastStack components"
```

---

### Task 10: Frontend — Wire toasts into DialogueMode

**Files:**
- Modify: `frontend/src/components/avatar/DialogueMode.tsx`

**Step 1: Add toast state and rendering to DialogueMode**

Add imports at the top:

```typescript
import { VideoToastStack } from '@/components/video/VideoToastStack';
import type { ToastItem } from '@/components/video/VideoContentToast';
```

Add state inside the component (after existing state declarations):

```typescript
const [toasts, setToasts] = useState<ToastItem[]>([]);
```

Add a helper to derive toast title from rich content (inside the component, before the return):

```typescript
const toastTitleForContent = useCallback((type: string, data: Record<string, unknown>): string => {
  switch (type) {
    case 'lead_card':
      return `Lead: ${(data.company_name as string) || 'Company'}`;
    case 'battle_card':
      return `Battle Card: ${(data.competitor_name as string) || 'Competitor'}`;
    case 'pipeline_chart':
      return `Pipeline: ${(data.total as number) || 0} leads`;
    case 'research_results':
      return `Research: ${(data.query as string) || 'Results'}`;
    case 'email_draft':
      return `Draft: ${(data.subject as string) || 'Email'}`;
    default:
      return type.replace('_', ' ');
  }
}, []);
```

In the existing `handleAriaMessage` callback (inside the `useEffect` that wires up event listeners), after the message is added to the conversation store, add toast creation. Insert this code right before the `if (data.suggestions?.length)` check:

```typescript
// Create toast notifications for video content overlay
const richItems = data.rich_content || [];
const VIDEO_CONTENT_TYPES = ['lead_card', 'battle_card', 'pipeline_chart', 'research_results', 'email_draft'];
for (const item of richItems) {
  if (VIDEO_CONTENT_TYPES.includes(item.type)) {
    const toastId = `toast-${item.type}-${Date.now()}`;
    setToasts((prev) => {
      const next = [...prev, { id: toastId, contentType: item.type, title: toastTitleForContent(item.type, item.data) }];
      // Enforce max by trimming oldest
      return next.length > 3 ? next.slice(-3) : next;
    });
  }
}
```

Add toast handlers (alongside existing handlers like handlePlayPause):

```typescript
const handleToastDismiss = useCallback((id: string) => {
  setToasts((prev) => prev.filter((t) => t.id !== id));
}, []);

const handleToastClick = useCallback((id: string) => {
  // Scroll transcript panel to the latest rich content card
  const transcriptEl = document.querySelector('[data-aria-id="transcript-panel"]');
  if (transcriptEl) {
    transcriptEl.scrollTop = transcriptEl.scrollHeight;
  }
  setToasts((prev) => prev.filter((t) => t.id !== id));
}, []);
```

In the JSX return, add `VideoToastStack` inside the avatar container div (the `<div className="flex-1 flex flex-col items-center justify-center relative">`), after `<AvatarContainer />`:

```tsx
<VideoToastStack
  toasts={toasts}
  onDismiss={handleToastDismiss}
  onToastClick={handleToastClick}
/>
```

**Step 2: Add `toastTitleForContent` to the useEffect dependency array**

The `handleAriaMessage` function now references `toastTitleForContent`, so add it to the dependency array of the useEffect that creates the WebSocket listeners. Update the dependency array to include `toastTitleForContent`.

**Step 3: Run typecheck**

Run: `cd /Users/dhruv/aria/frontend && npx tsc --noEmit`
Expected: No new errors

**Step 4: Commit**

```bash
git add frontend/src/components/avatar/DialogueMode.tsx
git commit -m "feat(frontend): wire VideoToastStack into DialogueMode for video content overlay"
```

---

### Task 11: Build verification and final commit

**Step 1: Run frontend build**

Run: `cd /Users/dhruv/aria/frontend && npm run build`
Expected: Build succeeds

**Step 2: Run frontend lint**

Run: `cd /Users/dhruv/aria/frontend && npm run lint`
Expected: No new errors from added files

**Step 3: Run backend lint**

Run: `cd /Users/dhruv/aria/backend && ruff check src/integrations/tavus_tool_executor.py src/api/routes/webhooks.py`
Expected: No new errors

**Step 4: If any issues, fix and commit**

```bash
git add -A && git commit -m "fix: resolve lint/build issues from video content overlay"
```
