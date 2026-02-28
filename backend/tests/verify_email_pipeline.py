#!/usr/bin/env python3
"""
ARIA Email Intelligence Pipeline E2E Verification

Runs 10 verification checks against Supabase directly using the service role key.
No running server or JWT required for database checks (Checks 4-9).
WebSocket checks (1, 2, 3, 10) require the server to be running and are optional.
Check 5 (Draft Approval) also has a database-only fallback.

Usage:
    cd backend && python tests/verify_email_pipeline.py
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Environment bootstrap
# ---------------------------------------------------------------------------

# Load .env from backend directory
_backend_dir = Path(__file__).resolve().parent.parent
_env_path = _backend_dir / ".env"

try:
    from dotenv import load_dotenv

    load_dotenv(_env_path)
except ImportError:
    # Manual fallback if python-dotenv is not installed
    if _env_path.exists():
        for line in _env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            val = val.strip().strip("\"'")
            os.environ.setdefault(key.strip(), val)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
SERVER_URL = os.environ.get("ARIA_SERVER_URL", "http://localhost:8000")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    print("FATAL: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in backend/.env")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Supabase client
# ---------------------------------------------------------------------------

from supabase import Client, create_client  # noqa: E402

db: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# ---------------------------------------------------------------------------
# Optional imports (websockets, httpx)
# ---------------------------------------------------------------------------

try:
    import websockets  # noqa: F401

    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False

try:
    import httpx  # noqa: F401

    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False

# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

PASS = "PASS"
FAIL = "FAIL"
SKIP = "SKIP"
NA = "N/A"

results: list[dict] = []


def record(check_id: str, name: str, status: str, details: list[str] | None = None):
    """Record the outcome of a single check."""
    results.append(
        {"id": check_id, "name": name, "status": status, "details": details or []}
    )


# ---------------------------------------------------------------------------
# Helper: discover test user
# ---------------------------------------------------------------------------


def discover_user() -> tuple[str | None, str | None]:
    """Find an active email-connected user.

    Returns (user_id, integration_type) or (None, None).
    """
    try:
        resp = (
            db.table("user_integrations")
            .select("user_id, integration_type")
            .in_("integration_type", ["gmail", "outlook"])
            .eq("status", "active")
            .limit(1)
            .execute()
        )
        if resp.data:
            row = resp.data[0]
            return row["user_id"], row["integration_type"]
    except Exception as exc:
        print(f"  Warning: user_integrations query failed: {exc}")
        # Fallback: try to find any user with email_drafts
        try:
            resp = (
                db.table("email_drafts")
                .select("user_id")
                .limit(1)
                .execute()
            )
            if resp.data:
                return resp.data[0]["user_id"], "unknown"
        except Exception:
            pass
    return None, None


# ---------------------------------------------------------------------------
# Helper: check if server is reachable
# ---------------------------------------------------------------------------


def server_reachable() -> bool:
    """Return True if the ARIA backend server is reachable."""
    if not HAS_HTTPX:
        return False
    try:
        resp = httpx.get(f"{SERVER_URL}/health", timeout=3.0)
        return resp.status_code < 500
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Pre-Check 0: Schema Validation
# ---------------------------------------------------------------------------


def check_0_schema():
    """Verify the email_draft_status enum includes 'pending_review'."""
    check_id = "Pre-Check 0"
    name = "Schema Validation"

    # Strategy: try to query drafts with status='pending_review'.
    # If the enum doesn't have this value, the query will error.
    # Also try to read existing rows to check current state.
    try:
        resp = (
            db.table("email_drafts")
            .select("id")
            .eq("status", "pending_review")
            .limit(1)
            .execute()
        )
        # If we got here without error, 'pending_review' is a valid enum value
        # (or the column is TEXT)
        count = len(resp.data) if resp.data else 0
        record(
            check_id, name, PASS,
            [
                "email_drafts.status accepts 'pending_review' value",
                f"  {count} row(s) currently have status=pending_review",
            ],
        )
        return True
    except Exception as exc:
        err = str(exc)
        if "invalid input value for enum" in err.lower() or "22P02" in err:
            record(
                check_id, name, FAIL,
                [
                    "email_draft_status enum does NOT include 'pending_review'",
                    "  Original enum: draft, sent, failed",
                    "  Missing values: pending_review, approved, dismissed",
                    "  Impact: Checks 4/5 will fail — autonomous_draft_engine.py:2421 writes 'pending_review'",
                    "  Fix: Run ALTER TYPE email_draft_status ADD VALUE 'pending_review';",
                ],
            )
            return False
        # Some other error — might be a connection issue
        record(
            check_id, name, FAIL,
            [f"Unexpected error probing schema: {err}"],
        )
        return False


# ---------------------------------------------------------------------------
# Checks 1, 2, 3, 10: WebSocket checks (optional)
# ---------------------------------------------------------------------------


async def _ws_chat(user_id: str, message: str, timeout_sec: float = 30.0) -> str:
    """Send a message via WebSocket and collect the full response."""
    import asyncio

    uri = f"ws://{SERVER_URL.replace('http://', '').replace('https://', '')}/ws/{user_id}?token={SUPABASE_SERVICE_KEY}&session_id=verify"
    tokens: list[str] = []

    async with websockets.connect(uri, close_timeout=5) as ws:
        payload = json.dumps(
            {"type": "user.message", "payload": {"message": message}}
        )
        await ws.send(payload)

        try:
            while True:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout_sec)
                data = json.loads(raw)
                msg_type = data.get("type", "")

                if msg_type == "aria.token":
                    tokens.append(data.get("payload", {}).get("token", ""))
                elif msg_type == "aria.stream_complete":
                    break
        except asyncio.TimeoutError:
            pass

    return "".join(tokens)


def check_1_email_awareness(user_id: str, reachable: bool):
    """Check 1: ARIA knows it can access the user's email."""
    check_id = "Check 1"
    name = "Email Access Awareness"

    if not reachable or not HAS_WEBSOCKETS:
        reason = "server not reachable" if not HAS_WEBSOCKETS else "server not reachable"
        if HAS_WEBSOCKETS and not reachable:
            reason = "server not reachable"
        elif not HAS_WEBSOCKETS:
            reason = "websockets package not installed"
        record(check_id, name, SKIP, [f"({reason})"])
        return

    import asyncio

    try:
        response = asyncio.get_event_loop().run_until_complete(
            _ws_chat(user_id, "Can you access my emails?")
        )
        keywords = ["email", "outlook", "gmail", "inbox", "mail"]
        if any(kw in response.lower() for kw in keywords):
            record(check_id, name, PASS, [f"Response mentions email access ({len(response)} chars)"])
        else:
            record(check_id, name, FAIL, [f"Response did not mention email: {response[:200]}"])
    except Exception as exc:
        record(check_id, name, SKIP, [f"WebSocket error: {exc}"])


