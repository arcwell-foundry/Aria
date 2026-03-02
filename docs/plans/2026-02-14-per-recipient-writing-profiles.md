# Per-Recipient Writing Style Profiles Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Extend the Digital Twin to store per-recipient writing style profiles derived from real sent email analysis during bootstrap.

**Architecture:** Add a `recipient_writing_profiles` table in Supabase to store per-contact style data. Extend `WritingAnalysisService` with a new `analyze_recipient_samples()` method that uses the LLM to analyze writing style per-recipient. Wire into email bootstrap after sent emails are fetched, grouping by recipient and analyzing the top 20 by frequency.

**Tech Stack:** Python 3.11+, FastAPI, Supabase (PostgreSQL), Pydantic, Claude LLM (via `LLMClient`), pytest

---

### Task 1: Create RecipientWritingProfile Pydantic Model

**Files:**
- Modify: `backend/src/onboarding/writing_analysis.py:26-67`

**Step 1: Write the failing test**

In `backend/tests/test_writing_analysis.py`, add after line 78 (end of `TestWritingStyleFingerprint`):

```python
from src.onboarding.writing_analysis import RecipientWritingProfile

class TestRecipientWritingProfile:
    """Tests for the RecipientWritingProfile Pydantic model."""

    def test_default_values(self):
        """Test that required fields must be provided and defaults work."""
        profile = RecipientWritingProfile(
            recipient_email="sarah@example.com",
        )
        assert profile.recipient_email == "sarah@example.com"
        assert profile.recipient_name is None
        assert profile.relationship_type == "unknown"
        assert profile.formality_level == 0.5
        assert profile.average_message_length == 0
        assert profile.greeting_style == ""
        assert profile.signoff_style == ""
        assert profile.tone == "balanced"
        assert profile.uses_emoji is False
        assert profile.email_count == 0
        assert profile.last_email_date is None

    def test_round_trip_serialization(self):
        """Test model_dump and reconstruction preserve all fields."""
        profile = RecipientWritingProfile(
            recipient_email="dr.fischer@novartis.com",
            recipient_name="Dr. Fischer",
            relationship_type="external_executive",
            formality_level=0.9,
            average_message_length=185,
            greeting_style="Dear Dr. Fischer,",
            signoff_style="Regards,",
            tone="formal",
            uses_emoji=False,
            email_count=12,
            last_email_date="2026-02-10T14:30:00+00:00",
        )
        data = profile.model_dump()
        restored = RecipientWritingProfile(**data)
        assert restored == profile

    def test_partial_construction(self):
        """Test creating profile with minimal fields."""
        profile = RecipientWritingProfile(
            recipient_email="team@internal.com",
            tone="casual",
            email_count=5,
        )
        assert profile.tone == "casual"
        assert profile.email_count == 5
        assert profile.formality_level == 0.5  # default
```

**Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_writing_analysis.py::TestRecipientWritingProfile -v`
Expected: FAIL with `ImportError: cannot import name 'RecipientWritingProfile'`

**Step 3: Write minimal implementation**

In `backend/src/onboarding/writing_analysis.py`, add after `WritingStyleFingerprint` class (after line 66):

```python
class RecipientWritingProfile(BaseModel):
    """Per-recipient writing style profile.

    Captures how the user adapts their writing style for a specific
    recipient, enabling ARIA to match tone per-contact.
    """

    recipient_email: str
    recipient_name: str | None = None
    relationship_type: str = "unknown"  # internal_team, external_executive, external_peer, vendor, new_contact
    formality_level: float = 0.5  # 0=very casual, 1=very formal
    average_message_length: int = 0  # words
    greeting_style: str = ""  # e.g., "Hi Sarah,", "Dear Dr. Fischer,"
    signoff_style: str = ""  # e.g., "Best,", "Thanks,", "Regards,"
    tone: str = "balanced"  # warm, direct, formal, casual, balanced
    uses_emoji: bool = False
    email_count: int = 0
    last_email_date: str | None = None  # ISO datetime string
```

**Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_writing_analysis.py::TestRecipientWritingProfile -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/src/onboarding/writing_analysis.py backend/tests/test_writing_analysis.py
git commit -m "feat: add RecipientWritingProfile model for per-contact style data"
```

---

### Task 2: Create Database Migration for recipient_writing_profiles Table

**Files:**
- Create: `backend/supabase/migrations/20260214000000_recipient_writing_profiles.sql`

**Step 1: Write the migration**

