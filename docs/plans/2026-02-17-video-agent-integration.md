# Video Agent Integration — Fix All 5 Gaps

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Wire all 6 agents properly into the video tool executor with Digital Twin style, Strategist-generated battle cards, episodic memory persistence, OODA trigger from video, and rich content for Scout signals.

**Architecture:** The `VideoToolExecutor` already routes 12 tools to agents. We enhance 5 existing handlers and add 1 new tool. All changes are in 2 files (`tavus_tool_executor.py`, `tavus_tools.py`) plus tests. No new services, no schema changes.

**Tech Stack:** Python 3.11+, FastAPI, Supabase, existing agent classes, EpisodicMemory, DigitalTwin, OODALoop.

---

### Task 1: Scribe Digital Twin Integration (draft_email)

**Files:**
- Modify: `backend/src/integrations/tavus_tool_executor.py:598-648` (`_handle_draft_email`)
- Test: `backend/tests/integrations/test_tavus_tool_executor.py`

**Step 1: Write the failing test**

```python
# In backend/tests/integrations/test_tavus_tool_executor.py

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_draft_email_loads_digital_twin_style():
    """draft_email should load Digital Twin fingerprint and pass style to ScribeAgent."""
    from src.integrations.tavus_tool_executor import VideoToolExecutor

    executor = VideoToolExecutor(user_id="user-123")

    # Mock LLM
    executor._llm = MagicMock()

    # Mock DB for recipient profile lookup
    mock_db = MagicMock()
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.limit.return_value.execute.return_value = MagicMock(data=[])
    executor._db = mock_db

    # Mock DigitalTwin.get_fingerprint
    mock_fingerprint = MagicMock()
    mock_fingerprint.greeting_style = "Hi"
    mock_fingerprint.sign_off_style = "Best"
    mock_fingerprint.formality_score = 0.8

    with patch("src.integrations.tavus_tool_executor.DigitalTwin") as MockDT:
        mock_dt_instance = AsyncMock()
        mock_dt_instance.get_fingerprint.return_value = mock_fingerprint
        MockDT.return_value = mock_dt_instance

        with patch("src.integrations.tavus_tool_executor.ScribeAgent") as MockScribe:
            mock_agent = AsyncMock()
            mock_agent._call_tool.return_value = {
                "subject": "Follow up",
                "body": "Hi there...",
                "word_count": 42,
            }
            MockScribe.return_value = mock_agent

            result = await executor._handle_draft_email({
                "to": "jane@lonza.com",
                "subject_context": "follow up on bioreactor demo",
                "tone": "formal",
            })

            # Verify Digital Twin was queried
            mock_dt_instance.get_fingerprint.assert_called_once_with("user-123")

            # Verify style was passed to ScribeAgent._call_tool
            call_kwargs = mock_agent._call_tool.call_args
            assert "style" in call_kwargs.kwargs or (len(call_kwargs.args) > 4)
            # Check style has Digital Twin values
            style_arg = call_kwargs.kwargs.get("style", {})
            assert style_arg.get("preferred_greeting") == "Hi"
            assert style_arg.get("signature") == "Best"

            assert result.spoken_text  # Should have content
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/integrations/test_tavus_tool_executor.py::test_draft_email_loads_digital_twin_style -v`
Expected: FAIL — `DigitalTwin` not imported in tavus_tool_executor

**Step 3: Implement the change**

In `backend/src/integrations/tavus_tool_executor.py`, replace `_handle_draft_email` (lines 598-648):