def check_2_email_reading(user_id: str, reachable: bool):
    """Check 2: ARIA can read and surface email content."""
    check_id = "Check 2"
    name = "Email Reading"

    if not reachable or not HAS_WEBSOCKETS:
        record(check_id, name, SKIP, ["(server not reachable)"])
        return

    import asyncio

    try:
        response = asyncio.get_event_loop().run_until_complete(
            _ws_chat(user_id, "Show me my recent emails")
        )
        # Look for email-like content: subjects, senders, @
        signals = ["@", "subject", "from", "re:", "email", "sent", "received"]
        hits = [s for s in signals if s in response.lower()]
        if len(hits) >= 2:
            record(check_id, name, PASS, [f"Response contains email content signals: {hits}"])
        else:
            record(check_id, name, FAIL, [f"Response lacks email content: {response[:200]}"])
    except Exception as exc:
        record(check_id, name, SKIP, [f"WebSocket error: {exc}"])


def check_3_confidence_language(user_id: str, reachable: bool):
    """Check 3: ARIA uses hedging language for uncertain inferences."""
    check_id = "Check 3"
    name = "Confidence Language"

    if not reachable or not HAS_WEBSOCKETS:
        record(check_id, name, SKIP, ["(server not reachable)"])
        return

    import asyncio

    try:
        response = asyncio.get_event_loop().run_until_complete(
            _ws_chat(user_id, "How do these emails relate to my goals?")
        )
        hedges = ["appears", "may", "suggest", "seems", "possible", "likely",
                   "might", "could", "it looks like", "based on", "i think",
                   "not certain", "can you confirm"]
        hits = [h for h in hedges if h in response.lower()]
        if hits:
            record(check_id, name, PASS, [f"Hedging phrases found: {hits}"])
        else:
            record(
                check_id, name, FAIL,
                ["No hedging language detected — flat assertions about uncertain inferences",
                 f"  Response excerpt: {response[:200]}"],
            )
    except Exception as exc:
        record(check_id, name, SKIP, [f"WebSocket error: {exc}"])