```sql
-- ============================================================
-- recipient_writing_profiles
-- Per-recipient writing style profiles for Digital Twin.
-- Stores how a user adapts writing style per contact.
-- ============================================================
CREATE TABLE IF NOT EXISTS recipient_writing_profiles (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    recipient_email         TEXT NOT NULL,
    recipient_name          TEXT,
    relationship_type       TEXT DEFAULT 'unknown'
                            CHECK (relationship_type IN (
                                'internal_team', 'external_executive', 'external_peer',
                                'vendor', 'new_contact', 'unknown'
                            )),
    formality_level         FLOAT DEFAULT 0.5,
    average_message_length  INTEGER DEFAULT 0,
    greeting_style          TEXT DEFAULT '',
    signoff_style           TEXT DEFAULT '',
    tone                    TEXT DEFAULT 'balanced'
                            CHECK (tone IN ('warm', 'direct', 'formal', 'casual', 'balanced')),
    uses_emoji              BOOLEAN DEFAULT FALSE,
    email_count             INTEGER DEFAULT 0,
    last_email_date         TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, recipient_email)
);

ALTER TABLE recipient_writing_profiles ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'recipient_writing_profiles'
        AND policyname = 'recipient_writing_profiles_user_own'
    ) THEN
        CREATE POLICY recipient_writing_profiles_user_own
            ON recipient_writing_profiles FOR ALL TO authenticated
            USING (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'recipient_writing_profiles'
        AND policyname = 'recipient_writing_profiles_service_role'
    ) THEN
        CREATE POLICY recipient_writing_profiles_service_role
            ON recipient_writing_profiles FOR ALL TO service_role
            USING (true);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_recipient_writing_profiles_user
    ON recipient_writing_profiles(user_id);

CREATE INDEX IF NOT EXISTS idx_recipient_writing_profiles_user_recipient
    ON recipient_writing_profiles(user_id, recipient_email);

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'update_recipient_writing_profiles_updated_at'
    ) THEN
        CREATE TRIGGER update_recipient_writing_profiles_updated_at
            BEFORE UPDATE ON recipient_writing_profiles
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;
```

**Step 2: Commit**

```bash
git add backend/supabase/migrations/20260214000000_recipient_writing_profiles.sql
git commit -m "feat: add recipient_writing_profiles migration for per-contact style data"
```

---

### Task 3: Implement analyze_recipient_samples() in WritingAnalysisService

**Files:**
- Modify: `backend/src/onboarding/writing_analysis.py:104-334`
- Test: `backend/tests/test_writing_analysis.py`

**Step 1: Write the failing tests**

Add to `backend/tests/test_writing_analysis.py`:

```python
class TestRecipientStyleAnalysis:
    """Tests for WritingAnalysisService.analyze_recipient_samples."""

    @pytest.mark.asyncio
    async def test_empty_email_list_returns_empty(self):
        """No emails produces no recipient profiles."""
        service, _, mock_db = _make_service_with_mocks()
        result = await service.analyze_recipient_samples("user-123", [])
        assert result == []

    @pytest.mark.asyncio
    async def test_groups_emails_by_recipient(self):
        """Emails are grouped by recipient before analysis."""
        service, mock_llm, mock_db = _make_service_with_mocks()

        # Build LLM response for recipient analysis
        recipient_response = json.dumps([
            {
                "recipient_email": "sarah@team.com",
                "recipient_name": "Sarah",
                "relationship_type": "internal_team",
                "formality_level": 0.3,
                "average_message_length": 45,
                "greeting_style": "Hey Sarah,",
                "signoff_style": "Thanks,",
                "tone": "casual",
                "uses_emoji": True,
            },
            {
                "recipient_email": "dr.fischer@novartis.com",
                "recipient_name": "Dr. Fischer",
                "relationship_type": "external_executive",
                "formality_level": 0.9,
                "average_message_length": 180,
                "greeting_style": "Dear Dr. Fischer,",
                "signoff_style": "Regards,",
                "tone": "formal",
                "uses_emoji": False,
            },
        ])
        mock_llm.generate_response = AsyncMock(return_value=recipient_response)

        emails = [
            {"to": ["sarah@team.com"], "body": "Hey Sarah, quick sync?", "date": "2026-02-10T10:00:00Z", "subject": "sync"},
            {"to": ["sarah@team.com"], "body": "Hey Sarah, done with the deck!", "date": "2026-02-11T10:00:00Z", "subject": "deck"},
            {"to": ["sarah@team.com"], "body": "Hey Sarah, see you at standup", "date": "2026-02-12T10:00:00Z", "subject": "standup"},
            {"to": ["dr.fischer@novartis.com"], "body": "Dear Dr. Fischer, Regarding our partnership...", "date": "2026-02-10T14:00:00Z", "subject": "partnership"},
            {"to": ["dr.fischer@novartis.com"], "body": "Dear Dr. Fischer, Please find attached...", "date": "2026-02-11T14:00:00Z", "subject": "attachment"},
        ]

        with patch("src.onboarding.writing_analysis.SupabaseClient") as mock_supa:
            mock_supa.get_client.return_value = mock_db
            profiles = await service.analyze_recipient_samples("user-123", emails)

        assert len(profiles) == 2
        # LLM was called to analyze recipients
        mock_llm.generate_response.assert_called_once()

    @pytest.mark.asyncio
    async def test_top_20_recipients_only(self):
        """Only top 20 recipients by email count are analyzed."""
        service, mock_llm, mock_db = _make_service_with_mocks()

        # Create 25 recipients, each with varying email counts
        emails = []
        for i in range(25):
            count = 25 - i  # First recipient has most emails
            for j in range(count):
                emails.append({
                    "to": [f"user{i}@example.com"],
                    "body": f"Hello user {i}, message {j}",
                    "date": f"2026-02-{10 + (j % 5):02d}T10:00:00Z",
                    "subject": f"msg {j}",
                })

        mock_llm.generate_response = AsyncMock(return_value="[]")

        with patch("src.onboarding.writing_analysis.SupabaseClient") as mock_supa:
            mock_supa.get_client.return_value = mock_db
            await service.analyze_recipient_samples("user-123", emails)

        # Verify LLM prompt only includes 20 recipients
        call_args = mock_llm.generate_response.call_args
        prompt_text = call_args[1]["messages"][0]["content"]
        # user24 has only 1 email, should be excluded (25th recipient)
        assert "user0@example.com" in prompt_text
        assert "user19@example.com" in prompt_text
        assert "user20@example.com" not in prompt_text

    @pytest.mark.asyncio
    async def test_profiles_stored_in_database(self):
        """Analyzed profiles are upserted into recipient_writing_profiles table."""
        service, mock_llm, mock_db = _make_service_with_mocks()

        recipient_response = json.dumps([
            {
                "recipient_email": "sarah@team.com",
                "recipient_name": "Sarah",
                "relationship_type": "internal_team",
                "formality_level": 0.3,
                "average_message_length": 45,
                "greeting_style": "Hey Sarah,",
                "signoff_style": "Thanks,",
                "tone": "casual",
                "uses_emoji": True,
            },
        ])
        mock_llm.generate_response = AsyncMock(return_value=recipient_response)

        # Set up upsert mock
        mock_upsert = MagicMock()
        mock_upsert.execute.return_value = MagicMock(data=[{}])
        mock_db.table.return_value.upsert.return_value = mock_upsert

        emails = [
            {"to": ["sarah@team.com"], "body": "Hey Sarah, quick note", "date": "2026-02-10T10:00:00Z", "subject": "note"},
            {"to": ["sarah@team.com"], "body": "Hey Sarah, see you!", "date": "2026-02-11T10:00:00Z", "subject": "bye"},
        ]

        with patch("src.onboarding.writing_analysis.SupabaseClient") as mock_supa:
            mock_supa.get_client.return_value = mock_db
            await service.analyze_recipient_samples("user-123", emails)

        # Verify upsert was called on the right table
        mock_db.table.assert_any_call("recipient_writing_profiles")

    @pytest.mark.asyncio
    async def test_llm_failure_returns_empty(self):
        """LLM returning invalid JSON produces empty results."""
        service, mock_llm, mock_db = _make_service_with_mocks()
        mock_llm.generate_response = AsyncMock(return_value="not json")

        emails = [
            {"to": ["a@b.com"], "body": "Hello there", "date": "2026-02-10T10:00:00Z", "subject": "hi"},
            {"to": ["a@b.com"], "body": "How are you", "date": "2026-02-11T10:00:00Z", "subject": "check"},
        ]

        with patch("src.onboarding.writing_analysis.SupabaseClient") as mock_supa:
            mock_supa.get_client.return_value = mock_db
            profiles = await service.analyze_recipient_samples("user-123", emails)

        assert profiles == []
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_writing_analysis.py::TestRecipientStyleAnalysis -v`
Expected: FAIL with `AttributeError: 'WritingAnalysisService' has no attribute 'analyze_recipient_samples'`

**Step 3: Write the implementation**

Add the LLM prompt constant after `_ANALYSIS_PROMPT` (after line 101) in `writing_analysis.py`:

```python
_RECIPIENT_ANALYSIS_PROMPT = """Analyze how this person writes to different recipients.
Below are groups of sent emails, organized by recipient. For each recipient, analyze the
writing style the sender uses SPECIFICALLY with that person.

{recipient_groups}

For each recipient, return a JSON array with objects containing:
[
  {{
    "recipient_email": "<email address>",
    "recipient_name": "<inferred name or null>",
    "relationship_type": "<internal_team|external_executive|external_peer|vendor|new_contact>",
    "formality_level": <float 0-1: 0=very casual, 1=very formal>,
    "average_message_length": <int: average words per email to this person>,
    "greeting_style": "<exact greeting pattern used, e.g. 'Hi Sarah,' or 'Dear Dr. Fischer,'>",
    "signoff_style": "<exact sign-off pattern used, e.g. 'Best,' or 'Thanks,'>",
    "tone": "<warm|direct|formal|casual|balanced>",
    "uses_emoji": <bool: whether emojis appear in messages to this person>
  }}
]

IMPORTANT:
- Base analysis on ACTUAL patterns in the emails, not assumptions
- relationship_type should be inferred from email domain, greeting formality, and content
- greeting_style and signoff_style should reflect what the sender ACTUALLY writes
- Return ONLY the JSON array, no other text"""
```

Add the method to `WritingAnalysisService` class (after `get_fingerprint`, after line 333):

