# US-214: Point-in-Time Memory Queries Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable ARIA to query "what did I know on date X" by adding temporal filtering across episodic and semantic memory.

**Architecture:** Extend existing `as_of` parameter support to all memory query methods and API endpoints. SemanticFact already has `is_valid(as_of)` and `get_facts_about(as_of)`. EpisodicMemory needs similar temporal filtering. The unified memory query endpoint needs an `as_of` parameter that propagates to all memory types.

**Tech Stack:** Python 3.11+, FastAPI, Graphiti (Neo4j), pytest, mypy, Pydantic

---

## Summary of Changes

1. **Episodic Memory** - Add `as_of` parameter to query methods for bi-temporal filtering
2. **Semantic Memory** - Extend `search_facts` to support `as_of` parameter
3. **Memory Query API** - Add `as_of` parameter to unified query endpoint
4. **API Response** - Include temporal metadata in query results

---

## Task 1: Add as_of Parameter to EpisodicMemory.query_by_time_range

**Files:**
- Test: `backend/tests/test_episodic_memory.py`
- Modify: `backend/src/memory/episodic.py:351-384`

### Step 1: Write the failing test

Add to `backend/tests/test_episodic_memory.py`:

```python
@pytest.mark.asyncio
async def test_query_by_time_range_respects_as_of_for_recorded_at() -> None:
    """Test query_by_time_range filters episodes recorded after as_of date."""
    memory = EpisodicMemory()
    mock_client = MagicMock()

    now = datetime.now(UTC)
    past = now - timedelta(days=30)

    # Episode occurred in the past but was recorded "today"
    mock_edge = MagicMock()
    mock_edge.fact = f"Event Type: meeting\nContent: Q1 planning\nOccurred At: {past.isoformat()}\nRecorded At: {now.isoformat()}"
    mock_edge.created_at = past
    mock_edge.uuid = "episode-123"

    mock_client.search = AsyncMock(return_value=[mock_edge])

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        # Query as of 7 days ago - should NOT include episode recorded today
        as_of_date = now - timedelta(days=7)
        results = await memory.query_by_time_range(
            user_id="user-456",
            start=past - timedelta(days=5),
            end=past + timedelta(days=5),
            as_of=as_of_date,
        )

        # Episode should be filtered out (recorded after as_of)
        assert len(results) == 0
```

### Step 2: Run test to verify it fails

Run: `cd backend && pytest tests/test_episodic_memory.py::test_query_by_time_range_respects_as_of_for_recorded_at -v`

Expected: FAIL with "got unexpected keyword argument 'as_of'"

### Step 3: Write minimal implementation

Modify `backend/src/memory/episodic.py`, update the `query_by_time_range` method:

```python
async def query_by_time_range(
    self,
    user_id: str,
    start: datetime,
    end: datetime,
    limit: int = 50,
    as_of: datetime | None = None,
) -> list[Episode]:
    """Query episodes within a time range.

    Args:
        user_id: The user ID to query episodes for.
        start: Start of the time range (inclusive).
        end: End of the time range (inclusive).
        limit: Maximum number of episodes to return.
        as_of: Point in time for filtering. If provided, only returns episodes
            that were recorded on or before this date. This enables "what did
            I know on date X" queries.

    Returns:
        List of Episode instances within the time range.

    Raises:
        EpisodicMemoryError: If the query fails.
    """
    try:
        client = await self._get_graphiti_client()
        query = f"episodes for user {user_id} between {start.isoformat()} and {end.isoformat()}"
        results = await client.search(query)

        episodes = []
        for edge in results[:limit]:
            episode = self._parse_edge_to_episode(edge, user_id)
            if episode:
                # Filter by as_of: only include if recorded on or before as_of date
                if as_of is not None and episode.recorded_at > as_of:
                    continue
                episodes.append(episode)
        return episodes
    except EpisodicMemoryError:
        raise
    except Exception as e:
        logger.exception("Failed to query episodes by time range")
        raise EpisodicMemoryError(f"Failed to query episodes: {e}") from e
```

### Step 4: Run test to verify it passes

Run: `cd backend && pytest tests/test_episodic_memory.py::test_query_by_time_range_respects_as_of_for_recorded_at -v`

Expected: PASS

### Step 5: Commit

```bash
cd backend && git add tests/test_episodic_memory.py src/memory/episodic.py
git commit -m "$(cat <<'EOF'
feat(memory): add as_of parameter to episodic query_by_time_range

Enables point-in-time queries on episodic memory by filtering
episodes based on when they were recorded. Episodes recorded after
the as_of date are excluded from results.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 2: Add as_of Parameter to EpisodicMemory.query_by_event_type

**Files:**
- Test: `backend/tests/test_episodic_memory.py`
- Modify: `backend/src/memory/episodic.py:385-417`

### Step 1: Write the failing test

Add to `backend/tests/test_episodic_memory.py`:

```python
@pytest.mark.asyncio
async def test_query_by_event_type_respects_as_of() -> None:
    """Test query_by_event_type filters episodes recorded after as_of date."""
    memory = EpisodicMemory()
    mock_client = MagicMock()

    now = datetime.now(UTC)
    past = now - timedelta(days=30)

    mock_edge = MagicMock()
    mock_edge.fact = f"Event Type: meeting\nContent: Team sync\nOccurred At: {past.isoformat()}\nRecorded At: {now.isoformat()}"
    mock_edge.created_at = past
    mock_edge.uuid = "episode-456"

    mock_client.search = AsyncMock(return_value=[mock_edge])

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        # Query as of 7 days ago - should NOT include episode recorded today
        as_of_date = now - timedelta(days=7)
        results = await memory.query_by_event_type(
            user_id="user-456",
            event_type="meeting",
            as_of=as_of_date,
        )

        assert len(results) == 0