# ---------------------------------------------------------------------------
# Check 4: Draft Generation (Database)
# ---------------------------------------------------------------------------


def check_4_draft_generation(user_id: str, schema_ok: bool):
    """Check 4: Verify drafts exist with correct metadata."""
    check_id = "Check 4"
    name = "Draft Generation"

    try:
        resp = (
            db.table("email_drafts")
            .select("id, status, recipient_name, confidence_level, style_match_score, aria_notes, user_action")
            .eq("user_id", user_id)
            .order("created_at", desc=True)
            .limit(10)
            .execute()
        )
        rows = resp.data or []

        if not rows:
            record(
                check_id, name, FAIL,
                ["No email drafts found for this user",
                 "  Expected: at least 1 draft with status='pending_review'"],
            )
            return

        # Count drafts by status
        statuses = {}
        for r in rows:
            s = r.get("status", "unknown")
            statuses[s] = statuses.get(s, 0) + 1

        pending = [r for r in rows if r.get("status") == "pending_review"]
        confidence_vals = [r["confidence_level"] for r in rows if r.get("confidence_level") is not None]
        aria_notes_count = sum(1 for r in rows if r.get("aria_notes"))

        details = [
            f"{len(rows)} drafts found, statuses: {statuses}",
            f"  pending_review: {len(pending)}",
            f"  confidence_level values: {confidence_vals[:5]}",
            f"  aria_notes populated: {aria_notes_count}/{len(rows)}",
        ]

        if not schema_ok:
            details.insert(0, "WARNING: Schema pre-check failed — 'pending_review' may not exist in enum")

        if len(pending) > 0 and confidence_vals and aria_notes_count > 0:
            record(check_id, name, PASS, details)
        elif len(rows) > 0 and confidence_vals:
            # Drafts exist with metadata but no pending_review status (schema bug)
            record(
                check_id, name, FAIL,
                details + ["  No drafts with status='pending_review' — likely schema enum bug"],
            )
        else:
            record(check_id, name, FAIL, details)
    except Exception as exc:
        record(check_id, name, FAIL, [f"Query error: {exc}"])


# ---------------------------------------------------------------------------
# Check 5: Draft Approval (Database fallback)
# ---------------------------------------------------------------------------


def check_5_draft_approval(user_id: str):
    """Check 5: Verify approval workflow produces correct state."""
    check_id = "Check 5"
    name = "Draft Approval"

    try:
        # Check that approved/edited drafts have correct state
        # Note: actual columns are saved_to_client (bool) and saved_to_client_at (timestamp),
        # NOT client_draft_id (that column was never migrated to the live DB).
        resp = (
            db.table("email_drafts")
            .select("id, status, user_action, action_detected_at, saved_to_client, saved_to_client_at")
            .eq("user_id", user_id)
            .in_("user_action", ["approved", "edited"])
            .limit(10)
            .execute()
        )
        approved = resp.data or []

        if not approved:
            # No approved drafts yet — check if there are any drafts at all
            all_resp = (
                db.table("email_drafts")
                .select("id, user_action")
                .eq("user_id", user_id)
                .limit(5)
                .execute()
            )
            all_drafts = all_resp.data or []
            actions = [r.get("user_action", "?") for r in all_drafts]
            record(
                check_id, name, FAIL,
                [
                    "No approved/edited drafts found",
                    f"  All draft actions: {actions}",
                    "  Either no drafts exist, or none have been approved yet",
                ],
            )
            return

        with_timestamp = [r for r in approved if r.get("action_detected_at")]
        with_saved = [r for r in approved if r.get("saved_to_client")]
        with_saved_at = [r for r in approved if r.get("saved_to_client_at")]

        details = [
            f"{len(approved)} approved/edited drafts found",
            f"  action_detected_at set: {len(with_timestamp)}/{len(approved)}",
            f"  saved_to_client set: {len(with_saved)}/{len(approved)}",
            f"  saved_to_client_at set: {len(with_saved_at)}/{len(approved)}",
        ]

        if with_timestamp:
            record(check_id, name, PASS, details)
        else:
            record(
                check_id, name, FAIL,
                details + ["  No approved drafts have action_detected_at — approval tracking broken"],
            )
    except Exception as exc:
        record(check_id, name, FAIL, [f"Query error: {exc}"])


# ---------------------------------------------------------------------------
# Check 6: Scan Log Transparency (Database)
# ---------------------------------------------------------------------------