```python
async def _handle_draft_email(self, args: dict[str, Any]) -> ToolResult:
    from src.agents import ScribeAgent
    from src.memory.digital_twin import DigitalTwin

    agent = ScribeAgent(llm_client=self.llm, user_id=self._user_id)

    recipient = {"name": args["to"]}
    if "@" in args["to"]:
        recipient = {"email": args["to"]}

    tone = args.get("tone", "formal")

    # Load Digital Twin writing style
    style: dict[str, Any] = {}
    try:
        dt = DigitalTwin()
        fingerprint = await dt.get_fingerprint(self._user_id)
        if fingerprint:
            style = {
                "preferred_greeting": fingerprint.greeting_style,
                "signature": fingerprint.sign_off_style,
                "formality": "formal" if fingerprint.formality_score > 0.6 else "casual",
            }
        # Check recipient-specific profile
        if "@" in args["to"]:
            rp = (
                self.db.table("recipient_writing_profiles")
                .select("greeting_style, signoff_style, formality_level, tone")
                .eq("user_id", self._user_id)
                .eq("recipient_email", args["to"])
                .limit(1)
                .execute()
            )
            if rp.data:
                profile = rp.data[0]
                if profile.get("greeting_style"):
                    style["preferred_greeting"] = profile["greeting_style"]
                if profile.get("signoff_style"):
                    style["signature"] = profile["signoff_style"]
                if profile.get("formality_level") is not None:
                    style["formality"] = (
                        "formal" if profile["formality_level"] > 0.6 else "casual"
                    )
                if profile.get("tone"):
                    tone = profile["tone"]
    except Exception:
        logger.debug("Failed to load digital twin style", exc_info=True)

    result = await agent._call_tool(
        "draft_email",
        recipient=recipient,
        context=args["subject_context"],
        goal=args["subject_context"],
        tone=tone,
        style=style,
    )

    if not result:
        return ToolResult(
            spoken_text="I wasn't able to draft that email. Can you give me more context?"
        )

    subject = result.get("subject", "")
    body = result.get("body", "")
    draft_id = result.get("draft_id", "")
    word_count = result.get("word_count", 0)

    parts = [f"I've drafted an email to {args['to']}."]
    if subject:
        parts.append(f"Subject line: {subject}.")
    if word_count:
        parts.append(f"It's {word_count} words.")
    parts.append(
        "The draft is saved and ready for your review. "
        "Would you like me to read it, adjust the tone, or send it?"
    )

    spoken_text = " ".join(parts)

    rich_content: dict[str, Any] = {
        "type": "email_draft",
        "data": {
            "to": args["to"],
            "subject": subject,
            "body": body,
            "draft_id": draft_id,
            "tone": tone,
        },
    }

    return ToolResult(spoken_text=spoken_text, rich_content=rich_content)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/integrations/test_tavus_tool_executor.py::test_draft_email_loads_digital_twin_style -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/integrations/tavus_tool_executor.py backend/tests/integrations/test_tavus_tool_executor.py
git commit -m "feat: load Digital Twin writing style in video draft_email tool"
```

---

### Task 2: Strategist Fallback for Battle Cards

**Files:**
- Modify: `backend/src/integrations/tavus_tool_executor.py:254-322` (`_handle_get_battle_card`)
- Test: `backend/tests/integrations/test_tavus_tool_executor.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_get_battle_card_generates_via_strategist_when_not_in_db():
    """When no battle card exists in DB, Strategist should generate one."""
    from src.integrations.tavus_tool_executor import VideoToolExecutor

    executor = VideoToolExecutor(user_id="user-123")
    executor._llm = MagicMock()

    # Mock DB — battle_cards returns empty, then insert succeeds
    mock_db = MagicMock()
    # First call: battle_cards select returns empty
    mock_select = MagicMock()
    mock_select.data = []
    mock_db.table.return_value.select.return_value.eq.return_value.ilike.return_value.limit.return_value.execute.return_value = mock_select
    # Insert call
    mock_db.table.return_value.insert.return_value.execute.return_value = MagicMock(data=[{"id": "card-1"}])
    executor._db = mock_db

    with patch("src.integrations.tavus_tool_executor.StrategistAgent") as MockStrat:
        mock_agent = AsyncMock()
        mock_agent._call_tool.return_value = {
            "target_company": "Catalent",
            "opportunities": ["Strong mAb portfolio"],
            "challenges": ["High pricing"],
            "recommendation": "Lead with cost efficiency",
            "competitive_analysis": {
                "competitors": [{"name": "Catalent", "strengths": ["Scale"], "weaknesses": ["Slow"]}],
            },
        }
        MockStrat.return_value = mock_agent

        result = await executor._handle_get_battle_card({"competitor_name": "Catalent"})

        # Strategist should have been invoked
        mock_agent._call_tool.assert_called_once()
        assert "Catalent" in result.spoken_text
        assert result.rich_content is not None
        assert result.rich_content["type"] == "battle_card"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/integrations/test_tavus_tool_executor.py::test_get_battle_card_generates_via_strategist_when_not_in_db -v`
Expected: FAIL — current code returns "I don't have a battle card" without calling Strategist

**Step 3: Implement the change**