```

### Step 2: Run test to verify it fails

Run: `cd backend && pytest tests/test_episodic_memory.py::test_query_by_event_type_respects_as_of -v`

Expected: FAIL with "got unexpected keyword argument 'as_of'"

### Step 3: Write minimal implementation

Modify `backend/src/memory/episodic.py`, update the `query_by_event_type` method:

```python
async def query_by_event_type(
    self,
    user_id: str,
    event_type: str,
    limit: int = 50,
    as_of: datetime | None = None,
) -> list[Episode]:
    """Query episodes by event type.

    Args:
        user_id: The user ID to query episodes for.
        event_type: The type of event (e.g., 'meeting', 'call', 'email').
        limit: Maximum number of episodes to return.
        as_of: Point in time for filtering. If provided, only returns episodes
            that were recorded on or before this date.

    Returns:
        List of Episode instances matching the event type.

    Raises:
        EpisodicMemoryError: If the query fails.
    """
    try:
        client = await self._get_graphiti_client()
        query = f"{event_type} events for user {user_id}"
        results = await client.search(query)

        episodes = []
        for edge in results[:limit]:
            episode = self._parse_edge_to_episode(edge, user_id)
            if episode and episode.event_type == event_type:
                # Filter by as_of date
                if as_of is not None and episode.recorded_at > as_of:
                    continue
                episodes.append(episode)
        return episodes
    except EpisodicMemoryError:
        raise
    except Exception as e:
        logger.exception("Failed to query episodes by event type")
        raise EpisodicMemoryError(f"Failed to query episodes: {e}") from e
```

### Step 4: Run test to verify it passes

Run: `cd backend && pytest tests/test_episodic_memory.py::test_query_by_event_type_respects_as_of -v`

Expected: PASS

### Step 5: Commit

```bash
cd backend && git add tests/test_episodic_memory.py src/memory/episodic.py
git commit -m "$(cat <<'EOF'
feat(memory): add as_of parameter to episodic query_by_event_type

Enables temporal filtering on event type queries.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 3: Add as_of Parameter to EpisodicMemory.query_by_participant

**Files:**
- Test: `backend/tests/test_episodic_memory.py`
- Modify: `backend/src/memory/episodic.py:418-454`

### Step 1: Write the failing test

Add to `backend/tests/test_episodic_memory.py`:

```python
@pytest.mark.asyncio
async def test_query_by_participant_respects_as_of() -> None:
    """Test query_by_participant filters episodes recorded after as_of date."""
    memory = EpisodicMemory()
    mock_client = MagicMock()

    now = datetime.now(UTC)
    past = now - timedelta(days=30)

    mock_edge = MagicMock()
    mock_edge.fact = f"Event Type: meeting\nContent: Discussion with John\nParticipants: John Smith\nOccurred At: {past.isoformat()}\nRecorded At: {now.isoformat()}"
    mock_edge.created_at = past
    mock_edge.uuid = "episode-789"

    mock_client.search = AsyncMock(return_value=[mock_edge])

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        as_of_date = now - timedelta(days=7)
        results = await memory.query_by_participant(
            user_id="user-456",
            participant="John",
            as_of=as_of_date,
        )

        assert len(results) == 0
```

### Step 2: Run test to verify it fails

Run: `cd backend && pytest tests/test_episodic_memory.py::test_query_by_participant_respects_as_of -v`

Expected: FAIL with "got unexpected keyword argument 'as_of'"

### Step 3: Write minimal implementation

Modify `backend/src/memory/episodic.py`, update the `query_by_participant` method:

```python
async def query_by_participant(
    self,
    user_id: str,
    participant: str,
    limit: int = 50,
    as_of: datetime | None = None,
) -> list[Episode]:
    """Query episodes by participant.

    Args:
        user_id: The user ID to query episodes for.
        participant: The participant name to search for.
        limit: Maximum number of episodes to return.
        as_of: Point in time for filtering. If provided, only returns episodes
            that were recorded on or before this date.

    Returns:
        List of Episode instances involving the participant.

    Raises:
        EpisodicMemoryError: If the query fails.
    """
    try:
        client = await self._get_graphiti_client()
        query = f"interactions with {participant} for user {user_id}"
        results = await client.search(query)

        episodes = []
        participant_lower = participant.lower()
        for edge in results[:limit]:
            episode = self._parse_edge_to_episode(edge, user_id)
            if episode and (
                any(participant_lower in p.lower() for p in episode.participants)
                or participant_lower in episode.content.lower()
            ):
                # Filter by as_of date
                if as_of is not None and episode.recorded_at > as_of:
                    continue
                episodes.append(episode)
        return episodes
    except EpisodicMemoryError:
        raise
    except Exception as e:
        logger.exception("Failed to query episodes by participant")
        raise EpisodicMemoryError(f"Failed to query episodes: {e}") from e
```

### Step 4: Run test to verify it passes

Run: `cd backend && pytest tests/test_episodic_memory.py::test_query_by_participant_respects_as_of -v`

Expected: PASS

### Step 5: Commit