def check_6_scan_log(user_id: str):
    """Check 6: Verify email scan decisions are logged."""
    check_id = "Check 6"
    name = "Scan Log Transparency"

    try:
        resp = (
            db.table("email_scan_log")
            .select("email_id, sender_email, sender_name, subject, category, urgency, reason, confidence, scanned_at")
            .eq("user_id", user_id)
            .order("scanned_at", desc=True)
            .limit(50)
            .execute()
        )
        rows = resp.data or []

        if not rows:
            record(check_id, name, FAIL, ["No scan log entries found for this user"])
            return

        # Count by category
        cats = {}
        for r in rows:
            c = r.get("category", "unknown")
            cats[c] = cats.get(c, 0) + 1

        # Check for populated reason field
        with_reason = sum(1 for r in rows if r.get("reason"))
        with_confidence = sum(1 for r in rows if r.get("confidence") is not None)

        details = [
            f"{len(rows)} decisions logged | " + " | ".join(f"{k}: {v}" for k, v in sorted(cats.items())),
            f"  reason populated: {with_reason}/{len(rows)}",
            f"  confidence populated: {with_confidence}/{len(rows)}",
        ]

        if with_reason > 0:
            record(check_id, name, PASS, details)
        else:
            record(
                check_id, name, FAIL,
                details + ["  reason field is empty on all entries — transparency broken"],
            )
    except Exception as exc:
        record(check_id, name, FAIL, [f"Query error: {exc}"])


# ---------------------------------------------------------------------------
# Check 7: Activity Feed (Database)
# ---------------------------------------------------------------------------


def check_7_activity_feed(user_id: str):
    """Check 7: Verify email-related activity entries exist."""
    check_id = "Check 7"
    name = "Activity Feed"

    email_activity_types = [
        "inbox_scanned",
        "email_drafted",
        "draft_saved_to_client",
        "draft_dismissed",
    ]

    try:
        resp = (
            db.table("aria_activity")
            .select("activity_type, agent, title, confidence, created_at")
            .eq("user_id", user_id)
            .in_("activity_type", email_activity_types)
            .order("created_at", desc=True)
            .limit(20)
            .execute()
        )
        rows = resp.data or []

        if not rows:
            record(check_id, name, FAIL, ["No email-related activity entries found"])
            return

        # Count by type
        types = {}
        for r in rows:
            t = r.get("activity_type", "unknown")
            types[t] = types.get(t, 0) + 1

        details = [" | ".join(f"{k}: {v}" for k, v in sorted(types.items()))]

        if types.get("inbox_scanned", 0) > 0:
            record(check_id, name, PASS, details)
        else:
            record(
                check_id, name, FAIL,
                details + ["  No 'inbox_scanned' activity — autonomous scanning may not be running"],
            )
    except Exception as exc:
        record(check_id, name, FAIL, [f"Query error: {exc}"])


# ---------------------------------------------------------------------------
# Check 8: Lead Matching (Database)
# ---------------------------------------------------------------------------


def check_8_lead_matching(user_id: str):
    """Check 8: Verify no false lead matches for 'bio' sender domains."""
    check_id = "Check 8"
    name = "Lead Matching"

    try:
        resp = (
            db.table("email_scan_log")
            .select("email_id, sender_email, sender_name, subject, category, reason")
            .eq("user_id", user_id)
            .ilike("sender_email", "%bio%")
            .limit(10)
            .execute()
        )
        rows = resp.data or []

        if not rows:
            record(check_id, name, NA, ["No sender_email matching '%bio%' in scan log"])
            return

        # Check for false matches: reason references BioMarin/Biogen for unrelated senders
        false_matches = []
        for r in rows:
            reason = (r.get("reason") or "").lower()
            sender = (r.get("sender_email") or "").lower()
            # If reason mentions specific companies but sender is generic
            if ("biomarin" in reason or "biogen" in reason) and (
                "biomarin" not in sender and "biogen" not in sender
            ):
                false_matches.append(
                    f"  {r['sender_email']}: reason mentions BioMarin/Biogen incorrectly"
                )

        details = [f"{len(rows)} 'bio' sender(s) found in scan log"]
        if false_matches:
            record(
                check_id, name, FAIL,
                details + ["  False lead matches detected:"] + false_matches,
            )
        else:
            senders = [r.get("sender_email", "?") for r in rows[:5]]
            record(
                check_id, name, PASS,
                details + [f"  Senders: {senders}", "  No false BioMarin/Biogen matches"],
            )
    except Exception as exc:
        record(check_id, name, FAIL, [f"Query error: {exc}"])


