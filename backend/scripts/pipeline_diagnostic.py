#!/usr/bin/env python3
"""End-to-end email draft pipeline diagnostic.

Run from backend/:
    python -m scripts.pipeline_diagnostic

Requires .env with SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, COMPOSIO_API_KEY, ANTHROPIC_API_KEY
"""

import asyncio
import json
import logging
import os
import re
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

# Add backend to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

# Load env before any imports that need config
from dotenv import load_dotenv
load_dotenv(backend_dir / ".env")

# Now import app modules
from src.core.config import settings
from src.db.supabase import SupabaseClient

USER_ID = "41475700-c1fb-4f66-8c56-77bd90b73abb"
TARGET_SENDER = "rdouglas@savillex.com"
TARGET_KEYWORD = "Design Partnership"

# Collect all diagnostic output
report_lines: list[str] = []


def log(msg: str) -> None:
    """Print and collect diagnostic output."""
    print(msg)
    report_lines.append(msg)


def divider(title: str) -> None:
    log(f"\n{'='*70}")
    log(f"  {title}")
    log(f"{'='*70}\n")


async def step1_fetch_emails() -> dict[str, Any] | None:
    """STEP 1: Fetch recent emails from Outlook via Composio."""
    divider("STEP 1 — Fetch Recent Emails from Outlook")

    try:
        from src.integrations.oauth import get_oauth_client
        oauth = get_oauth_client()

        # Get user's Outlook integration
        db = SupabaseClient.get_client()
        integration = (
            db.table("user_integrations")
            .select("*")
            .eq("user_id", USER_ID)
            .eq("integration_type", "outlook")
            .maybe_single()
            .execute()
        )

        if not integration.data:
            log("ERROR: No Outlook integration found for user")
            return None

        connection_id = integration.data.get("composio_connection_id")
        account_email = integration.data.get("account_email", "")
        log(f"Integration found: provider=outlook, connection_id={connection_id[:20]}..., account_email={account_email}")

        # Fetch recent emails
        result = oauth.execute_action_sync(
            connection_id=connection_id,
            action="OUTLOOK_LIST_MESSAGES",
            params={
                "$top": 10,
                "$orderby": "receivedDateTime desc",
                "$select": "id,subject,from,receivedDateTime,conversationId,hasAttachments,body,bodyPreview",
            },
            user_id=USER_ID,
        )

        if not result.get("successful"):
            log(f"ERROR: Composio call failed: {result.get('error')}")
            log(f"Full response: {json.dumps(result, indent=2, default=str)[:2000]}")
            return None

        messages = result.get("data", {}).get("value", [])
        log(f"Fetched {len(messages)} emails\n")

        selected_email: dict[str, Any] | None = None

        for i, msg in enumerate(messages):
            sender = msg.get("from", {}).get("emailAddress", {})
            sender_email = sender.get("address", "")
            sender_name = sender.get("name", "")
            subject = msg.get("subject", "")
            received = msg.get("receivedDateTime", "")
            conv_id = msg.get("conversationId", "")
            has_attach = msg.get("hasAttachments", False)
            body = msg.get("body", {})
            body_preview = msg.get("bodyPreview", "")

            log(f"--- Email {i+1} ---")
            log(f"  Subject: {subject}")
            log(f"  Sender email: {sender_email}")
            log(f"  Sender name: {sender_name}")
            log(f"  Received: {received}")
            log(f"  ConversationId: {conv_id[:80]}...")
            log(f"  hasAttachments: {has_attach}")
            log(f"  Body type: {type(body).__name__}")
            if isinstance(body, dict):
                log(f"  Body keys: {list(body.keys())}")
                log(f"  Body contentType: {body.get('contentType', 'N/A')}")
                content = body.get("content", "")
                log(f"  Body content (first 500 chars): {content[:500]}")
            else:
                log(f"  Body (first 500 chars): {str(body)[:500]}")
            log(f"  Body preview: {body_preview[:200]}")
            log("")

            # Check for target email
            if TARGET_SENDER.lower() in sender_email.lower() and TARGET_KEYWORD.lower() in subject.lower():
                selected_email = msg
            elif selected_email is None and sender_email and not any(
                x in sender_email.lower() for x in ["noreply", "no-reply", "notifications", "mailer-daemon"]
            ):
                # Fallback: pick first real business email
                selected_email = msg

        if selected_email:
            sel_sender = selected_email.get("from", {}).get("emailAddress", {})
            log(f"\nSELECTED EMAIL: \"{selected_email.get('subject')}\" from {sel_sender.get('name', '')} <{sel_sender.get('address', '')}>")
        else:
            log("\nERROR: Could not select any email")
            return None

        return {
            "raw": selected_email,
            "connection_id": connection_id,
            "account_email": account_email,
        }

    except Exception as e:
        log(f"STEP 1 EXCEPTION: {e}")
        log(traceback.format_exc())
        return None