```python
    async def analyze_recipient_samples(
        self,
        user_id: str,
        sent_emails: list[dict[str, Any]],
    ) -> list[RecipientWritingProfile]:
        """Analyze sent emails grouped by recipient to build per-contact profiles.

        Groups emails by primary recipient, takes the top 20 by frequency,
        and uses LLM to analyze writing style differences per recipient.

        Args:
            user_id: The user whose emails to analyze.
            sent_emails: List of email dicts with 'to', 'body', 'date', 'subject'.

        Returns:
            List of RecipientWritingProfile for analyzed recipients.
        """
        if not sent_emails:
            return []

        # Group emails by primary recipient
        recipient_emails: dict[str, list[dict[str, Any]]] = {}
        for email in sent_emails:
            recipients = email.get("to", [])
            if not recipients:
                continue
            # Use first recipient as primary
            primary = recipients[0] if isinstance(recipients[0], str) else recipients[0].get("email", "")
            primary = primary.lower().strip()
            if not primary:
                continue
            if primary not in recipient_emails:
                recipient_emails[primary] = []
            recipient_emails[primary].append(email)

        if not recipient_emails:
            return []

        # Sort by email count descending, take top 20
        sorted_recipients = sorted(
            recipient_emails.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        )[:20]

        # Build prompt with grouped samples
        groups: list[str] = []
        recipient_counts: dict[str, int] = {}
        recipient_last_dates: dict[str, str] = {}

        for recipient, emails in sorted_recipients:
            recipient_counts[recipient] = len(emails)
            # Track last email date
            dates = [e.get("date", "") for e in emails if e.get("date")]
            if dates:
                recipient_last_dates[recipient] = max(dates)

            # Include up to 5 sample bodies per recipient (cap at 500 chars each)
            sample_bodies = []
            for e in emails[:5]:
                body = e.get("body", "")[:500]
                if body:
                    sample_bodies.append(body)

            if sample_bodies:
                group_text = (
                    f"--- RECIPIENT: {recipient} ({len(emails)} emails) ---\n"
                    + "\n\n".join(sample_bodies)
                )
                groups.append(group_text)

        if not groups:
            return []

        prompt = _RECIPIENT_ANALYSIS_PROMPT.format(
            recipient_groups="\n\n".join(groups)
        )

        # Call LLM
        try:
            response = await self.llm.generate_response(
                messages=[{"role": "user", "content": prompt}],
                max_tokens=4000,
                temperature=0.3,
            )

            # Strip markdown fences
            text = response.strip()
            if text.startswith("```"):
                first_newline = text.index("\n")
                text = text[first_newline + 1:]
            if text.endswith("```"):
                text = text[:-3].rstrip()

            raw_profiles: list[dict[str, Any]] = json.loads(text)
        except Exception as e:
            logger.warning("Recipient style analysis failed: %s", e)
            return []

        # Build profiles and store
        profiles: list[RecipientWritingProfile] = []
        for raw in raw_profiles:
            email_addr = raw.get("recipient_email", "").lower().strip()
            if not email_addr:
                continue

            profile = RecipientWritingProfile(
                recipient_email=email_addr,
                recipient_name=raw.get("recipient_name"),
                relationship_type=raw.get("relationship_type", "unknown"),
                formality_level=float(raw.get("formality_level", 0.5)),
                average_message_length=int(raw.get("average_message_length", 0)),
                greeting_style=raw.get("greeting_style", ""),
                signoff_style=raw.get("signoff_style", ""),
                tone=raw.get("tone", "balanced"),
                uses_emoji=bool(raw.get("uses_emoji", False)),
                email_count=recipient_counts.get(email_addr, 0),
                last_email_date=recipient_last_dates.get(email_addr),
            )
            profiles.append(profile)

        # Store profiles in database
        await self._store_recipient_profiles(user_id, profiles)

        return profiles

    async def _store_recipient_profiles(
        self,
        user_id: str,
        profiles: list[RecipientWritingProfile],
    ) -> None:
        """Store recipient writing profiles in database.

        Uses upsert with (user_id, recipient_email) as conflict key.

        Args:
            user_id: The user who owns these profiles.
            profiles: List of profiles to store.
        """
        if not profiles:
            return

        try:
            db = SupabaseClient.get_client()

            for profile in profiles:
                row = {
                    "user_id": user_id,
                    "recipient_email": profile.recipient_email,
                    "recipient_name": profile.recipient_name,
                    "relationship_type": profile.relationship_type,
                    "formality_level": profile.formality_level,
                    "average_message_length": profile.average_message_length,
                    "greeting_style": profile.greeting_style,
                    "signoff_style": profile.signoff_style,
                    "tone": profile.tone,
                    "uses_emoji": profile.uses_emoji,
                    "email_count": profile.email_count,
                    "last_email_date": profile.last_email_date,
                }
                db.table("recipient_writing_profiles").upsert(
                    row,
                    on_conflict="user_id,recipient_email",
                ).execute()

        except Exception as e:
            logger.warning("Failed to store recipient profiles: %s", e)
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_writing_analysis.py::TestRecipientStyleAnalysis -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add backend/src/onboarding/writing_analysis.py backend/tests/test_writing_analysis.py
git commit -m "feat: implement per-recipient writing style analysis via LLM"
```

---

### Task 4: Add get_recipient_style() to WritingAnalysisService

**Files:**
- Modify: `backend/src/onboarding/writing_analysis.py`
- Test: `backend/tests/test_writing_analysis.py`

**Step 1: Write the failing tests**

Add to `backend/tests/test_writing_analysis.py`:

```python
class TestGetRecipientStyle:
    """Tests for WritingAnalysisService.get_recipient_style."""

    @pytest.mark.asyncio
    async def test_returns_profile_when_found(self):
        """Returns recipient-specific profile from database."""
        service = WritingAnalysisService.__new__(WritingAnalysisService)

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.eq = MagicMock(return_value=mock_query)
        mock_query.maybe_single.return_value = mock_query
        mock_query.execute.return_value = MagicMock(data={
            "recipient_email": "sarah@team.com",
            "recipient_name": "Sarah",
            "relationship_type": "internal_team",
            "formality_level": 0.3,
            "average_message_length": 45,
            "greeting_style": "Hey Sarah,",
            "signoff_style": "Thanks,",
            "tone": "casual",
            "uses_emoji": True,
            "email_count": 15,
            "last_email_date": "2026-02-10T10:00:00+00:00",
        })
        mock_db.table.return_value.select.return_value = mock_query

        with patch("src.onboarding.writing_analysis.SupabaseClient") as mock_supa:
            mock_supa.get_client.return_value = mock_db
            result = await service.get_recipient_style("user-123", "sarah@team.com")

        assert result is not None
        profile, is_recipient_specific = result
        assert is_recipient_specific is True
        assert profile.recipient_email == "sarah@team.com"
        assert profile.tone == "casual"
        assert profile.formality_level == 0.3

    @pytest.mark.asyncio
    async def test_returns_global_fallback_when_not_found(self):
        """Returns global style as fallback when no recipient profile exists."""
        service = WritingAnalysisService.__new__(WritingAnalysisService)
        service.llm = AsyncMock()
        service.episodic = AsyncMock()

        mock_db = MagicMock()
        # Recipient query returns None
        mock_query_recipient = MagicMock()
        mock_query_recipient.eq = MagicMock(return_value=mock_query_recipient)
        mock_query_recipient.maybe_single.return_value = mock_query_recipient
        mock_query_recipient.execute.return_value = MagicMock(data=None)

        # Global fingerprint query returns data
        mock_query_global = MagicMock()
        mock_query_global.eq = MagicMock(return_value=mock_query_global)
        mock_query_global.maybe_single.return_value = mock_query_global
        mock_query_global.execute.return_value = MagicMock(data={
            "preferences": {
                "digital_twin": {
                    "writing_style": {
                        "formality_index": 0.6,
                        "opening_style": "Hi,",
                        "closing_style": "Best,",
                        "warmth": 0.5,
                        "emoji_usage": "never",
                        "confidence": 0.8,
                    }
                }
            }
        })

        def table_side_effect(name):
            mock_table = MagicMock()
            if name == "recipient_writing_profiles":
                mock_table.select.return_value = mock_query_recipient
            else:
                mock_table.select.return_value = mock_query_global
            return mock_table

        mock_db.table = MagicMock(side_effect=table_side_effect)

        with patch("src.onboarding.writing_analysis.SupabaseClient") as mock_supa:
            mock_supa.get_client.return_value = mock_db
            result = await service.get_recipient_style("user-123", "unknown@newcontact.com")

        assert result is not None
        profile, is_recipient_specific = result
        assert is_recipient_specific is False
        assert profile.formality_level == 0.6
        assert profile.greeting_style == "Hi,"

    @pytest.mark.asyncio
    async def test_returns_none_when_no_data_at_all(self):
        """Returns None when neither recipient nor global profile exists."""
        service = WritingAnalysisService.__new__(WritingAnalysisService)
        service.llm = AsyncMock()
        service.episodic = AsyncMock()

        mock_db = MagicMock()
        mock_query = MagicMock()
        mock_query.eq = MagicMock(return_value=mock_query)
        mock_query.maybe_single.return_value = mock_query
        mock_query.execute.return_value = MagicMock(data=None)
        mock_db.table.return_value.select.return_value = mock_query

        with patch("src.onboarding.writing_analysis.SupabaseClient") as mock_supa:
            mock_supa.get_client.return_value = mock_db
            result = await service.get_recipient_style("user-123", "nobody@nowhere.com")

        assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_writing_analysis.py::TestGetRecipientStyle -v`
Expected: FAIL with `AttributeError: 'WritingAnalysisService' has no attribute 'get_recipient_style'`

**Step 3: Write the implementation**

Add to `WritingAnalysisService` class in `writing_analysis.py`:

```python
    async def get_recipient_style(
        self,
        user_id: str,
        recipient_email: str,
    ) -> tuple[RecipientWritingProfile, bool] | None:
        """Get writing style adapted for a specific recipient.

        Looks up per-recipient profile first. If not found, falls back
        to global WritingStyleFingerprint converted to a RecipientWritingProfile.

        Args:
            user_id: The user whose style to look up.
            recipient_email: The recipient to get style for.

        Returns:
            Tuple of (RecipientWritingProfile, is_recipient_specific) or None
            if no style data exists at all. is_recipient_specific is True when
            a per-recipient profile was found, False when falling back to global.
        """
        try:
            db = SupabaseClient.get_client()

            # Try recipient-specific profile first
            result = (
                db.table("recipient_writing_profiles")
                .select("*")
                .eq("user_id", user_id)
                .eq("recipient_email", recipient_email.lower().strip())
                .maybe_single()
                .execute()
            )

            if result and result.data:
                data = cast(dict[str, Any], result.data)
                profile = RecipientWritingProfile(
                    recipient_email=data.get("recipient_email", recipient_email),
                    recipient_name=data.get("recipient_name"),
                    relationship_type=data.get("relationship_type", "unknown"),
                    formality_level=float(data.get("formality_level", 0.5)),
                    average_message_length=int(data.get("average_message_length", 0)),
                    greeting_style=data.get("greeting_style", ""),
                    signoff_style=data.get("signoff_style", ""),
                    tone=data.get("tone", "balanced"),
                    uses_emoji=bool(data.get("uses_emoji", False)),
                    email_count=int(data.get("email_count", 0)),
                    last_email_date=data.get("last_email_date"),
                )
                return profile, True

            # Fall back to global fingerprint
            global_fp = await self.get_fingerprint(user_id)
            if global_fp:
                # Convert global fingerprint to a RecipientWritingProfile
                profile = RecipientWritingProfile(
                    recipient_email=recipient_email,
                    relationship_type="new_contact",
                    formality_level=global_fp.formality_index,
                    greeting_style=global_fp.opening_style,
                    signoff_style=global_fp.closing_style,
                    tone=self._map_tone_from_fingerprint(global_fp),
                    uses_emoji=global_fp.emoji_usage != "never",
                )
                return profile, False

        except Exception as e:
            logger.warning("Failed to get recipient style: %s", e)

        return None

    @staticmethod
    def _map_tone_from_fingerprint(fp: WritingStyleFingerprint) -> str:
        """Map global fingerprint tone metrics to a single tone label.

        Args:
            fp: The global writing style fingerprint.

        Returns:
            One of: warm, direct, formal, casual, balanced.
        """
        if fp.formality_index >= 0.7:
            return "formal"
        if fp.warmth >= 0.7:
            return "warm"
        if fp.directness >= 0.7:
            return "direct"
        if fp.formality_index <= 0.3:
            return "casual"
        return "balanced"
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_writing_analysis.py::TestGetRecipientStyle -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add backend/src/onboarding/writing_analysis.py backend/tests/test_writing_analysis.py
git commit -m "feat: add get_recipient_style() with global fallback"
```

---

### Task 5: Wire Recipient Analysis into Email Bootstrap

**Files:**
- Modify: `backend/src/onboarding/email_bootstrap.py:242-243`
- Test: `backend/tests/test_email_bootstrap_recipients.py` (create)

**Step 1: Write the failing test**

Create `backend/tests/test_email_bootstrap_recipients.py`:

```python
"""Tests for per-recipient style analysis in email bootstrap."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestEmailBootstrapRecipientProfiles:
    """Tests for recipient profile building during bootstrap."""

    @pytest.mark.asyncio
    async def test_bootstrap_calls_recipient_analysis(self):
        """Bootstrap calls analyze_recipient_samples after fetching emails."""
        from src.onboarding.email_bootstrap import PriorityEmailIngestion

        service = PriorityEmailIngestion.__new__(PriorityEmailIngestion)
        service._db = MagicMock()
        service._llm = AsyncMock()

        emails = [
            {
                "to": ["sarah@team.com"],
                "cc": [],
                "body": "Hey Sarah, quick sync?",
                "date": "2026-02-10T10:00:00Z",
                "subject": "sync",
                "thread_id": "t1",
            },
            {
                "to": ["boss@client.com"],
                "cc": [],
                "body": "Dear Mr. Smith, Following up on our discussion...",
                "date": "2026-02-10T14:00:00Z",
                "subject": "follow up",
                "thread_id": "t2",
            },
        ]

        # Mock all bootstrap methods to isolate recipient analysis
        service._load_exclusions = AsyncMock(return_value=[])
        service._fetch_sent_emails = AsyncMock(return_value=emails)
        service._apply_exclusions = MagicMock(return_value=emails)
        service._extract_contacts = AsyncMock(return_value=[])
        service._identify_active_threads = AsyncMock(return_value=[])
        service._detect_commitments = AsyncMock(return_value=[])
        service._extract_writing_samples = MagicMock(return_value=[])
        service._analyze_patterns = MagicMock(
            return_value=MagicMock(model_dump=MagicMock(return_value={}))
        )
        service._store_contacts = AsyncMock()
        service._store_threads = AsyncMock()
        service._store_commitments = AsyncMock()
        service._refine_writing_style = AsyncMock()
        service._store_patterns = AsyncMock()
        service._build_recipient_profiles = AsyncMock()
        service._update_readiness = AsyncMock()
        service._record_episodic = AsyncMock()
        service._trigger_retroactive_enrichment = AsyncMock()

        with patch("src.onboarding.email_bootstrap.ActivityService", autospec=True):
            result = await service.run_bootstrap("user-123")

        # Verify recipient profile building was called with the emails
        service._build_recipient_profiles.assert_called_once_with("user-123", emails)

    @pytest.mark.asyncio
    async def test_build_recipient_profiles_delegates_to_writing_analysis(self):
        """_build_recipient_profiles calls WritingAnalysisService."""
        from src.onboarding.email_bootstrap import PriorityEmailIngestion

        service = PriorityEmailIngestion.__new__(PriorityEmailIngestion)
        service._db = MagicMock()
        service._llm = AsyncMock()

        emails = [
            {"to": ["a@b.com"], "body": "Hello", "date": "2026-02-10T10:00:00Z", "subject": "hi"},
        ]

        mock_analysis = AsyncMock()
        mock_analysis.analyze_recipient_samples = AsyncMock(return_value=[])

        with patch(
            "src.onboarding.email_bootstrap.WritingAnalysisService",
            return_value=mock_analysis,
        ):
            await service._build_recipient_profiles("user-123", emails)

        mock_analysis.analyze_recipient_samples.assert_called_once_with("user-123", emails)

    @pytest.mark.asyncio
    async def test_build_recipient_profiles_handles_failure_gracefully(self):
        """Failure in recipient analysis doesn't crash bootstrap."""
        from src.onboarding.email_bootstrap import PriorityEmailIngestion

        service = PriorityEmailIngestion.__new__(PriorityEmailIngestion)
        service._db = MagicMock()
        service._llm = AsyncMock()

        with patch(
            "src.onboarding.email_bootstrap.WritingAnalysisService",
            side_effect=Exception("LLM down"),
        ):
            # Should not raise
            await service._build_recipient_profiles("user-123", [{"to": ["a@b.com"], "body": "hi"}])