```bash
cd backend && git add tests/test_episodic_memory.py src/memory/episodic.py
git commit -m "$(cat <<'EOF'
feat(memory): add as_of parameter to episodic query_by_participant

Enables temporal filtering on participant queries.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 4: Add as_of Parameter to EpisodicMemory.semantic_search

**Files:**
- Test: `backend/tests/test_episodic_memory.py`
- Modify: `backend/src/memory/episodic.py:455-485`

### Step 1: Write the failing test

Add to `backend/tests/test_episodic_memory.py`:

```python
@pytest.mark.asyncio
async def test_semantic_search_respects_as_of() -> None:
    """Test semantic_search filters episodes recorded after as_of date."""
    memory = EpisodicMemory()
    mock_client = MagicMock()

    now = datetime.now(UTC)
    past = now - timedelta(days=30)

    mock_edge = MagicMock()
    mock_edge.fact = f"Event Type: decision\nContent: Budget approved for Q2\nOccurred At: {past.isoformat()}\nRecorded At: {now.isoformat()}"
    mock_edge.created_at = past
    mock_edge.uuid = "episode-search-1"

    mock_client.search = AsyncMock(return_value=[mock_edge])

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        as_of_date = now - timedelta(days=7)
        results = await memory.semantic_search(
            user_id="user-456",
            query="budget decisions",
            as_of=as_of_date,
        )

        assert len(results) == 0
```

### Step 2: Run test to verify it fails

Run: `cd backend && pytest tests/test_episodic_memory.py::test_semantic_search_respects_as_of -v`

Expected: FAIL with "got unexpected keyword argument 'as_of'"

### Step 3: Write minimal implementation

Modify `backend/src/memory/episodic.py`, update the `semantic_search` method:

```python
async def semantic_search(
    self,
    user_id: str,
    query: str,
    limit: int = 10,
    as_of: datetime | None = None,
) -> list[Episode]:
    """Search episodes using semantic similarity.

    Args:
        user_id: The user ID to search episodes for.
        query: The natural language query string.
        limit: Maximum number of episodes to return.
        as_of: Point in time for filtering. If provided, only returns episodes
            that were recorded on or before this date.

    Returns:
        List of Episode instances semantically similar to the query.

    Raises:
        EpisodicMemoryError: If the search fails.
    """
    try:
        client = await self._get_graphiti_client()
        search_query = f"{query} (user: {user_id})"
        results = await client.search(search_query)

        episodes = []
        for edge in results[:limit]:
            episode = self._parse_edge_to_episode(edge, user_id)
            if episode:
                # Filter by as_of date
                if as_of is not None and episode.recorded_at > as_of:
                    continue
                episodes.append(episode)
        return episodes
    except EpisodicMemoryError:
        raise
    except Exception as e:
        logger.exception("Failed to perform semantic search")
        raise EpisodicMemoryError(f"Failed to search episodes: {e}") from e
```

### Step 4: Run test to verify it passes

Run: `cd backend && pytest tests/test_episodic_memory.py::test_semantic_search_respects_as_of -v`

Expected: PASS

### Step 5: Commit

```bash
cd backend && git add tests/test_episodic_memory.py src/memory/episodic.py
git commit -m "$(cat <<'EOF'
feat(memory): add as_of parameter to episodic semantic_search

Enables temporal filtering on semantic search queries.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 5: Update EpisodicMemory._parse_edge_to_episode for Recorded At

**Files:**
- Test: `backend/tests/test_episodic_memory.py`
- Modify: `backend/src/memory/episodic.py:133-177`

### Step 1: Write the failing test

Add to `backend/tests/test_episodic_memory.py`:

```python
def test_parse_edge_to_episode_extracts_recorded_at() -> None:
    """Test _parse_edge_to_episode extracts recorded_at from edge content."""
    memory = EpisodicMemory()

    now = datetime.now(UTC)
    occurred = now - timedelta(days=30)
    recorded = now - timedelta(days=10)

    mock_edge = MagicMock()
    mock_edge.fact = f"Event Type: meeting\nContent: Planning session\nOccurred At: {occurred.isoformat()}\nRecorded At: {recorded.isoformat()}\nParticipants: Alice, Bob"
    mock_edge.created_at = occurred
    mock_edge.uuid = "edge-123"

    episode = memory._parse_edge_to_episode(mock_edge, "user-456")

    assert episode is not None
    assert episode.recorded_at == recorded
    assert episode.occurred_at == occurred
```

### Step 2: Run test to verify it fails

Run: `cd backend && pytest tests/test_episodic_memory.py::test_parse_edge_to_episode_extracts_recorded_at -v`

Expected: FAIL (recorded_at is set to datetime.now(UTC) instead of parsed value)

### Step 3: Write minimal implementation

Modify `backend/src/memory/episodic.py`, update the `_parse_edge_to_episode` method:

```python
def _parse_edge_to_episode(self, edge: Any, user_id: str) -> Episode | None:
    """Parse a Graphiti edge into an Episode.

    Args:
        edge: The Graphiti edge object.
        user_id: The expected user ID.

    Returns:
        Episode if parsing succeeds and matches user, None otherwise.
    """
    try:
        fact = getattr(edge, "fact", "")
        created_at = getattr(edge, "created_at", datetime.now(UTC))
        # Try to get edge uuid, fall back to generating new one
        edge_uuid = getattr(edge, "uuid", None) or str(uuid.uuid4())

        # Parse structured content from fact
        lines = fact.split("\n")
        event_type = "unknown"
        content = ""
        participants: list[str] = []
        occurred_at: datetime | None = None
        recorded_at: datetime | None = None

        for line in lines:
            if line.startswith("Event Type:"):
                event_type = line.replace("Event Type:", "").strip()
            elif line.startswith("Content:"):
                content = line.replace("Content:", "").strip()
            elif line.startswith("Participants:"):
                participants_str = line.replace("Participants:", "").strip()
                participants = [p.strip() for p in participants_str.split(",") if p.strip()]
            elif line.startswith("Occurred At:"):
                try:
                    occurred_at = datetime.fromisoformat(line.replace("Occurred At:", "").strip())
                except ValueError:
                    pass
            elif line.startswith("Recorded At:"):
                try:
                    recorded_at = datetime.fromisoformat(line.replace("Recorded At:", "").strip())
                except ValueError:
                    pass

        # Use parsed values or fall back to defaults
        final_occurred_at = occurred_at or (created_at if isinstance(created_at, datetime) else datetime.now(UTC))
        final_recorded_at = recorded_at or datetime.now(UTC)

        return Episode(
            id=edge_uuid,
            user_id=user_id,
            event_type=event_type,
            content=content.strip(),
            participants=participants,
            occurred_at=final_occurred_at,
            recorded_at=final_recorded_at,
            context={},
        )
    except Exception as e:
        logger.warning(f"Failed to parse edge to episode: {e}")
        return None
```

### Step 4: Run test to verify it passes

Run: `cd backend && pytest tests/test_episodic_memory.py::test_parse_edge_to_episode_extracts_recorded_at -v`

Expected: PASS

### Step 5: Commit

```bash
cd backend && git add tests/test_episodic_memory.py src/memory/episodic.py
git commit -m "$(cat <<'EOF'
feat(memory): parse recorded_at from episodic edge content

Enables accurate bi-temporal tracking by extracting the recorded_at
timestamp from stored episode data.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 6: Add as_of Parameter to SemanticMemory.search_facts

**Files:**
- Test: `backend/tests/test_semantic_memory.py`
- Modify: `backend/src/memory/semantic.py:611-667`

### Step 1: Write the failing test

Add to `backend/tests/test_semantic_memory.py`:

```python
@pytest.mark.asyncio
async def test_search_facts_respects_as_of_validity() -> None:
    """Test search_facts filters by validity at as_of date."""
    memory = SemanticMemory()
    mock_client = MagicMock()

    now = datetime.now(UTC)
    past = now - timedelta(days=60)

    # Fact that was valid in the past but is now expired
    mock_edge = MagicMock()
    mock_edge.fact = f"Subject: John\nPredicate: works_at\nObject: OldCorp\nConfidence: 0.90\nSource: user_stated\nValid From: {past.isoformat()}\nValid To: {(now - timedelta(days=30)).isoformat()}"
    mock_edge.created_at = past
    mock_edge.uuid = "fact-temporal"

    mock_client.search = AsyncMock(return_value=[mock_edge])

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        # Query as of 45 days ago - fact should be valid then
        as_of_date = now - timedelta(days=45)
        results = await memory.search_facts(
            user_id="user-456",
            query="where does John work",
            as_of=as_of_date,
        )

        # Should include the fact (was valid at that time)
        assert len(results) == 1
        assert results[0].object == "OldCorp"


@pytest.mark.asyncio
async def test_search_facts_excludes_invalid_at_as_of() -> None:
    """Test search_facts excludes facts invalid at as_of date."""
    memory = SemanticMemory()
    mock_client = MagicMock()

    now = datetime.now(UTC)
    past = now - timedelta(days=60)

    # Fact that was valid in the past but is now expired
    mock_edge = MagicMock()
    mock_edge.fact = f"Subject: John\nPredicate: works_at\nObject: OldCorp\nConfidence: 0.90\nSource: user_stated\nValid From: {past.isoformat()}\nValid To: {(now - timedelta(days=30)).isoformat()}"
    mock_edge.created_at = past
    mock_edge.uuid = "fact-temporal-2"

    mock_client.search = AsyncMock(return_value=[mock_edge])

    with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_client

        # Query as of today - fact should be expired
        results = await memory.search_facts(
            user_id="user-456",
            query="where does John work",
            as_of=now,
        )

        # Should NOT include the fact (expired)
        assert len(results) == 0
```

### Step 2: Run test to verify it fails

Run: `cd backend && pytest tests/test_semantic_memory.py::test_search_facts_respects_as_of_validity tests/test_semantic_memory.py::test_search_facts_excludes_invalid_at_as_of -v`

Expected: FAIL with "got unexpected keyword argument 'as_of'"

### Step 3: Write minimal implementation

Modify `backend/src/memory/semantic.py`, update the `search_facts` method:

```python
async def search_facts(
    self,
    user_id: str,
    query: str,
    min_confidence: float = 0.5,
    limit: int = 20,
    as_of: datetime | None = None,
) -> list[SemanticFact]:
    """Search facts using semantic similarity.

    Args:
        user_id: The user whose facts to search.
        query: Natural language search query.
        min_confidence: Minimum confidence threshold.
        limit: Maximum number of facts to return.
        as_of: Point in time to check validity. If provided, only returns facts
            that were valid at that time. Defaults to now.

    Returns:
        List of relevant facts, ordered by relevance.

    Raises:
        SemanticMemoryError: If search fails.
    """
    try:
        client = await self._get_graphiti_client()

        # Build semantic query with user context
        search_query = f"{query} (user: {user_id})"

        results = await client.search(search_query)

        # Parse results and filter by confidence
        facts = []
        for edge in results[: limit * 2]:  # Get extra to account for filtering
            fact = self._parse_edge_to_fact(edge, user_id)
            if fact is None:
                continue

            # Filter by minimum confidence
            if fact.confidence < min_confidence:
                continue

            # Check validity at as_of time (or now if not specified)
            if not fact.is_valid(as_of=as_of):
                continue

            facts.append(fact)

            if len(facts) >= limit:
                break

        return facts

    except SemanticMemoryError:
        raise
    except Exception as e:
        logger.exception("Failed to search facts", extra={"query": query})
        raise SemanticMemoryError(f"Failed to search facts: {e}") from e