Replace `_handle_get_battle_card` (lines 254-322):

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

    if result.data:
        card = result.data[0]
        return self._format_battle_card(card, competitor_name)

    # No card in DB — generate one via Strategist
    try:
        from src.agents import StrategistAgent

        agent = StrategistAgent(llm_client=self.llm, user_id=self._user_id)
        analysis = await agent._call_tool(
            "analyze_account",
            goal={"title": f"Competitive analysis of {competitor_name}", "type": "research"},
            context={"target_company": competitor_name},
        )

        if not analysis:
            return ToolResult(
                spoken_text=(
                    f"I don't have a battle card for {competitor_name} yet "
                    "and couldn't generate one right now. Would you like me to try again?"
                )
            )

        # Extract competitive data
        comp_analysis = analysis.get("competitive_analysis", {})
        competitors = comp_analysis.get("competitors", [])
        target = next((c for c in competitors if competitor_name.lower() in c.get("name", "").lower()), {})

        strengths = target.get("strengths", analysis.get("challenges", []))
        weaknesses = target.get("weaknesses", analysis.get("opportunities", []))
        recommendation = analysis.get("recommendation", "")

        # Cache the generated card in DB (best-effort)
        try:
            self.db.table("battle_cards").insert({
                "user_id": self._user_id,
                "competitor_name": competitor_name,
                "strengths": json.dumps(strengths),
                "weaknesses": json.dumps(weaknesses),
                "overview": recommendation,
                "update_source": "strategist_agent",
            }).execute()
        except Exception:
            logger.debug("Failed to cache generated battle card", exc_info=True)

        # Build response
        card = {
            "competitor_name": competitor_name,
            "strengths": strengths,
            "weaknesses": weaknesses,
            "win_strategy": recommendation,
            "our_differentiators": analysis.get("opportunities", []),
        }
        return self._format_battle_card(card, competitor_name)

    except Exception:
        logger.debug("Strategist battle card generation failed", exc_info=True)
        return ToolResult(
            spoken_text=(
                f"I don't have a battle card for {competitor_name} yet. "
                "Would you like me to create one?"
            )
        )

def _format_battle_card(self, card: dict[str, Any], competitor_name: str) -> ToolResult:
    """Format a battle card dict into a ToolResult with spoken text and rich content."""
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

    spoken_text = " ".join(parts)

    rows: list[dict[str, str]] = []
    if strengths:
        s_list = [strengths] if isinstance(strengths, str) else strengths[:3]
        for s_item in s_list:
            rows.append({"dimension": "Strength", "competitor": str(s_item), "us": ""})
    if weaknesses:
        w_list = [weaknesses] if isinstance(weaknesses, str) else weaknesses[:3]
        for w_item in w_list:
            rows.append({"dimension": "Weakness", "competitor": str(w_item), "us": ""})
    if differentiators:
        d_list = [differentiators] if isinstance(differentiators, str) else differentiators[:3]
        for d_item in d_list:
            rows.append({"dimension": "Differentiator", "competitor": "", "us": str(d_item)})
    if win_strategy:
        rows.append({"dimension": "Win Strategy", "competitor": "", "us": win_strategy[:150]})

    rich_content: dict[str, Any] = {
        "type": "battle_card",
        "data": {
            "competitor_name": name,
            "our_company": "Your Team",
            "rows": rows,
        },
    }

    return ToolResult(spoken_text=spoken_text, rich_content=rich_content)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/integrations/test_tavus_tool_executor.py::test_get_battle_card_generates_via_strategist_when_not_in_db -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/integrations/tavus_tool_executor.py backend/tests/integrations/test_tavus_tool_executor.py
git commit -m "feat: generate battle cards via Strategist when not cached in DB"
```

---

### Task 3: Episodic Memory Storage for Video Tool Results

**Files:**
- Modify: `backend/src/integrations/tavus_tool_executor.py` (add `_store_episodic` method + call from `execute`)
- Test: `backend/tests/integrations/test_tavus_tool_executor.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_execute_stores_episodic_memory_on_success():
    """Successful tool execution should store an episodic memory."""
    from src.integrations.tavus_tool_executor import VideoToolExecutor, ToolResult

    executor = VideoToolExecutor(user_id="user-123")
    executor._llm = MagicMock()
    executor._db = MagicMock()

    # Stub a handler that returns successfully
    async def mock_handler(args):
        return ToolResult(spoken_text="Found 3 articles on CAR-T therapy.")

    with patch.object(executor, "_handle_search_pubmed", mock_handler):
        with patch.object(executor, "_log_activity", new_callable=AsyncMock):
            with patch.object(executor, "_store_episodic", new_callable=AsyncMock) as mock_store:
                result = await executor.execute("search_pubmed", {"query": "CAR-T"})

                mock_store.assert_called_once()
                call_args = mock_store.call_args
                assert call_args[0][0] == "search_pubmed"  # tool_name
                assert call_args[0][1] == {"query": "CAR-T"}  # arguments
                assert call_args[0][2].spoken_text == "Found 3 articles on CAR-T therapy."
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/integrations/test_tavus_tool_executor.py::test_execute_stores_episodic_memory_on_success -v`
Expected: FAIL — `_store_episodic` doesn't exist

**Step 3: Implement the change**

Add `_store_episodic` method and call it from `execute()`:

```python
# Add to the execute() method, after line 99 (await self._log_activity):
#   await self._store_episodic(tool_name, arguments, result)