async def step2_check_replied(email_data: dict[str, Any]) -> dict[str, Any]:
    """STEP 2: Check if user already replied."""
    divider("STEP 2 — Check If User Already Replied")

    raw = email_data["raw"]
    conv_id = raw.get("conversationId", "")
    connection_id = email_data["connection_id"]
    account_email = email_data["account_email"]

    log(f"ConversationId: {conv_id}")

    try:
        from src.integrations.oauth import get_oauth_client
        oauth = get_oauth_client()

        safe_conv_id = conv_id.replace("'", "''")
        result = oauth.execute_action_sync(
            connection_id=connection_id,
            action="OUTLOOK_LIST_MESSAGES",
            params={
                "$filter": f"conversationId eq '{safe_conv_id}'",
                "$orderby": "receivedDateTime asc",
                "$top": 20,
                "$select": "id,subject,from,receivedDateTime,body,bodyPreview",
            },
            user_id=USER_ID,
        )

        if not result.get("successful"):
            log(f"ERROR fetching thread: {result.get('error')}")
            return {"replied": "UNKNOWN", "thread_messages": []}

        thread_msgs = result.get("data", {}).get("value", [])
        log(f"Thread messages found: {len(thread_msgs)}")

        selected_received = raw.get("receivedDateTime", "")
        user_replied = False

        for i, msg in enumerate(thread_msgs):
            sender = msg.get("from", {}).get("emailAddress", {})
            sender_email = sender.get("address", "")
            sender_name = sender.get("name", "")
            received = msg.get("receivedDateTime", "")
            preview = msg.get("bodyPreview", "")

            is_from_user = account_email.lower() in sender_email.lower()
            marker = " [FROM USER]" if is_from_user else ""

            log(f"  [{i+1}] {sender_name} <{sender_email}>{marker}")
            log(f"      Date: {received}")
            log(f"      Preview: {preview[:200]}")
            log("")

            if is_from_user and received > selected_received:
                user_replied = True

        log(f"User already replied after selected email: {'YES' if user_replied else 'NO'}")
        return {"replied": user_replied, "thread_messages": thread_msgs}

    except Exception as e:
        log(f"STEP 2 EXCEPTION: {e}")
        log(traceback.format_exc())
        return {"replied": "ERROR", "thread_messages": []}