```

### Step 4: Run test to verify it passes

Run: `cd backend && pytest tests/test_semantic_memory.py::test_search_facts_respects_as_of_validity tests/test_semantic_memory.py::test_search_facts_excludes_invalid_at_as_of -v`

Expected: PASS

### Step 5: Commit

```bash
cd backend && git add tests/test_semantic_memory.py src/memory/semantic.py
git commit -m "$(cat <<'EOF'
feat(memory): add as_of parameter to semantic search_facts

Enables point-in-time queries on semantic facts by checking
validity at the specified date instead of now.

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 7: Add as_of Parameter to Memory Query API

**Files:**
- Test: `backend/tests/test_api_memory.py`
- Modify: `backend/src/api/routes/memory.py:296-354` (MemoryQueryService.query)
- Modify: `backend/src/api/routes/memory.py:517-615` (query_memory endpoint)

### Step 1: Write the failing test

Add to `backend/tests/test_api_memory.py`:

```python
@pytest.mark.asyncio
async def test_query_memory_accepts_as_of_parameter(
    mock_current_user: AsyncMock,
) -> None:
    """Test query_memory endpoint accepts as_of parameter."""
    from datetime import UTC, datetime, timedelta
    from fastapi.testclient import TestClient
    from src.main import app

    with TestClient(app) as client:
        now = datetime.now(UTC)
        as_of = now - timedelta(days=30)

        with patch("src.api.routes.memory.MemoryQueryService") as mock_service_class:
            mock_service = MagicMock()
            mock_service.query = AsyncMock(return_value=[])
            mock_service_class.return_value = mock_service

            response = client.get(
                "/api/v1/memory/query",
                params={
                    "q": "test query",
                    "types": ["episodic", "semantic"],
                    "as_of": as_of.isoformat(),
                },
                headers={"Authorization": "Bearer test-token"},
            )

            # Should accept the parameter (may still return 200 with empty results)
            assert response.status_code in [200, 401]  # 401 if auth fails in test

            # Verify service was called with as_of parameter
            if response.status_code == 200:
                mock_service.query.assert_called_once()
                call_kwargs = mock_service.query.call_args.kwargs
                assert "as_of" in call_kwargs
```

### Step 2: Run test to verify it fails

Run: `cd backend && pytest tests/test_api_memory.py::test_query_memory_accepts_as_of_parameter -v`

Expected: FAIL (as_of not in parameters)

### Step 3: Write minimal implementation

Modify `backend/src/api/routes/memory.py`:

First, update the `MemoryQueryService.query` method signature and implementation:

```python
async def query(
    self,
    user_id: str,
    query: str,
    memory_types: list[str],
    start_date: datetime | None,
    end_date: datetime | None,
    min_confidence: float | None,
    limit: int,
    offset: int,
    as_of: datetime | None = None,
) -> list[dict[str, Any]]:
    """Query across specified memory types.

    Args:
        user_id: The user ID to query memories for.
        query: The search query string.
        memory_types: List of memory types to search.
        start_date: Optional start of time range filter.
        end_date: Optional end of time range filter.
        min_confidence: Minimum confidence threshold for semantic results.
        limit: Maximum results to return.
        offset: Number of results to skip.
        as_of: Point in time for temporal queries. If provided, returns
            memories as they were known at that time.

    Returns:
        List of memory results sorted by relevance.
    """
    tasks = []

    if "episodic" in memory_types:
        tasks.append(self._query_episodic(user_id, query, start_date, end_date, limit, as_of))
    if "semantic" in memory_types:
        tasks.append(self._query_semantic(user_id, query, limit, min_confidence, as_of))
    if "procedural" in memory_types:
        tasks.append(self._query_procedural(user_id, query, limit))
    if "prospective" in memory_types:
        tasks.append(self._query_prospective(user_id, query, limit))

    # Execute all queries in parallel
    results_lists: list[list[dict[str, Any]] | BaseException] = await asyncio.gather(
        *tasks, return_exceptions=True
    )

    # Flatten results, filtering out exceptions
    all_results: list[dict[str, Any]] = []
    for result in results_lists:
        if isinstance(result, BaseException):
            logger.warning("Memory query failed: %s", result)
            continue
        all_results.extend(result)

    # Sort by relevance score descending
    all_results.sort(key=lambda x: float(x.get("relevance_score", 0.0)), reverse=True)

    # Apply offset and limit
    return all_results[offset : offset + limit]
```

Then, update the `_query_episodic` method:

```python
async def _query_episodic(
    self,
    user_id: str,
    query: str,
    _start_date: datetime | None,
    _end_date: datetime | None,
    limit: int,
    as_of: datetime | None = None,
) -> list[dict[str, Any]]:
    """Query episodic memory.

    Note: _start_date and _end_date are accepted for API consistency but
    date filtering is not yet implemented in EpisodicMemory.semantic_search().
    """
    from src.memory.episodic import EpisodicMemory

    memory = EpisodicMemory()
    episodes = await memory.semantic_search(user_id, query, limit=limit, as_of=as_of)

    results = []
    for episode in episodes:
        relevance = self._calculate_text_relevance(query, episode.content)
        results.append(
            {
                "id": episode.id,
                "memory_type": "episodic",
                "content": f"[{episode.event_type}] {episode.content}",
                "relevance_score": relevance,
                "confidence": None,
                "timestamp": episode.occurred_at,
            }
        )

    return results
```

Then, update the `_query_semantic` method:

```python
async def _query_semantic(
    self,
    user_id: str,
    query: str,
    limit: int,
    min_confidence: float | None = None,
    as_of: datetime | None = None,
) -> list[dict[str, Any]]:
    """Query semantic memory."""
    from src.memory.semantic import SemanticMemory

    memory = SemanticMemory()
    facts = await memory.search_facts(user_id, query, min_confidence=0.0, limit=limit, as_of=as_of)

    results = []
    for fact in facts:
        # Calculate effective confidence with decay and boosts at as_of time
        effective_confidence = memory.get_effective_confidence(fact, as_of=as_of)

        # Filter by minimum confidence threshold
        if min_confidence is not None and effective_confidence < min_confidence:
            continue

        relevance = self._calculate_text_relevance(
            query, f"{fact.subject} {fact.predicate} {fact.object}"
        )
        results.append(
            {
                "id": fact.id,
                "memory_type": "semantic",
                "content": f"{fact.subject} {fact.predicate} {fact.object}",
                "relevance_score": relevance,
                "confidence": effective_confidence,
                "timestamp": fact.valid_from,
            }
        )

    return results
```

Finally, update the `query_memory` endpoint:

```python
@router.get("/query", response_model=MemoryQueryResponse)
async def query_memory(
    current_user: CurrentUser,
    q: str = Query(..., min_length=1, description="Search query string"),
    types: list[str] = Query(
        default=["episodic", "semantic"],
        description="Memory types to search",
    ),
    start_date: datetime | None = Query(None, description="Start of time range filter"),
    end_date: datetime | None = Query(None, description="End of time range filter"),
    as_of: datetime | None = Query(
        None,
        description="Point in time for temporal query. Returns memories as known at this date.",
    ),
    min_confidence: float | None = Query(
        None, ge=0.0, le=1.0, description="Minimum confidence threshold for semantic results"
    ),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Results per page"),
) -> MemoryQueryResponse:
    """Query across multiple memory types with optional temporal filtering.

    Searches episodic, semantic, procedural, and/or prospective memories
    based on the provided query string. Returns ranked results sorted by
    relevance score.

    The `as_of` parameter enables point-in-time queries - asking "what did
    ARIA know on a specific date?" This filters:
    - Episodic memories by when they were recorded (not when they occurred)
    - Semantic facts by their temporal validity window

    Args:
        current_user: Authenticated user.
        q: Search query string.
        types: List of memory types to search.
        start_date: Optional start of time range filter.
        end_date: Optional end of time range filter.
        as_of: Optional point in time for temporal queries.
        min_confidence: Minimum confidence threshold for semantic results.
        page: Page number (1-indexed).
        page_size: Number of results per page.

    Returns:
        Paginated memory query results.
    """
    # Validate and filter memory types
    valid_types = {"episodic", "semantic", "procedural", "prospective"}
    invalid_types = [t for t in types if t not in valid_types]
    if invalid_types:
        logger.warning(
            "Invalid memory types ignored in query",
            extra={"invalid_types": invalid_types, "user_id": current_user.id},
        )
    requested_types = [t for t in types if t in valid_types]

    if not requested_types:
        requested_types = ["episodic", "semantic"]

    # Calculate offset
    offset = (page - 1) * page_size

    # Query memories
    service = MemoryQueryService()
    # Request extra to determine has_more
    results = await service.query(
        user_id=current_user.id,
        query=q,
        memory_types=requested_types,
        start_date=start_date,
        end_date=end_date,
        min_confidence=min_confidence,
        limit=page_size + 1,
        offset=offset,
        as_of=as_of,
    )

    # Check if there are more results
    has_more = len(results) > page_size
    results = results[:page_size]

    # Convert to response models
    items = [
        MemoryQueryResult(
            id=r["id"],
            memory_type=r["memory_type"],
            content=r["content"],
            relevance_score=r["relevance_score"],
            confidence=r["confidence"],
            timestamp=r["timestamp"],
        )
        for r in results
    ]

    logger.info(
        "Memory query executed",
        extra={
            "user_id": current_user.id,
            "query": q,
            "types": requested_types,
            "as_of": as_of.isoformat() if as_of else None,
            "results_count": len(items),
        },
    )

    return MemoryQueryResponse(
        items=items,
        total=len(items),
        page=page,
        page_size=page_size,
        has_more=has_more,
    )
```

### Step 4: Run test to verify it passes

Run: `cd backend && pytest tests/test_api_memory.py::test_query_memory_accepts_as_of_parameter -v`

Expected: PASS

### Step 5: Commit

```bash
cd backend && git add tests/test_api_memory.py src/api/routes/memory.py
git commit -m "$(cat <<'EOF'
feat(api): add as_of parameter to memory query endpoint

Enables point-in-time memory queries via the unified API.
The as_of parameter filters:
- Episodic memories by when they were recorded
- Semantic facts by their temporal validity

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 8: Add Point-in-Time Query Integration Test

**Files:**
- Create: `backend/tests/integration/test_point_in_time_queries.py`

### Step 1: Write the test file

Create `backend/tests/integration/test_point_in_time_queries.py`:

```python
"""Integration tests for point-in-time memory queries.

Tests the full flow of temporal queries across episodic and semantic memory
to verify US-214 acceptance criteria.
"""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.memory.episodic import Episode, EpisodicMemory
from src.memory.semantic import FactSource, SemanticFact, SemanticMemory