async def _store_episodic(
    self,
    tool_name: str,
    arguments: dict[str, Any],
    result: ToolResult,
) -> None:
    """Store video tool execution as an episodic memory."""
    try:
        from src.memory.episodic import Episode, EpisodicMemory

        em = EpisodicMemory()
        now = datetime.now(UTC)
        episode = Episode(
            id=str(uuid.uuid4()),
            user_id=self._user_id,
            event_type=f"video_tool_{tool_name}",
            content=result.spoken_text,
            participants=[self._user_id],
            occurred_at=now,
            recorded_at=now,
            context={
                "tool_name": tool_name,
                "arguments": arguments,
                "source": "tavus_video",
                "has_rich_content": result.rich_content is not None,
            },
        )
        await em.store_episode(episode)
    except Exception:
        logger.debug("Failed to store episodic memory for video tool", exc_info=True)
```

In the `execute` method, add the call after `_log_activity` (line 99):

```python
try:
    result = await handler(arguments)
    await self._log_activity(tool_name, arguments, success=True)
    await self._store_episodic(tool_name, arguments, result)
    return result
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/integrations/test_tavus_tool_executor.py::test_execute_stores_episodic_memory_on_success -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/integrations/tavus_tool_executor.py backend/tests/integrations/test_tavus_tool_executor.py
git commit -m "feat: store episodic memory for video tool executions"
```

---

### Task 4: OODA Trigger from Video (new tool: trigger_goal_action)

**Files:**
- Modify: `backend/src/integrations/tavus_tools.py` (add tool #13 schema)
- Modify: `backend/src/integrations/tavus_tool_executor.py` (add handler)
- Test: `backend/tests/integrations/test_tavus_tool_executor.py`

**Step 4a: Add tool schema to tavus_tools.py**

Add to `ARIA_VIDEO_TOOLS` list before the closing `]`:

```python
# ── 13. trigger_goal_action (OODA Loop) ──────────────────────────
_tool(
    name="trigger_goal_action",
    description=(
        "Trigger immediate action on one of the user's goals. Use when "
        "the user says things like 'work on my goal', 'make progress on', "
        "'take action on', or refers to a specific strategic objective. "
        "Runs one OODA cycle (observe-orient-decide-act) and returns "
        "what action was taken."
    ),
    properties={
        "goal_description": {
            "type": "string",
            "description": (
                "Description of the goal to act on, e.g. 'expand into "
                "cell therapy market' or 'close the Lonza deal'"
            ),
        },
    },
    required=["goal_description"],
),
```

Add to `TOOL_AGENT_MAP`:

```python
"trigger_goal_action": "ooda",
```

**Step 4b: Write the failing test**

```python
@pytest.mark.asyncio
async def test_trigger_goal_action_runs_ooda_cycle():
    """trigger_goal_action should find a matching goal and run one OODA iteration."""
    from src.integrations.tavus_tool_executor import VideoToolExecutor

    executor = VideoToolExecutor(user_id="user-123")
    executor._llm = MagicMock()

    # Mock DB — goals table returns a matching goal
    mock_db = MagicMock()
    mock_goals_result = MagicMock()
    mock_goals_result.data = [
        {
            "id": "goal-1",
            "title": "Expand into cell therapy market",
            "description": "Target cell therapy CDMOs",
            "goal_type": "research",
            "config": {},
            "progress": 25,
            "status": "active",
        }
    ]
    mock_db.table.return_value.select.return_value.eq.return_value.eq.return_value.execute.return_value = mock_goals_result
    executor._db = mock_db

    with patch("src.integrations.tavus_tool_executor.OODALoop") as MockOODA:
        mock_ooda = AsyncMock()
        mock_state = MagicMock()
        mock_state.is_complete = False
        mock_state.is_blocked = False
        mock_state.decision = {"action": "research", "agent": "analyst", "reasoning": "Need more data"}
        mock_state.action_result = {"summary": "Found 5 cell therapy CDMOs"}
        mock_ooda.run_single_iteration.return_value = mock_state
        MockOODA.return_value = mock_ooda

        with patch("src.integrations.tavus_tool_executor.EpisodicMemory"):
            with patch("src.integrations.tavus_tool_executor.SemanticMemory"):
                result = await executor._handle_trigger_goal_action({
                    "goal_description": "cell therapy"
                })

        assert "cell therapy" in result.spoken_text.lower() or "research" in result.spoken_text.lower()
        mock_ooda.run_single_iteration.assert_called_once()