def step3_clean_body(email_data: dict[str, Any]) -> dict[str, Any]:
    """STEP 3: Clean the email body."""
    divider("STEP 3 — Clean Email Body")

    raw = email_data["raw"]
    body = raw.get("body", {})

    log(f"Raw body type: {type(body).__name__}")

    if isinstance(body, dict):
        log(f"Body keys: {list(body.keys())}")
        log(f"Body contentType: {body.get('contentType', 'N/A')}")
        raw_content = body.get("content", "")
        log(f"Body['content'] first 500 chars:\n{raw_content[:500]}")
    elif isinstance(body, str):
        raw_content = body
        log(f"Body string first 500 chars:\n{raw_content[:500]}")
    else:
        raw_content = str(body)
        log(f"Body (converted to str) first 500 chars:\n{raw_content[:500]}")

    # Clean
    text = raw_content
    if isinstance(text, dict):
        text = text.get("content", "")
    text = re.sub(r'<br\s*/?>', '\n', text)
    text = re.sub(r'</p>', '\n\n', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()

    log(f"\nCLEANED BODY ({len(text)} chars):\n{text[:1000]}")
    log(f"\nIs cleaned body meaningful (>50 chars of real content): {'YES' if len(text) > 50 else 'NO'}")

    return {"cleaned_body": text, "raw_content": raw_content}


async def step4_fetch_thread(email_data: dict[str, Any]) -> dict[str, Any]:
    """STEP 4: Fetch thread via EmailContextGatherer._fetch_thread."""
    divider("STEP 4 — Fetch Thread History via Context Gatherer")

    raw = email_data["raw"]
    conv_id = raw.get("conversationId", "")

    try:
        from src.services.email_context_gatherer import EmailContextGatherer
        gatherer = EmailContextGatherer()

        thread_context = await gatherer._fetch_thread(USER_ID, conv_id)

        if thread_context is None:
            log("Thread context: NULL (returned None)")
            return {"thread_context": None}

        log(f"Thread ID: {thread_context.thread_id[:80]}")
        log(f"Message count: {thread_context.message_count}")
        log(f"Summary: {thread_context.summary}")
        log(f"Summary length: {len(thread_context.summary)} chars")
        log("")

        for i, msg in enumerate(thread_context.messages):
            log(f"  [{i+1}] {msg.sender_name or 'Unknown'} <{msg.sender_email}>")
            log(f"      is_from_user: {msg.is_from_user}")
            log(f"      timestamp: {msg.timestamp}")
            log(f"      body (first 200 chars): {msg.body[:200]}")
            log("")

        return {"thread_context": thread_context}

    except Exception as e:
        log(f"STEP 4 EXCEPTION: {e}")
        log(traceback.format_exc())
        return {"thread_context": None}


async def step5_gather_context_sources(email_data: dict[str, Any]) -> dict[str, Any]:
    """STEP 5: Call each context source individually."""
    divider("STEP 5 — Context Sources (7 Sources)")

    raw = email_data["raw"]
    sender = raw.get("from", {}).get("emailAddress", {})
    sender_email = sender.get("address", "")
    sender_name = sender.get("name", "")
    subject = raw.get("subject", "")
    email_id = raw.get("id", "")
    conv_id = raw.get("conversationId", "")

    results = {}
    score = 0

    try:
        from src.services.email_context_gatherer import EmailContextGatherer
        gatherer = EmailContextGatherer()

        # Source 1: Thread
        log("--- Source 1: Thread Context ---")
        try:
            thread = await gatherer._fetch_thread(USER_ID, conv_id)
            if thread:
                log(f"  RESULT: {thread.message_count} messages, summary={len(thread.summary)} chars")
                log(f"  Summary preview: {thread.summary[:300]}")
                results["thread"] = "DATA"
                score += 1
            else:
                log("  RESULT: None")
                results["thread"] = "NULL"
        except Exception as e:
            log(f"  ERROR: {e}")
            log(f"  {traceback.format_exc()}")
            results["thread"] = "ERROR"

        # Source 2: Recipient Research
        log("\n--- Source 2: Recipient Research ---")
        try:
            research = await gatherer._research_recipient(sender_email, sender_name, user_id=USER_ID)
            if research and (research.sender_title or research.sender_company or research.bio):
                log(f"  Name: {research.sender_name}")
                log(f"  Title: {research.sender_title}")
                log(f"  Company: {research.sender_company}")
                log(f"  Bio: {(research.bio or '')[:300]}")
                log(f"  Exa sources used: {research.exa_sources_used}")
                results["recipient_research"] = "DATA"
                score += 1
            else:
                log(f"  RESULT: {research}")
                results["recipient_research"] = "NULL"
        except Exception as e:
            log(f"  ERROR: {e}")
            log(f"  {traceback.format_exc()}")
            results["recipient_research"] = "ERROR"

        # Source 3: Recipient Style
        log("\n--- Source 3: Recipient Writing Style ---")
        try:
            style = await gatherer._get_recipient_style(USER_ID, sender_email)
            if style and style.exists:
                log(f"  Greeting: {style.greeting_style}")
                log(f"  Signoff: {style.signoff_style}")
                log(f"  Formality: {style.formality_level}")
                log(f"  Tone: {style.tone}")
                log(f"  Email count: {style.email_count}")
                results["recipient_style"] = "DATA"
                score += 1
            else:
                log(f"  RESULT: exists={style.exists if style else 'None'}")
                results["recipient_style"] = "NULL"
        except Exception as e:
            log(f"  ERROR: {e}")
            log(f"  {traceback.format_exc()}")
            results["recipient_style"] = "ERROR"

        # Source 4: Relationship History
        log("\n--- Source 4: Relationship History ---")
        try:
            history = await gatherer._get_relationship_history(USER_ID, sender_email)
            if history and (history.total_emails > 0 or history.memory_facts):
                log(f"  Total emails: {history.total_emails}")
                log(f"  Relationship type: {history.relationship_type}")
                log(f"  Last interaction: {history.last_interaction}")
                log(f"  Recent topics: {history.recent_topics}")
                log(f"  Memory facts: {history.memory_facts[:3]}")
                results["relationship_history"] = "DATA"
                score += 1
            else:
                log(f"  RESULT: total_emails={history.total_emails if history else 'None'}")
                results["relationship_history"] = "NULL"
        except Exception as e:
            log(f"  ERROR: {e}")
            log(f"  {traceback.format_exc()}")
            results["relationship_history"] = "ERROR"

        # Source 5: Relationship Health
        log("\n--- Source 5: Relationship Health ---")
        try:
            health = await gatherer._get_relationship_health(USER_ID, sender_email)
            if health and health.trend != "new":
                log(f"  Total emails: {health.total_emails}")
                log(f"  Trend: {health.trend}")
                log(f"  Weekly frequency: {health.weekly_frequency}")
                log(f"  Health score: {health.health_score}")
                log(f"  ARIA note: {health.aria_note}")
                results["relationship_health"] = "DATA"
                score += 1
            else:
                log(f"  RESULT: trend={health.trend if health else 'None'}")
                results["relationship_health"] = "NULL"
        except Exception as e:
            log(f"  ERROR: {e}")
            log(f"  {traceback.format_exc()}")
            results["relationship_health"] = "ERROR"

        # Source 6: Corporate Memory
        log("\n--- Source 6: Corporate Memory ---")
        try:
            corp = await gatherer._get_corporate_memory(USER_ID, subject, sender_email)
            if corp and corp.facts:
                log(f"  Facts found: {len(corp.facts)}")
                for f in corp.facts[:3]:
                    log(f"    - {f}")
                results["corporate_memory"] = "DATA"
                score += 1
            else:
                log(f"  RESULT: facts={len(corp.facts) if corp else 'None'}")
                results["corporate_memory"] = "NULL"
        except Exception as e:
            log(f"  ERROR: {e}")
            log(f"  {traceback.format_exc()}")
            results["corporate_memory"] = "ERROR"

        # Source 7: Calendar Context
        log("\n--- Source 7: Calendar Context ---")
        try:
            calendar = await gatherer._get_calendar_context(USER_ID, sender_email)
            if calendar and calendar.connected:
                log(f"  Connected: {calendar.connected}")
                log(f"  Upcoming: {calendar.upcoming_meetings}")
                log(f"  Recent: {calendar.recent_meetings}")
                results["calendar"] = "DATA"
                score += 1
            else:
                log(f"  RESULT: connected={calendar.connected if calendar else 'None'}")
                results["calendar"] = "NULL"
        except Exception as e:
            log(f"  ERROR: {e}")
            log(f"  {traceback.format_exc()}")
            results["calendar"] = "ERROR"

        # Source 8: CRM Context (bonus)
        log("\n--- Source 8: CRM Context ---")
        try:
            crm = await gatherer._get_crm_context(USER_ID, sender_email)
            if crm and crm.connected:
                log(f"  Connected: {crm.connected}")
                log(f"  Lead stage: {crm.lead_stage}")
                log(f"  Deal value: {crm.deal_value}")
                results["crm"] = "DATA"
            else:
                log(f"  RESULT: connected={crm.connected if crm else 'None'}")
                results["crm"] = "NULL"
        except Exception as e:
            log(f"  ERROR: {e}")
            log(f"  {traceback.format_exc()}")
            results["crm"] = "ERROR"

        log(f"\nCONTEXT SCORECARD: {score}/7 sources returned data")

    except Exception as e:
        log(f"STEP 5 EXCEPTION: {e}")
        log(traceback.format_exc())

    results["score"] = score
    return results


async def step6_digital_twin(email_data: dict[str, Any]) -> dict[str, Any]:
    """STEP 6: Get digital twin writing style."""
    divider("STEP 6 — Digital Twin Writing Style")

    try:
        db = SupabaseClient.get_client()

        result = (
            db.table("digital_twin_profiles")
            .select("*")
            .eq("user_id", USER_ID)
            .maybe_single()
            .execute()
        )

        if result.data:
            log(f"DIGITAL TWIN EXISTS: YES")
            writing_style = result.data.get("writing_style", "")
            log(f"Writing style (first 500 chars): {str(writing_style)[:500]}")
            formatting = result.data.get("formatting_patterns", {})
            log(f"Formatting patterns: {json.dumps(formatting, default=str)[:500]}")
            log(f"All keys: {list(result.data.keys())}")
            return {"exists": True, "data": result.data}
        else:
            log("DIGITAL TWIN EXISTS: NO")
            return {"exists": False, "data": None}

    except Exception as e:
        log(f"STEP 6 EXCEPTION: {e}")
        log(traceback.format_exc())
        return {"exists": False, "data": None}


async def step7_recipient_profile(email_data: dict[str, Any]) -> dict[str, Any]:
    """STEP 7: Get recipient writing profile."""
    divider("STEP 7 — Recipient Writing Profile")

    raw = email_data["raw"]
    sender = raw.get("from", {}).get("emailAddress", {})
    sender_email = sender.get("address", "")

    try:
        db = SupabaseClient.get_client()

        result = (
            db.table("recipient_writing_profiles")
            .select("*")
            .eq("user_id", USER_ID)
            .eq("recipient_email", sender_email)
            .maybe_single()
            .execute()
        )

        if result.data:
            log(f"RECIPIENT PROFILE EXISTS: YES")
            log(f"  Greeting: {result.data.get('greeting_style')}")
            log(f"  Signoff: {result.data.get('signoff_style')}")
            log(f"  Formality: {result.data.get('formality_level')}")
            log(f"  Tone: {result.data.get('tone')}")
            log(f"  Email count: {result.data.get('email_count')}")
            log(f"  Relationship type: {result.data.get('relationship_type')}")
            log(f"  Uses emoji: {result.data.get('uses_emoji')}")
            return {"exists": True, "data": result.data}
        else:
            log(f"RECIPIENT PROFILE EXISTS: NO (for {sender_email})")
            return {"exists": False, "data": None}

    except Exception as e:
        log(f"STEP 7 EXCEPTION: {e}")
        log(traceback.format_exc())
        return {"exists": False, "data": None}


async def step8_build_prompt(email_data: dict[str, Any], context_data: dict[str, Any]) -> dict[str, Any]:
    """STEP 8: Build the EXACT LLM prompt."""
    divider("STEP 8 — Build LLM Prompt")

    raw = email_data["raw"]
    sender = raw.get("from", {}).get("emailAddress", {})
    sender_email = sender.get("address", "")
    sender_name = sender.get("name", "")
    subject = raw.get("subject", "")
    email_id = raw.get("id", "")
    conv_id = raw.get("conversationId", "")
    body = raw.get("body", {})
    body_preview = raw.get("bodyPreview", "")

    try:
        from src.services.autonomous_draft_engine import AutonomousDraftEngine
        from src.services.email_context_gatherer import EmailContextGatherer, DraftContext

        engine = AutonomousDraftEngine()
        gatherer = EmailContextGatherer()

        # First, gather context the same way the pipeline does
        log("Gathering full context via EmailContextGatherer.gather_context()...")
        context = await gatherer.gather_context(
            user_id=USER_ID,
            email_id=email_id,
            thread_id=conv_id,
            sender_email=sender_email,
            sender_name=sender_name,
            subject=subject,
        )
        log(f"Context gathered. Sources used: {context.sources_used}")
        log(f"Context ID: {context.id}")

        # Get style guidelines
        from src.memory.digital_twin import DigitalTwin
        dt = DigitalTwin()
        style_guidelines = await dt.get_style_guidelines(USER_ID)
        log(f"\nStyle guidelines length: {len(style_guidelines)} chars")
        log(f"Style guidelines preview: {style_guidelines[:500]}")

        # Get personality calibration
        from src.onboarding.personality_calibrator import PersonalityCalibrator
        calibrator = PersonalityCalibrator()
        calibration = await calibrator.get_calibration(USER_ID)
        tone_guidance = calibration.tone_guidance if calibration else ""
        log(f"\nTone guidance length: {len(tone_guidance)} chars")
        log(f"Tone guidance: {tone_guidance[:300]}")

        # Create a mock EmailCategory-like object (what the pipeline actually uses)
        email_obj = SimpleNamespace(
            email_id=email_id,
            thread_id=conv_id,
            sender_email=sender_email,
            sender_name=sender_name,
            subject=subject,
            snippet=body_preview[:200] if body_preview else "",
            urgency="NORMAL",
            hasAttachments=raw.get("hasAttachments", False),
            # NOTE: EmailCategory does NOT have a 'body' field!
            # The original pipeline's EmailCategory model only stores 'snippet' (200 chars)
        )

        # Check what _build_reply_prompt would see
        email_body_from_getattr = getattr(email_obj, "body", None)
        log(f"\n--- CRITICAL CHECK ---")
        log(f"getattr(email, 'body', None) = {email_body_from_getattr}")
        log(f"email.snippet = {email_obj.snippet[:200]}")
        log(f"So _build_reply_prompt will use: {'email.body (full body)' if email_body_from_getattr else 'email.snippet (200 chars only!)'}")

        # Get formatting patterns
        formatting_patterns = await engine._get_formatting_patterns(USER_ID)
        log(f"\nFormatting patterns: {formatting_patterns}")

        # Get user name
        user_name = await engine._get_user_name(USER_ID)
        log(f"User name: {user_name}")

        # Build the prompt
        prompt = engine._build_reply_prompt(
            user_name=user_name,
            email=email_obj,
            context=context,
            style_guidelines=style_guidelines,
            tone_guidance=tone_guidance,
            formatting_patterns=formatting_patterns,
        )

        log(f"\n--- FULL PROMPT ({len(prompt)} chars) ---")
        log(prompt)
        log(f"--- END PROMPT ---\n")

        # Checks
        cleaned_body = body.get("content", "") if isinstance(body, dict) else str(body)
        # Strip HTML for comparison
        cleaned_check = re.sub(r'<[^>]+>', '', cleaned_body).strip()[:100]

        has_email_body = cleaned_check[:50] in prompt if cleaned_check[:50] else False
        has_thread_summary = bool(context.thread_context and context.thread_context.summary and context.thread_context.summary[:50] in prompt)
        has_writing_style = style_guidelines[:50] in prompt if style_guidelines else False
        has_recipient_name = sender_name in prompt if sender_name else False
        output_format = "JSON" if '"subject"' in prompt and '"body"' in prompt else "HTML" if "HTML" in prompt else "UNCLEAR"
        has_anti_hallucination = "guardrail" in prompt.lower() or "do not" in prompt.lower() or "never" in prompt.lower()

        log(f"CHECK: Contains email body content: {'YES' if has_email_body else 'NO'}")
        log(f"CHECK: Contains thread summary: {'YES' if has_thread_summary else 'NO'}")
        log(f"CHECK: Contains writing style: {'YES' if has_writing_style else 'NO'}")
        log(f"CHECK: Contains recipient name: {'YES' if has_recipient_name else 'NO'}")
        log(f"CHECK: Output format requested: {output_format}")
        log(f"CHECK: Has anti-hallucination: {'YES' if has_anti_hallucination else 'NO'}")

        return {
            "prompt": prompt,
            "context": context,
            "email_obj": email_obj,
            "style_guidelines": style_guidelines,
            "tone_guidance": tone_guidance,
            "user_name": user_name,
            "has_email_body": has_email_body,
        }

    except Exception as e:
        log(f"STEP 8 EXCEPTION: {e}")
        log(traceback.format_exc())
        return {"prompt": None}


async def step9_call_llm(prompt_data: dict[str, Any]) -> dict[str, Any]:
    """STEP 9: Call the LLM and capture raw response."""
    divider("STEP 9 — Call LLM")

    if not prompt_data.get("prompt"):
        log("SKIPPED: No prompt available from Step 8")
        return {"response": None}

    try:
        from src.services.autonomous_draft_engine import AutonomousDraftEngine

        engine = AutonomousDraftEngine()

        # Call _generate_reply_draft the same way the pipeline does
        email_obj = prompt_data["email_obj"]
        context = prompt_data["context"]
        style_guidelines = prompt_data["style_guidelines"]
        tone_guidance = prompt_data["tone_guidance"]
        user_name = prompt_data["user_name"]

        log("Calling _generate_reply_draft()...")

        draft_content = await engine._generate_reply_draft(
            user_id=USER_ID,
            user_name=user_name,
            email=email_obj,
            context=context,
            style_guidelines=style_guidelines,
            tone_guidance=tone_guidance,
        )

        log(f"\n--- RAW LLM RESPONSE ---")
        log(f"Subject: {draft_content.subject}")
        log(f"Body ({len(draft_content.body)} chars):")
        log(draft_content.body)
        log(f"--- END RESPONSE ---\n")

        # Checks
        is_json = draft_content.body.strip().startswith("{")
        has_p_tags = "<p>" in draft_content.body
        body_lower = draft_content.body.lower()

        log(f"CHECK: Response is JSON wrapper: {'YES' if is_json else 'NO'}")
        log(f"CHECK: Body contains <p> tags: {'YES' if has_p_tags else 'NO'}")
        log(f"CHECK: Final body is HTML: {'YES' if has_p_tags else 'NO'}")

        return {
            "draft_content": draft_content,
            "subject": draft_content.subject,
            "body": draft_content.body,
        }

    except Exception as e:
        log(f"STEP 9 EXCEPTION: {e}")
        log(traceback.format_exc())
        return {"response": None}


async def step10_parse_response(llm_data: dict[str, Any]) -> dict[str, Any]:
    """STEP 10: Parse the response."""
    divider("STEP 10 — Parse Response")

    if not llm_data.get("draft_content"):
        log("SKIPPED: No LLM response from Step 9")
        return {}

    draft_content = llm_data["draft_content"]

    log(f"Parsed subject: {draft_content.subject}")
    log(f"Parsed body (first 500 chars): {draft_content.body[:500]}")
    log(f"Body length: {len(draft_content.body)} chars")

    # Check for JSON wrapper
    body = draft_content.body
    has_json_wrapper = body.strip().startswith("{") or body.strip().startswith("```")
    is_clean_html = "<p>" in body and not has_json_wrapper

    log(f"\nCHECK: Body extracted cleanly: {'YES' if is_clean_html else 'NO'}")
    log(f"CHECK: JSON wrapper present: {'YES' if has_json_wrapper else 'NO'}")
    log(f"CHECK: Final body is HTML: {'YES' if '<p>' in body else 'NO'}")

    return {"clean_html": is_clean_html, "body": body, "subject": draft_content.subject}


async def step11_check_save(email_data: dict[str, Any], parsed_data: dict[str, Any], prompt_data: dict[str, Any]) -> dict[str, Any]:
    """STEP 11: Check what would be saved."""
    divider("STEP 11 — What Would Be Saved")

    if not parsed_data.get("body"):
        log("SKIPPED: No parsed data from Step 10")
        return {}

    raw = email_data["raw"]
    sender = raw.get("from", {}).get("emailAddress", {})

    # What goes to email_drafts table
    db_record = {
        "user_id": USER_ID,
        "recipient_email": sender.get("address", ""),
        "recipient_name": sender.get("name", ""),
        "subject": parsed_data.get("subject", ""),
        "body": parsed_data.get("body", ""),
        "purpose": "reply",
        "tone": "friendly",
        "original_email_id": raw.get("id", ""),
        "thread_id": raw.get("conversationId", ""),
        "status": "draft",
    }

    log("--- email_drafts table record ---")
    for k, v in db_record.items():
        val_str = str(v)
        if len(val_str) > 300:
            val_str = val_str[:300] + "..."
        log(f"  {k}: {val_str}")

    # What goes to Outlook
    outlook_params = {
        "subject": parsed_data.get("subject", ""),
        "body": parsed_data.get("body", ""),
        "is_html": True,
        "to_recipients": [sender.get("address", "")],
    }

    log("\n--- Outlook create draft params ---")
    for k, v in outlook_params.items():
        val_str = str(v)
        if len(val_str) > 300:
            val_str = val_str[:300] + "..."
        log(f"  {k}: {val_str}")

    body = parsed_data.get("body", "")
    is_clean_html = "<p>" in body and not body.strip().startswith("{")
    has_json_wrapper = body.strip().startswith("{") or "```" in body

    log(f"\nCHECK: DB body is clean HTML: {'YES' if is_clean_html else 'NO'}")
    log(f"CHECK: Outlook body is clean HTML: {'YES' if is_clean_html else 'NO'}")
    log(f"CHECK: is_html flag set: YES (hardcoded True)")
    log(f"CHECK: JSON wrapper in body: {'YES — PROBLEM!' if has_json_wrapper else 'NO'}")

    return {"db_record": db_record, "outlook_params": outlook_params}


async def generate_report(
    step1_result, step2_result, step3_result, step4_result,
    step5_result, step6_result, step7_result, step8_result,
    step9_result, step10_result, step11_result,
) -> None:
    """Generate the final diagnostic report."""
    divider("DIAGNOSTIC REPORT")

    body_type = "dict" if isinstance(step1_result["raw"].get("body"), dict) else type(step1_result["raw"].get("body")).__name__
    step3_data = step3_result or {}

    report = f"""
╔═══════════════════════════════════════════════════════════════╗
║            EMAIL DRAFT PIPELINE — DIAGNOSTIC REPORT           ║
╠═══════════════════════════════════════════════════════════════╣
║                                                               ║
║  STEP 1 — Email Fetch                                         ║
║  Email fetched: YES                                           ║
║  Body readable: {'YES' if step3_data.get('cleaned_body') else 'NO':50s}║
║  Body type: {body_type:55s}║
║                                                               ║
║  STEP 2 — Already Replied                                     ║
║  User already replied: {str(step2_result.get('replied', 'UNKNOWN')):44s}║
║                                                               ║
║  STEP 3 — Body Cleaning                                       ║
║  Clean body has real content: {'YES' if len(step3_data.get('cleaned_body', '')) > 50 else 'NO':37s}║
║  Clean body length: {len(step3_data.get('cleaned_body', '')):47d}║
║                                                               ║
║  STEP 4 — Thread Fetch                                        ║
║  Thread messages found: {step4_result.get('thread_context').message_count if step4_result.get('thread_context') else 0:43d}║
║  Thread summary generated: {'YES' if step4_result.get('thread_context') and step4_result['thread_context'].summary else 'NO':40s}║
║                                                               ║
║  STEP 5 — Context Sources                                     ║
║  Thread summary: {step5_result.get('thread', 'N/A'):50s}║
║  Recipient research: {step5_result.get('recipient_research', 'N/A'):46s}║
║  Recipient style: {step5_result.get('recipient_style', 'N/A'):49s}║
║  Relationship history: {step5_result.get('relationship_history', 'N/A'):44s}║
║  Relationship health: {step5_result.get('relationship_health', 'N/A'):45s}║
║  Corporate memory: {step5_result.get('corporate_memory', 'N/A'):48s}║
║  Calendar context: {step5_result.get('calendar', 'N/A'):48s}║
║  Score: {step5_result.get('score', 0)}/7{' ':59s}║
║                                                               ║
║  STEP 6 — Digital Twin                                        ║
║  Writing style exists: {'YES' if step6_result.get('exists') else 'NO':44s}║
║                                                               ║
║  STEP 7 — Recipient Profile                                   ║
║  Profile exists: {'YES' if step7_result.get('exists') else 'NO':50s}║
║                                                               ║
║  STEP 8 — LLM Prompt                                          ║
║  Contains email body: {'YES' if step8_result.get('has_email_body') else 'NO':45s}║
║  Prompt length: {len(step8_result.get('prompt', '')):51d}║
║                                                               ║
║  STEP 9 — LLM Response                                        ║
║  Response generated: {'YES' if step9_result.get('draft_content') else 'NO':46s}║
║  Body has <p> tags: {'YES' if step9_result.get('body') and '<p>' in step9_result['body'] else 'NO':47s}║
║                                                               ║
║  STEP 10 — Parsing                                            ║
║  Body extracted cleanly: {'YES' if step10_result.get('clean_html') else 'NO':42s}║
║                                                               ║
║  STEP 11 — Save                                               ║
║  is_html flag set: YES (hardcoded)                            ║
║                                                               ║
║  BROKEN LINKS IDENTIFIED:                                     ║"""

    broken_links: list[str] = []

    # Check: EmailCategory has no 'body' field
    broken_links.append(
        "EmailCategory model has NO 'body' field (only 'snippet' = 200 chars).\n"
        "║     _build_reply_prompt uses getattr(email, 'body', None) which returns\n"
        "║     None, falling back to email.snippet (200 chars only).\n"
        "║     File: backend/src/services/email_analyzer.py:33-47\n"
        "║     File: backend/src/services/autonomous_draft_engine.py:1373"
    )

    if not step8_result.get("has_email_body"):
        broken_links.append(
            "Prompt does NOT contain the actual email body content.\n"
            "║     The LLM has insufficient context to write a meaningful reply."
        )

    if step5_result.get("score", 0) < 3:
        broken_links.append(
            f"Only {step5_result.get('score', 0)}/7 context sources returned data.\n"
            "║     Drafts will lack context awareness."
        )

    if not step6_result.get("exists"):
        broken_links.append(
            "No digital twin writing style exists for this user.\n"
            "║     Style matching will use fallback/generic style."
        )

    for i, link in enumerate(broken_links, 1):
        report += f"\n║  {i}. {link}"

    if not broken_links:
        report += "\n║  None identified — pipeline looks healthy."

    report += f"""
║                                                               ║
╚═══════════════════════════════════════════════════════════════╝"""

    log(report)


async def main() -> None:
    """Run the full diagnostic pipeline."""
    log(f"EMAIL DRAFT PIPELINE DIAGNOSTIC")
    log(f"Run at: {datetime.now(UTC).isoformat()}")
    log(f"User ID: {USER_ID}")
    log(f"Target sender: {TARGET_SENDER}")

    # Step 1
    step1_result = await step1_fetch_emails()
    if not step1_result:
        log("\nABORTED: Could not fetch any emails.")
        return

    # Step 2
    step2_result = await step2_check_replied(step1_result)

    # Step 3
    step3_result = step3_clean_body(step1_result)

    # Step 4
    step4_result = await step4_fetch_thread(step1_result)

    # Step 5
    step5_result = await step5_gather_context_sources(step1_result)

    # Step 6
    step6_result = await step6_digital_twin(step1_result)

    # Step 7
    step7_result = await step7_recipient_profile(step1_result)

    # Step 8
    step8_result = await step8_build_prompt(step1_result, step5_result)

    # Step 9
    step9_result = await step9_call_llm(step8_result)

    # Step 10
    step10_result = await step10_parse_response(step9_result)

    # Step 11
    step11_result = await step11_check_save(step1_result, step10_result, step8_result)

    # Final report
    await generate_report(
        step1_result, step2_result, step3_result, step4_result,
        step5_result, step6_result, step7_result, step8_result,
        step9_result, step10_result, step11_result,
    )

    # Save report
    report_path = backend_dir / "docs" / "PIPELINE_DIAGNOSTIC_REPORT.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        f.write("# Email Draft Pipeline — End-to-End Diagnostic Report\n\n")
        f.write(f"**Generated:** {datetime.now(UTC).isoformat()}\n")
        f.write(f"**User ID:** `{USER_ID}`\n\n")
        f.write("```\n")
        f.write("\n".join(report_lines))
        f.write("\n```\n")

    log(f"\nReport saved to: {report_path}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)  # Suppress noisy INFO logs
    asyncio.run(main())