```

**Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_email_bootstrap_recipients.py -v`
Expected: FAIL with `AttributeError: 'PriorityEmailIngestion' has no attribute '_build_recipient_profiles'`

**Step 3: Write the implementation**

In `backend/src/onboarding/email_bootstrap.py`, add the `_build_recipient_profiles` method after `_refine_writing_style` (after line 871):

```python
    async def _build_recipient_profiles(self, user_id: str, emails: list[dict[str, Any]]) -> None:
        """Build per-recipient writing style profiles from sent emails.

        Args:
            user_id: User whose profiles to build.
            emails: Sent email dicts with 'to', 'body', 'date', 'subject'.
        """
        if not emails:
            return
        try:
            from src.onboarding.writing_analysis import WritingAnalysisService

            service = WritingAnalysisService()
            profiles = await service.analyze_recipient_samples(user_id, emails)
            logger.info(
                "EMAIL_BOOTSTRAP: Built %d recipient writing profiles for user %s",
                len(profiles),
                user_id,
            )
        except Exception as e:
            logger.warning("Recipient profile building failed: %s", e)
```

Then wire it into `run_bootstrap` — add the call after `_refine_writing_style` (after line 242). Insert after line 243 (`await self._store_patterns(...)`):

```python
            await self._build_recipient_profiles(user_id, emails)
```