```

**Step 4c: Implement the handler**

```python
async def _handle_trigger_goal_action(self, args: dict[str, Any]) -> ToolResult:
    goal_description = args["goal_description"]

    # Find matching active goal
    goals_result = (
        self.db.table("goals")
        .select("id, title, description, goal_type, config, progress, status")
        .eq("user_id", self._user_id)
        .eq("status", "active")
        .execute()
    )

    if not goals_result.data:
        return ToolResult(
            spoken_text=(
                "You don't have any active goals right now. "
                "Would you like me to create one?"
            )
        )

    # Find best match by keyword overlap
    query_words = set(goal_description.lower().split())
    best_match = None
    best_score = 0
    for goal in goals_result.data:
        title_words = set(goal.get("title", "").lower().split())
        desc_words = set(goal.get("description", "").lower().split())
        all_words = title_words | desc_words
        overlap = len(query_words & all_words)
        if overlap > best_score:
            best_score = overlap
            best_match = goal

    if not best_match or best_score == 0:
        # No keyword match — use first active goal
        best_match = goals_result.data[0]

    goal_title = best_match.get("title", "your goal")

    # Run one OODA iteration
    try:
        from src.core.ooda import OODAConfig, OODALoop, OODAState
        from src.memory.episodic import EpisodicMemory
        from src.memory.semantic import SemanticMemory
        from src.memory.working import WorkingMemory

        episodic = EpisodicMemory()
        semantic = SemanticMemory()
        working = WorkingMemory(
            conversation_id=f"video-ooda-{best_match['id']}",
            user_id=self._user_id,
        )

        ooda = OODALoop(
            llm_client=self.llm,
            episodic_memory=episodic,
            semantic_memory=semantic,
            working_memory=working,
            config=OODAConfig(max_iterations=1),
        )

        state = OODAState(goal_id=best_match["id"])
        state = await ooda.run_single_iteration(state, best_match)

        decision = state.decision or {}
        action = decision.get("action", "observe")
        agent = decision.get("agent", "")
        reasoning = decision.get("reasoning", "")

        parts = [f"Working on '{goal_title}'."]

        if action == "complete":
            parts.append("This goal appears to be complete based on current data.")
        elif state.is_blocked:
            parts.append(
                f"I'm blocked on this goal. {state.blocked_reason or 'I need more information.'}"
            )
        else:
            if reasoning:
                parts.append(reasoning[:150])
            if agent:
                parts.append(f"I've dispatched the {agent} agent to take action.")
            if state.action_result:
                summary = (
                    state.action_result.get("summary", "")
                    if isinstance(state.action_result, dict)
                    else str(state.action_result)[:150]
                )
                if summary:
                    parts.append(summary[:150])

        parts.append("Want me to continue working on this?")
        return ToolResult(spoken_text=" ".join(parts))

    except Exception:
        logger.exception("OODA trigger failed", extra={"goal_id": best_match.get("id")})
        return ToolResult(
            spoken_text=(
                f"I found your goal '{goal_title}' but ran into an issue "
                "processing it right now. I'll keep monitoring it in the background."
            )
        )