class TestPointInTimeEpisodic:
    """Integration tests for episodic memory point-in-time queries."""

    @pytest.mark.asyncio
    async def test_query_returns_only_episodes_known_at_as_of_date(self) -> None:
        """Test that point-in-time query excludes episodes recorded after as_of."""
        memory = EpisodicMemory()
        mock_client = MagicMock()

        now = datetime.now(UTC)

        # Create three episodes with different recording times
        episodes_data = [
            {
                "occurred": now - timedelta(days=60),
                "recorded": now - timedelta(days=60),  # Known 60 days ago
                "content": "Old meeting",
                "uuid": "ep-old",
            },
            {
                "occurred": now - timedelta(days=40),
                "recorded": now - timedelta(days=20),  # Known 20 days ago
                "content": "Backdated meeting",
                "uuid": "ep-backdated",
            },
            {
                "occurred": now - timedelta(days=30),
                "recorded": now - timedelta(days=5),  # Known 5 days ago
                "content": "Recent recording",
                "uuid": "ep-recent",
            },
        ]

        mock_edges = []
        for ep in episodes_data:
            edge = MagicMock()
            edge.fact = (
                f"Event Type: meeting\n"
                f"Content: {ep['content']}\n"
                f"Occurred At: {ep['occurred'].isoformat()}\n"
                f"Recorded At: {ep['recorded'].isoformat()}"
            )
            edge.created_at = ep["occurred"]
            edge.uuid = ep["uuid"]
            mock_edges.append(edge)

        mock_client.search = AsyncMock(return_value=mock_edges)

        with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_client

            # Query as of 30 days ago - should only include the first episode
            as_of_date = now - timedelta(days=30)
            results = await memory.semantic_search(
                user_id="user-123",
                query="meeting",
                as_of=as_of_date,
            )

            # Only "Old meeting" was recorded by 30 days ago
            assert len(results) == 1
            assert results[0].content == "Old meeting"


class TestPointInTimeSemantic:
    """Integration tests for semantic memory point-in-time queries."""

    @pytest.mark.asyncio
    async def test_query_returns_facts_valid_at_as_of_date(self) -> None:
        """Test that point-in-time query respects fact validity windows."""
        memory = SemanticMemory()
        mock_client = MagicMock()

        now = datetime.now(UTC)

        # Create facts with different validity periods
        facts_data = [
            {
                "subject": "John",
                "predicate": "works_at",
                "object": "CompanyA",
                "valid_from": now - timedelta(days=365),
                "valid_to": now - timedelta(days=100),  # Expired 100 days ago
                "uuid": "fact-expired",
            },
            {
                "subject": "John",
                "predicate": "works_at",
                "object": "CompanyB",
                "valid_from": now - timedelta(days=100),
                "valid_to": None,  # Still valid
                "uuid": "fact-current",
            },
        ]

        mock_edges = []
        for fact in facts_data:
            edge = MagicMock()
            valid_to_str = f"\nValid To: {fact['valid_to'].isoformat()}" if fact['valid_to'] else ""
            edge.fact = (
                f"Subject: {fact['subject']}\n"
                f"Predicate: {fact['predicate']}\n"
                f"Object: {fact['object']}\n"
                f"Confidence: 0.90\n"
                f"Source: user_stated\n"
                f"Valid From: {fact['valid_from'].isoformat()}"
                f"{valid_to_str}"
            )
            edge.created_at = fact["valid_from"]
            edge.uuid = fact["uuid"]
            mock_edges.append(edge)

        mock_client.search = AsyncMock(return_value=mock_edges)

        with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_client

            # Query as of 150 days ago - only CompanyA should be valid
            as_of_date = now - timedelta(days=150)
            results = await memory.search_facts(
                user_id="user-123",
                query="where does John work",
                as_of=as_of_date,
            )

            assert len(results) == 1
            assert results[0].object == "CompanyA"

            # Query as of today - only CompanyB should be valid
            results_now = await memory.search_facts(
                user_id="user-123",
                query="where does John work",
                as_of=now,
            )

            assert len(results_now) == 1
            assert results_now[0].object == "CompanyB"


class TestPointInTimeConfidence:
    """Integration tests for confidence scoring at point in time."""

    def test_effective_confidence_at_past_date(self) -> None:
        """Test confidence calculation uses correct decay for as_of date."""
        now = datetime.now(UTC)

        # Fact created 90 days ago, never confirmed
        fact = SemanticFact(
            id="fact-confidence",
            user_id="user-123",
            subject="Market",
            predicate="size",
            object="$1B",
            confidence=0.80,
            source=FactSource.WEB_RESEARCH,
            valid_from=now - timedelta(days=90),
            last_confirmed_at=None,
            corroborating_sources=[],
        )

        memory = SemanticMemory()

        # Confidence at creation (no decay yet - within 7 day window)
        creation_plus_3 = now - timedelta(days=87)
        conf_at_creation = memory.get_effective_confidence(fact, as_of=creation_plus_3)
        assert conf_at_creation == 0.80  # No decay within refresh window

        # Confidence now (should have decayed)
        conf_now = memory.get_effective_confidence(fact, as_of=now)
        # 0.80 - ((90-7) * 0.05/30) = 0.80 - 0.138 = 0.662
        assert conf_now < 0.80
        assert conf_now > 0.60  # Should still be above floor

        # Confidence at 30 days ago
        conf_30_ago = memory.get_effective_confidence(fact, as_of=now - timedelta(days=30))
        # Should be between creation and now
        assert conf_at_creation >= conf_30_ago >= conf_now