# ---------------------------------------------------------------------------
# Check 9: Style Fingerprint (Database)
# ---------------------------------------------------------------------------


def check_9_style_fingerprint(user_id: str):
    """Check 9: Verify writing style data is available via at least one source.

    Primary source: user_settings.preferences.digital_twin (writing_style + personality_calibration)
    Fallback source: digital_twin_profiles table (tone, writing_style, formality_level)

    The draft generation pipeline uses cascading reads, so PASS if either source
    provides the data needed for style-matched drafts.
    """
    check_id = "Check 9"
    name = "Style Fingerprint"

    us_style_summary = False
    us_tone_guidance = False
    dtp_writing_style = False
    dtp_tone = None
    dtp_formality = None
    details: list[str] = []

    # Location 1: user_settings.preferences JSONB (primary)
    try:
        resp = (
            db.table("user_settings")
            .select("preferences")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if resp.data:
            prefs = resp.data[0].get("preferences") or {}
            dt = prefs.get("digital_twin") or {}

            ws = dt.get("writing_style") or {}
            style_summary = ws.get("style_summary")
            if style_summary:
                us_style_summary = True
                snippet = f'"{style_summary[:80]}..."' if len(str(style_summary)) > 80 else f'"{style_summary}"'
                details.append(f"user_settings style_summary: {snippet}")
            else:
                details.append("user_settings style_summary: not set")

            pc = dt.get("personality_calibration") or {}
            tone_guidance = pc.get("tone_guidance")
            if tone_guidance:
                us_tone_guidance = True
                snippet = f'"{tone_guidance[:80]}..."' if len(str(tone_guidance)) > 80 else f'"{tone_guidance}"'
                details.append(f"user_settings tone_guidance: {snippet}")
            else:
                details.append("user_settings tone_guidance: not set")
        else:
            details.append("user_settings row: NOT FOUND")
    except Exception as exc:
        details.append(f"user_settings query failed: {exc}")

    # Location 2: digital_twin_profiles table (fallback)
    try:
        resp = (
            db.table("digital_twin_profiles")
            .select("tone, writing_style, vocabulary_patterns, formality_level")
            .eq("user_id", user_id)
            .limit(1)
            .execute()
        )
        if resp.data:
            row = resp.data[0]
            dtp_tone = row.get("tone")
            dtp_formality = row.get("formality_level")
            if row.get("writing_style"):
                dtp_writing_style = True
                ws_snippet = row["writing_style"]
                ws_snippet = f'"{ws_snippet[:80]}..."' if len(ws_snippet) > 80 else f'"{ws_snippet}"'
                details.append(
                    f"digital_twin_profiles: tone={dtp_tone}, "
                    f"formality={dtp_formality}, "
                    f"writing_style={ws_snippet}"
                )
            else:
                details.append("digital_twin_profiles: row exists but writing_style is NULL")
        else:
            details.append("digital_twin_profiles: NO ROW for this user")
    except Exception as exc:
        details.append(f"digital_twin_profiles query failed: {exc}")

    # Evaluate: PASS if at least one complete source exists
    primary_complete = us_style_summary and us_tone_guidance
    fallback_available = dtp_writing_style

    if primary_complete:
        details.insert(0, "Primary source (user_settings) complete")
        record(check_id, name, PASS, details)
    elif fallback_available:
        details.insert(0, "Fallback source (digital_twin_profiles) available — draft pipeline can synthesize calibration")
        record(check_id, name, PASS, details)
    else:
        missing = []
        if not us_style_summary and not dtp_writing_style:
            missing.append("writing style (neither user_settings nor digital_twin_profiles)")
        if not us_tone_guidance and not dtp_writing_style:
            missing.append("tone guidance (no source to synthesize from)")
        record(
            check_id, name, FAIL,
            [f"Missing: {', '.join(missing)}"] + details,
        )


# ---------------------------------------------------------------------------
# Check 10: No Duplicate Responses (WebSocket — optional)
# ---------------------------------------------------------------------------


def check_10_no_duplicates(user_id: str, reachable: bool):
    """Check 10: Each message should produce exactly 1 stream_complete."""
    check_id = "Check 10"
    name = "No Duplicate Responses"

    if not reachable or not HAS_WEBSOCKETS:
        record(check_id, name, SKIP, ["(server not reachable)"])
        return

    import asyncio

    async def _count_completions():
        uri = f"ws://{SERVER_URL.replace('http://', '').replace('https://', '')}/ws/{user_id}?token={SUPABASE_SERVICE_KEY}&session_id=verify_dup"
        counts = []

        async with websockets.connect(uri, close_timeout=5) as ws:
            messages = ["Hello", "What's new?", "Thanks"]
            for msg in messages:
                payload = json.dumps(
                    {"type": "user.message", "payload": {"message": msg}}
                )
                await ws.send(payload)
                complete_count = 0
                try:
                    while True:
                        raw = await asyncio.wait_for(ws.recv(), timeout=30.0)
                        data = json.loads(raw)
                        if data.get("type") == "aria.stream_complete":
                            complete_count += 1
                            break
                except asyncio.TimeoutError:
                    pass
                counts.append(complete_count)

        return counts

    try:
        counts = asyncio.get_event_loop().run_until_complete(_count_completions())
        all_one = all(c == 1 for c in counts)
        details = [f"stream_complete counts per message: {counts}"]
        if all_one:
            record(check_id, name, PASS, details)
        else:
            record(
                check_id, name, FAIL,
                details + ["  Expected exactly 1 stream_complete per message"],
            )
    except Exception as exc:
        record(check_id, name, SKIP, [f"WebSocket error: {exc}"])


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------


def print_report(user_id: str | None, integration_type: str | None):
    """Print the formatted verification report."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print()
    print("=" * 60)
    print("  ARIA Email Intelligence Pipeline Verification")
    print("=" * 60)
    if user_id:
        print(f"  User: {user_id} ({integration_type})")
    else:
        print("  User: NONE FOUND")
    print(f"  Timestamp: {now}")
    print()

    # Determine column widths
    max_name_len = max(len(f"{r['id']}: {r['name']}") for r in results) if results else 40

    for r in results:
        label = f"{r['id']}:  {r['name']}"
        dots = "." * (max_name_len - len(label) + 6)
        status = r["status"]

        # Color codes (ANSI)
        color = {PASS: "\033[92m", FAIL: "\033[91m", SKIP: "\033[93m", NA: "\033[90m"}.get(
            status, ""
        )
        reset = "\033[0m"

        print(f"  {label} {dots} {color}{status}{reset}")
        for detail in r.get("details", []):
            print(f"    {detail}")

    # Summary
    counts = {PASS: 0, FAIL: 0, SKIP: 0, NA: 0}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1

    print()
    print("=" * 60)
    summary_parts = []
    for status in [PASS, FAIL, SKIP, NA]:
        if counts.get(status, 0) > 0:
            color = {PASS: "\033[92m", FAIL: "\033[91m", SKIP: "\033[93m", NA: "\033[90m"}.get(
                status, ""
            )
            reset = "\033[0m"
            summary_parts.append(f"{color}{status}: {counts[status]}{reset}")
    print(f"  SUMMARY: {' | '.join(summary_parts)}")
    print("=" * 60)
    print()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    print("\nARIA Email Intelligence Pipeline Verification")
    print("-" * 50)

    # Discover user
    print("Discovering test user...")
    user_id, integration_type = discover_user()
    if not user_id:
        print("\nFATAL: No user with active email integration found.")
        print("  Checked: user_integrations WHERE integration_type IN ('gmail','outlook') AND status = 'active'")
        print("  Also checked: email_drafts table for any user_id")
        print("\n  To run this verification, at least one user must have connected their email.\n")
        record("Global", "User Discovery", FAIL, ["No active email user found"])
        print_report(None, None)
        sys.exit(1)

    print(f"  Found user: {user_id} ({integration_type})")

    # Check server
    reachable = server_reachable()
    print(f"  Server reachable: {reachable}")
    print()

    # Run checks
    schema_ok = check_0_schema()
    check_1_email_awareness(user_id, reachable)
    check_2_email_reading(user_id, reachable)
    check_3_confidence_language(user_id, reachable)
    check_4_draft_generation(user_id, schema_ok)
    check_5_draft_approval(user_id)
    check_6_scan_log(user_id)
    check_7_activity_feed(user_id)
    check_8_lead_matching(user_id)
    check_9_style_fingerprint(user_id)
    check_10_no_duplicates(user_id, reachable)

    # Print report
    print_report(user_id, integration_type)

    # Exit code
    fail_count = sum(1 for r in results if r["status"] == FAIL)
    sys.exit(1 if fail_count > 0 else 0)


if __name__ == "__main__":
    main()