```

**Step 4d: Run tests**

Run: `cd backend && python -m pytest tests/integrations/test_tavus_tool_executor.py -k "trigger_goal" -v`
Expected: PASS

**Step 4e: Commit**

```bash
git add backend/src/integrations/tavus_tools.py backend/src/integrations/tavus_tool_executor.py backend/tests/integrations/test_tavus_tool_executor.py
git commit -m "feat: add trigger_goal_action video tool for OODA loop from video"
```

---

### Task 5: Rich Content for Scout Market Signals

**Files:**
- Modify: `backend/src/integrations/tavus_tool_executor.py:690-725` (`_handle_get_market_signals`)
- Test: `backend/tests/integrations/test_tavus_tool_executor.py`

**Step 1: Write the failing test**

```python
@pytest.mark.asyncio
async def test_get_market_signals_returns_rich_content():
    """get_market_signals should return rich_content with signal_list type."""
    from src.integrations.tavus_tool_executor import VideoToolExecutor

    executor = VideoToolExecutor(user_id="user-123")
    executor._llm = MagicMock()

    with patch("src.integrations.tavus_tool_executor.ScoutAgent") as MockScout:
        mock_agent = AsyncMock()
        mock_agent._call_tool.return_value = [
            {"title": "Lonza acquires biotech startup", "source": "Reuters", "url": "https://example.com/1", "published_at": "2026-02-15"},
            {"title": "Cell therapy market grows 15%", "source": "FiercePharma", "url": "https://example.com/2", "published_at": "2026-02-14"},
        ]
        MockScout.return_value = mock_agent

        result = await executor._handle_get_market_signals({"topic": "cell therapy CDMOs"})

        assert result.rich_content is not None
        assert result.rich_content["type"] == "signal_list"
        assert result.rich_content["data"]["topic"] == "cell therapy CDMOs"
        assert len(result.rich_content["data"]["signals"]) == 2
        assert result.rich_content["data"]["signals"][0]["title"] == "Lonza acquires biotech startup"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/integrations/test_tavus_tool_executor.py::test_get_market_signals_returns_rich_content -v`
Expected: FAIL — `rich_content` is None

**Step 3: Implement the change**

Replace `_handle_get_market_signals` (lines 690-725):

```python
async def _handle_get_market_signals(self, args: dict[str, Any]) -> ToolResult:
    from src.agents import ScoutAgent

    agent = ScoutAgent(llm_client=self.llm, user_id=self._user_id)
    topic = args["topic"]

    results = await agent._call_tool(
        "news_search",
        query=topic,
        limit=5,
        days_back=14,
    )

    if not results:
        return ToolResult(
            spoken_text=f"I didn't find any recent market signals for {topic}. Want me to expand the time window?"
        )

    articles = results if isinstance(results, list) else []
    if not articles:
        return ToolResult(
            spoken_text=f"No recent signals found for {topic}."
        )

    parts = [f"Here are the latest market signals for {topic}."]
    for i, article in enumerate(articles[:4], 1):
        title = article.get("title", "")
        source = article.get("source", "")
        if title:
            entry = f"{i}. {title[:100]}"
            if source:
                entry += f" from {source}"
            parts.append(entry)

    parts.append("Would you like me to analyse any of these signals in more detail?")

    # Build rich content for signal overlay
    signal_items: list[dict[str, str]] = []
    for article in articles[:5]:
        signal_items.append({
            "title": article.get("title", ""),
            "source": article.get("source", ""),
            "url": article.get("url", ""),
            "date": article.get("published_at", article.get("date", "")),
        })

    rich_content: dict[str, Any] = {
        "type": "signal_list",
        "data": {
            "topic": topic,
            "signals": signal_items,
        },
    }

    return ToolResult(spoken_text=" ".join(parts), rich_content=rich_content)
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/integrations/test_tavus_tool_executor.py::test_get_market_signals_returns_rich_content -v`
Expected: PASS

**Step 5: Commit**

```bash
git add backend/src/integrations/tavus_tool_executor.py backend/tests/integrations/test_tavus_tool_executor.py
git commit -m "feat: add rich content overlay for Scout market signals in video"
```

---

### Task 6: Run Full Test Suite and Final Commit

**Step 1: Run all new tests together**

Run: `cd backend && python -m pytest tests/integrations/test_tavus_tool_executor.py -v`
Expected: All tests PASS

**Step 2: Run linter**

Run: `cd backend && ruff check src/integrations/tavus_tool_executor.py src/integrations/tavus_tools.py`
Expected: No errors (fix any that appear)

**Step 3: Run type checker**

Run: `cd backend && mypy src/integrations/tavus_tool_executor.py src/integrations/tavus_tools.py --ignore-missing-imports`
Expected: No errors

**Step 4: Final commit if any lint/type fixes were needed**

```bash
git add -A
git commit -m "fix: resolve lint and type issues in video agent integration"
```