The updated section (lines ~239-245) should read:

```python
            await self._store_contacts(user_id, contacts)
            await self._store_threads(user_id, threads)
            await self._store_commitments(user_id, commitments)
            await self._refine_writing_style(user_id, writing_samples)
            await self._store_patterns(user_id, result.communication_patterns)
            await self._build_recipient_profiles(user_id, emails)
            logger.info("EMAIL_BOOTSTRAP: All results stored for user %s", user_id)
```

**Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_email_bootstrap_recipients.py -v`
Expected: PASS (3 tests)

**Step 5: Run all writing analysis tests**

Run: `cd backend && python -m pytest tests/test_writing_analysis.py tests/test_email_bootstrap_recipients.py -v`
Expected: ALL PASS

**Step 6: Commit**

```bash
git add backend/src/onboarding/email_bootstrap.py backend/tests/test_email_bootstrap_recipients.py
git commit -m "feat: wire per-recipient style analysis into email bootstrap"
```

---

### Task 6: Run Full Test Suite and Verify

**Step 1: Run all related tests**

Run: `cd backend && python -m pytest tests/test_writing_analysis.py tests/test_email_bootstrap_recipients.py -v --tb=short`
Expected: ALL PASS

**Step 2: Run type checking**

Run: `cd backend && python -m mypy src/onboarding/writing_analysis.py src/onboarding/email_bootstrap.py --ignore-missing-imports`
Expected: No errors (or only pre-existing ones)

**Step 3: Run linting**

Run: `cd backend && ruff check src/onboarding/writing_analysis.py src/onboarding/email_bootstrap.py`
Expected: No errors

**Step 4: Fix any issues found**

Address any linting or type errors.

**Step 5: Final commit if fixes needed**

```bash
git add -u
git commit -m "fix: address lint and type issues in recipient profiles"
```

---

## File Summary

| File | Action | Purpose |
|------|--------|---------|
| `backend/src/onboarding/writing_analysis.py` | Modify | Add `RecipientWritingProfile` model, `analyze_recipient_samples()`, `get_recipient_style()`, `_store_recipient_profiles()`, `_map_tone_from_fingerprint()` |
| `backend/src/onboarding/email_bootstrap.py` | Modify | Add `_build_recipient_profiles()` method, wire into `run_bootstrap()` |
| `backend/supabase/migrations/20260214000000_recipient_writing_profiles.sql` | Create | Database table for per-recipient profiles |
| `backend/tests/test_writing_analysis.py` | Modify | Add tests for `RecipientWritingProfile`, `TestRecipientStyleAnalysis`, `TestGetRecipientStyle` |
| `backend/tests/test_email_bootstrap_recipients.py` | Create | Tests for bootstrap integration |

## Architecture Notes

- **Storage:** New `recipient_writing_profiles` table (not JSONB in user_settings) because per-recipient data is relational, queryable, and grows with contacts. The unique constraint on `(user_id, recipient_email)` prevents duplicates.
- **LLM Analysis:** One LLM call analyzes all 20 recipients together (batched), not 20 separate calls. This is cost-efficient and lets the LLM compare styles across recipients.
- **Fallback:** `get_recipient_style()` returns global fingerprint converted to `RecipientWritingProfile` format when no recipient-specific data exists, with a boolean flag indicating whether it's recipient-specific.
- **Error Handling:** All new code follows the existing pattern of catching exceptions and logging warnings without crashing the bootstrap pipeline.