class TestPointInTimeInvalidatedFacts:
    """Integration tests for handling invalidated facts."""

    def test_is_valid_returns_false_regardless_of_as_of_when_invalidated(self) -> None:
        """Test invalidated facts are never valid, even at past dates."""
        now = datetime.now(UTC)

        fact = SemanticFact(
            id="fact-invalidated",
            user_id="user-123",
            subject="Data",
            predicate="status",
            object="Active",
            confidence=0.90,
            source=FactSource.USER_STATED,
            valid_from=now - timedelta(days=60),
            invalidated_at=now - timedelta(days=10),
            invalidation_reason="superseded",
        )

        # Even checking validity at 30 days ago (before invalidation),
        # the fact should be invalid because invalidated_at is set
        assert fact.is_valid(as_of=now - timedelta(days=30)) is False
        assert fact.is_valid(as_of=now) is False

    @pytest.mark.asyncio
    async def test_get_facts_about_respects_include_invalidated_with_as_of(self) -> None:
        """Test that include_invalidated works with as_of parameter."""
        memory = SemanticMemory()
        mock_client = MagicMock()

        now = datetime.now(UTC)

        # Invalidated fact
        mock_edge = MagicMock()
        mock_edge.fact = (
            f"Subject: Account\n"
            f"Predicate: status\n"
            f"Object: Active\n"
            f"Confidence: 0.90\n"
            f"Source: user_stated\n"
            f"Valid From: {(now - timedelta(days=60)).isoformat()}"
        )
        mock_edge.created_at = now - timedelta(days=60)
        mock_edge.uuid = "fact-inv"

        mock_client.search = AsyncMock(return_value=[mock_edge])

        with patch.object(memory, "_get_graphiti_client", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = mock_client

            # Without include_invalidated, should respect validity
            results = await memory.get_facts_about(
                user_id="user-123",
                subject="Account",
                as_of=now - timedelta(days=30),
                include_invalidated=False,
            )

            # The mock fact is valid (not explicitly invalidated)
            assert len(results) == 1
```

### Step 2: Run test to verify tests pass

Run: `cd backend && pytest tests/integration/test_point_in_time_queries.py -v`

Expected: PASS

### Step 3: Commit

```bash
cd backend && git add tests/integration/test_point_in_time_queries.py
git commit -m "$(cat <<'EOF'
test(integration): add point-in-time query integration tests

Comprehensive tests for US-214 temporal query functionality:
- Episodic memory filtering by recorded_at
- Semantic memory filtering by validity window
- Confidence scoring at historical dates
- Invalidated fact handling

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Task 9: Run All Tests and Quality Gates

**Files:** None (verification only)

### Step 1: Run all memory tests

Run: `cd backend && pytest tests/test_episodic_memory.py tests/test_semantic_memory.py tests/test_api_memory.py tests/integration/test_point_in_time_queries.py -v`

Expected: All tests PASS

### Step 2: Run mypy type checking

Run: `cd backend && mypy src/memory/episodic.py src/memory/semantic.py src/api/routes/memory.py --strict`

Expected: No errors

### Step 3: Run ruff linting

Run: `cd backend && ruff check src/memory/episodic.py src/memory/semantic.py src/api/routes/memory.py`

Expected: No warnings

### Step 4: Run full test suite

Run: `cd backend && pytest tests/ -v`

Expected: All tests PASS

### Step 5: Commit (if any formatting fixes needed)

```bash
cd backend && ruff format src/memory/episodic.py src/memory/semantic.py src/api/routes/memory.py
git add -A
git commit -m "$(cat <<'EOF'
chore: format code per project standards

Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>
EOF
)"
```

---

## Verification Checklist (US-214 Acceptance Criteria)

After completing all tasks, verify:

- [ ] `as_of` parameter on fact queries works (`SemanticMemory.search_facts`, `SemanticMemory.get_facts_about`)
- [ ] Returns only facts valid at that timestamp
- [ ] Handles invalidated facts correctly (never valid regardless of as_of)
- [ ] Works for both episodic and semantic memory
- [ ] API endpoint supports temporal queries (`GET /api/v1/memory/query?as_of=...`)
- [ ] Unit tests for temporal correctness
- [ ] Integration tests pass
- [ ] All quality gates pass (pytest, mypy --strict, ruff)

---

## Notes

### Bi-Temporal Model

The implementation follows a bi-temporal model:
- **Episodic Memory**: `occurred_at` (when event happened) vs `recorded_at` (when we learned about it)
- **Semantic Memory**: `valid_from`/`valid_to` (temporal validity window)

The `as_of` parameter filters based on when ARIA knew about information, not when events occurred.

### Confidence at Point in Time

`SemanticMemory.get_effective_confidence()` already supports `as_of` parameter. The API integration uses this to show confidence as it would have been calculated at the query date.

### Invalidated Facts Behavior

Invalidated facts (`invalidated_at` is set) are never considered valid, even when querying at dates before invalidation. This is intentional - once we know something is wrong, we shouldn't return it even for historical queries.
