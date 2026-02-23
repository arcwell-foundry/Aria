#!/usr/bin/env python3
"""Demo Validation Script — Board demo readiness check for Feb 28.

Runs the full email scan → draft generation pipeline, evaluates each draft,
checks Outlook sync, and produces a readiness report.

Usage:
    cd backend
    python demo_validation.py
"""

import asyncio
import html
import json
import logging
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent))

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger("demo_validation")

USER_ID = "41475700-c1fb-4f66-8c56-77bd90b73abb"
SINCE_HOURS = 72  # Scan last 3 days to catch enough emails for demo


def strip_html_for_display(html_body: str) -> str:
    """Strip HTML for terminal display."""
    text = re.sub(r"<br\s*/?>", "\n", html_body, flags=re.IGNORECASE)
    text = re.sub(r"<p>", "", text)
    text = re.sub(r"</p>", "\n", text)
    text = re.sub(r"<li>", "  - ", text)
    text = re.sub(r"</li>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def check_references_sender_content(draft_body: str, original_body: str | None, subject: str) -> bool:
    """Check if draft references specific content from the sender's email."""
    if not original_body:
        return False
    draft_lower = draft_body.lower()
    original_lower = original_body.lower()
    # Extract key terms from original (3+ word phrases, names, numbers, dates)
    words = set(re.findall(r'\b[a-z]{4,}\b', original_lower))
    common_words = {"this", "that", "with", "from", "have", "been", "will", "would",
                    "could", "should", "their", "about", "which", "when", "where",
                    "what", "your", "they", "them", "than", "more", "some", "also",
                    "just", "like", "into", "over", "only", "very", "then", "here",
                    "much", "most", "each", "does", "made", "well", "back", "even",
                    "good", "great", "help", "take", "come", "make", "know", "think",
                    "want", "look", "first", "need", "other", "work", "right", "please",
                    "thank", "thanks", "email", "hope", "forward", "looking", "reach"}
    specific_words = words - common_words
    # Check if draft uses specific terms from the original
    matches = sum(1 for w in specific_words if w in draft_lower)
    return matches >= 2


def check_sounds_like_human(draft_body: str) -> tuple[bool, list[str]]:
    """Check if draft avoids AI filler phrases."""
    filler_phrases = [
        "hope this email finds you well",
        "i hope this finds you",
        "thank you for reaching out",
        "please don't hesitate",
        "please do not hesitate",
        "as an ai",
        "i don't have opinions",
        "at your earliest convenience",
        "per our last conversation",
        "touching base",
        "circling back",
        "loop you in",
        "synergy",
        "leverage our",
        "align on",
        "bandwidth",
        "move the needle",
        "low-hanging fruit",
    ]
    found = []
    body_lower = draft_body.lower()
    for phrase in filler_phrases:
        if phrase in body_lower:
            found.append(phrase)
    return len(found) == 0, found


def check_clean_html(draft_body: str) -> tuple[bool, list[str]]:
    """Check draft is clean email HTML."""
    issues = []
    if "<html" in draft_body.lower():
        issues.append("Contains <html> tag")
    if "<head" in draft_body.lower():
        issues.append("Contains <head> tag")
    if "<style" in draft_body.lower():
        issues.append("Contains <style> tag")
    if "<body" in draft_body.lower():
        issues.append("Contains <body> tag")
    if not re.search(r"<p[> ]", draft_body, re.IGNORECASE):
        issues.append("No <p> tags found")
    return len(issues) == 0, issues


def check_hallucinations(draft_body: str, original_body: str | None, thread_context: str | None) -> list[str]:
    """Basic hallucination check — flag suspicious specifics not in source."""
    hallucinations = []
    # Check for specific dollar amounts not in context
    draft_prices = re.findall(r'\$[\d,]+(?:\.\d+)?', draft_body)
    context_text = (original_body or "") + (thread_context or "")
    for price in draft_prices:
        if price not in context_text:
            hallucinations.append(f"Price '{price}' not found in source email")
    # Check for specific dates that seem invented
    draft_dates = re.findall(r'(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}', draft_body)
    for date in draft_dates:
        if date not in context_text:
            hallucinations.append(f"Date '{date}' not found in source email")
    return hallucinations


async def run_demo_validation():
    """Run the full demo validation pipeline."""
    from src.services.autonomous_draft_engine import AutonomousDraftEngine

    engine = AutonomousDraftEngine()

    print("=" * 80)
    print("  ARIA DEMO VALIDATION — Board Demo Feb 28, 2026")
    print("=" * 80)
    print(f"\nUser ID: {USER_ID}")
    print(f"Scan window: last {SINCE_HOURS} hours")
    print(f"Timestamp: {datetime.now(UTC).isoformat()}")
    print()

    # =========================================================================
    # STEP 1: Run Email Scan Pipeline
    # =========================================================================
    print("=" * 80)
    print("  STEP 1: EMAIL SCAN PIPELINE")
    print("=" * 80)
    print("\nRunning inbox scan + draft generation...")
    print("(This may take several minutes — scanning, gathering context, generating drafts)")
    print()

    # Step 1a: Scan inbox to classify emails
    from src.services.email_analyzer import EmailAnalyzer
    analyzer = EmailAnalyzer()
    scan_result = await analyzer.scan_inbox(USER_ID, since_hours=SINCE_HOURS)

    print(f"\n--- Scan Results ---")
    print(f"Total emails scanned:  {scan_result.total_emails}")
    print(f"NEEDS_REPLY:           {len(scan_result.needs_reply)}")
    print(f"SKIP:                  {len(scan_result.skipped)}")
    print(f"FYI:                   {len(scan_result.fyi)}")

    if scan_result.needs_reply:
        print(f"\n--- NEEDS_REPLY Emails ---")
        for i, email in enumerate(scan_result.needs_reply, 1):
            print(f"  {i}. {email.sender_name} <{email.sender_email}>")
            print(f"     Subject: {email.subject}")
            print(f"     Urgency: {email.urgency}")
            print(f"     Reason: {email.reason}")
    else:
        print("\n  No NEEDS_REPLY emails found.")

    # Step 1b: Generate drafts using draft_reply_on_demand (bypasses dedup checks)
    # This is needed because some threads may already have user replies,
    # but for the demo we still want to show draft generation capability.
    from dataclasses import dataclass
    from src.services.autonomous_draft_engine import DraftResult, ProcessingRunResult

    result = ProcessingRunResult(
        run_id="demo-validation",
        user_id=USER_ID,
        started_at=datetime.now(UTC),
        emails_scanned=scan_result.total_emails,
        emails_needs_reply=len(scan_result.needs_reply),
    )

    for email in scan_result.needs_reply:
        print(f"\n  Generating draft for: {email.sender_name} — {email.subject}...")
        try:
            draft_result = await engine.draft_reply_on_demand(
                user_id=USER_ID,
                email_data={
                    "email_id": email.email_id,
                    "thread_id": email.thread_id,
                    "sender_email": email.sender_email,
                    "sender_name": email.sender_name,
                    "subject": email.subject,
                    "body": email.body or email.snippet,
                    "snippet": email.snippet,
                    "urgency": email.urgency,
                },
            )

            if draft_result.get("error"):
                result.drafts_failed += 1
                result.drafts.append(DraftResult(
                    draft_id="",
                    recipient_email=email.sender_email,
                    recipient_name=email.sender_name,
                    subject=email.subject or "",
                    body="",
                    style_match_score=0.0,
                    confidence_level=0.0,
                    aria_notes="",
                    original_email_id=email.email_id,
                    thread_id=email.thread_id,
                    context_id="",
                    success=False,
                    error=draft_result["error"],
                ))
                print(f"    FAILED: {draft_result['error']}")
            else:
                result.drafts_generated += 1
                result.drafts.append(DraftResult(
                    draft_id=draft_result.get("draft_id", ""),
                    recipient_email=email.sender_email,
                    recipient_name=email.sender_name,
                    subject=draft_result.get("subject", email.subject or ""),
                    body=draft_result.get("body", ""),
                    style_match_score=draft_result.get("style_match", 0.0),
                    confidence_level=draft_result.get("confidence", 0.0),
                    aria_notes=draft_result.get("aria_notes", ""),
                    original_email_id=email.email_id,
                    thread_id=email.thread_id,
                    context_id="",
                    success=True,
                ))
                print(f"    OK: confidence={draft_result.get('confidence', 0):.2f}, style_match={draft_result.get('style_match', 0):.2f}")
        except Exception as e:
            result.drafts_failed += 1
            logger.error("Draft generation failed for %s: %s", email.sender_email, e, exc_info=True)

    result.completed_at = datetime.now(UTC)
    result.status = "completed" if result.drafts_failed == 0 else "partial_failure"

    from src.db.supabase import SupabaseClient
    db = SupabaseClient.get_client()

    print(f"\nDrafts generated:      {result.drafts_generated}")
    print(f"Drafts failed:         {result.drafts_failed}")
    print(f"Pipeline status:       {result.status}")

    # =========================================================================
    # STEP 2: Evaluate Each Draft
    # =========================================================================
    print("\n" + "=" * 80)
    print("  STEP 2: DRAFT EVALUATION")
    print("=" * 80)

    evaluations = []

    for i, draft in enumerate(result.drafts, 1):
        if not draft.success:
            evaluations.append({
                "index": i,
                "subject": draft.subject,
                "recipient": draft.recipient_name or draft.recipient_email,
                "success": False,
                "error": draft.error,
                "demo_ready": False,
                "issues": [f"Draft generation failed: {draft.error}"],
            })
            continue

        print(f"\n{'─' * 70}")
        print(f"  Draft {i}: {draft.subject}")
        print(f"  To: {draft.recipient_name or draft.recipient_email} <{draft.recipient_email}>")
        print(f"{'─' * 70}")

        # Print full draft body
        print(f"\n  --- Draft Body ---")
        display_body = strip_html_for_display(draft.body)
        for line in display_body.split("\n"):
            print(f"  {line}")
        print()

        # Fetch original email body from scan log for comparison
        original_body = None
        try:
            orig = db.table("email_scan_log") \
                .select("snippet, subject") \
                .eq("user_id", USER_ID) \
                .eq("sender_email", draft.recipient_email) \
                .order("scanned_at", desc=True) \
                .limit(1) \
                .execute()
            if orig and orig.data:
                original_body = orig.data[0].get("snippet")
        except Exception as e:
            logger.debug("Could not fetch original body: %s", e)

        # Fetch thread context from draft_context table
        thread_context = None
        try:
            ctx = db.table("draft_context") \
                .select("thread_summary, thread_context") \
                .eq("draft_id", draft.draft_id) \
                .execute()
            if ctx and ctx.data:
                thread_context = ctx.data[0].get("thread_summary") or ""
                # Also include raw thread context if available
                raw_ctx = ctx.data[0].get("thread_context")
                if raw_ctx:
                    if isinstance(raw_ctx, str):
                        thread_context += " " + raw_ctx
                    elif isinstance(raw_ctx, dict):
                        thread_context += " " + json.dumps(raw_ctx)
        except Exception as e:
            logger.debug("Could not fetch thread context: %s", e)

        # If original_body is missing, use thread context as fallback for content checks
        check_body = original_body or thread_context

        # Evaluation checks
        refs_content = check_references_sender_content(draft.body, check_body, draft.subject)
        sounds_human, filler_found = check_sounds_like_human(draft.body)
        clean_html, html_issues = check_clean_html(draft.body)
        hallucinations = check_hallucinations(draft.body, original_body, thread_context)

        issues = []
        if not refs_content:
            issues.append("Does not reference sender's specific content")
        if not sounds_human:
            issues.append(f"Contains filler phrases: {', '.join(filler_found)}")
        if not clean_html:
            issues.append(f"HTML issues: {', '.join(html_issues)}")
        if hallucinations:
            issues.append(f"Possible hallucinations: {'; '.join(hallucinations)}")
        if draft.confidence_level < 0.3:
            issues.append(f"Low confidence: {draft.confidence_level:.2f}")

        demo_ready = len(issues) == 0

        print(f"  --- Evaluation ---")
        print(f"  References sender's content?  {'YES' if refs_content else 'NO'}")
        print(f"  Sounds like Dhruv?            {'YES' if sounds_human else 'NO'}")
        print(f"  Clean HTML?                   {'YES' if clean_html else 'NO'}")
        print(f"  Hallucinated content?          {'; '.join(hallucinations) if hallucinations else 'None detected'}")
        print(f"  Confidence:                   {draft.confidence_level:.2f}")
        print(f"  Style match:                  {draft.style_match_score:.2f}")
        print(f"  DEMO READY:                   {'YES' if demo_ready else 'NO'}")
        if issues:
            print(f"  Issues:")
            for issue in issues:
                print(f"    - {issue}")

        evaluations.append({
            "index": i,
            "subject": draft.subject,
            "recipient": draft.recipient_name or draft.recipient_email,
            "recipient_email": draft.recipient_email,
            "body": draft.body,
            "body_text": display_body,
            "success": True,
            "refs_content": refs_content,
            "sounds_human": sounds_human,
            "filler_found": filler_found,
            "clean_html": clean_html,
            "html_issues": html_issues,
            "hallucinations": hallucinations,
            "confidence": draft.confidence_level,
            "style_match": draft.style_match_score,
            "demo_ready": demo_ready,
            "issues": issues,
            "aria_notes": draft.aria_notes,
        })

    # =========================================================================
    # STEP 3: Check Outlook Drafts
    # =========================================================================
    print("\n" + "=" * 80)
    print("  STEP 3: OUTLOOK DRAFTS VERIFICATION")
    print("=" * 80)

    # Check email_drafts table for saved_to_client (indicates Outlook sync)
    outlook_synced = 0
    outlook_failed = 0
    draft_ids = [d.draft_id for d in result.drafts if d.success and d.draft_id]
    if draft_ids:
        for did in draft_ids:
            try:
                d_rec = db.table("email_drafts") \
                    .select("id, subject, saved_to_client, saved_to_client_at, email_client, recipient_email") \
                    .eq("id", did) \
                    .maybe_single() \
                    .execute()
                if d_rec and d_rec.data:
                    d = d_rec.data
                    if d.get("saved_to_client"):
                        outlook_synced += 1
                        print(f"  SYNCED: {d.get('subject', 'N/A')} → {d.get('recipient_email', 'N/A')} ({d.get('email_client', 'unknown')})")
                    else:
                        outlook_failed += 1
                        print(f"  NOT SYNCED: {d.get('subject', 'N/A')} → {d.get('recipient_email', 'N/A')}")
            except Exception as e:
                logger.warning("Could not verify draft %s: %s", did, e)
                print(f"  Error checking draft {did}: {e}")
    else:
        print("  No draft IDs to verify.")

    print(f"\n  {outlook_synced} drafts saved to Outlook")
    if outlook_failed > 0:
        print(f"  {outlook_failed} drafts FAILED to sync to Outlook")

    # =========================================================================
    # STEP 4: Demo Readiness Assessment
    # =========================================================================
    print("\n" + "=" * 80)
    print("  STEP 4: DEMO READINESS ASSESSMENT")
    print("=" * 80)

    ready_drafts = [e for e in evaluations if e["demo_ready"]]
    needs_work = [e for e in evaluations if not e["demo_ready"]]
    failed_drafts = [e for e in evaluations if not e.get("success", True)]

    print(f"\n  Drafts that are demo-ready ({len(ready_drafts)}):")
    if ready_drafts:
        for e in ready_drafts:
            print(f"    - {e['subject']} → {e['recipient']}")
    else:
        print("    (none)")

    print(f"\n  Drafts that need work ({len(needs_work)}):")
    if needs_work:
        for e in needs_work:
            print(f"    - {e['subject']} → {e['recipient']}")
            for issue in e["issues"]:
                print(f"      Issue: {issue}")
    else:
        print("    (none)")

    if failed_drafts:
        print(f"\n  Failed drafts ({len(failed_drafts)}):")
        for e in failed_drafts:
            print(f"    - {e['subject']} → {e['recipient']}: {e['error']}")

    # Overall assessment
    total = len(evaluations)
    if total == 0:
        overall = "NOT READY"
        reason = "No emails found or no drafts generated. Need emails in inbox for demo."
    elif len(ready_drafts) == total:
        overall = "DEMO READY"
        reason = f"All {total} drafts passed quality checks."
    elif len(ready_drafts) >= total * 0.7:
        overall = "MOSTLY READY"
        reason = f"{len(ready_drafts)}/{total} drafts passed. {len(needs_work)} need minor fixes."
    else:
        overall = "NOT READY"
        reason = f"Only {len(ready_drafts)}/{total} drafts passed quality checks."

    print(f"\n  {'=' * 40}")
    print(f"  OVERALL: {overall}")
    print(f"  {reason}")
    print(f"  {'=' * 40}")

    # =========================================================================
    # Generate Report
    # =========================================================================
    report = generate_report(result, evaluations, outlook_synced, outlook_failed, overall, reason)
    report_path = Path(__file__).parent / "docs" / "DEMO_READINESS_REPORT.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report)
    print(f"\n  Report saved: {report_path}")

    return overall, evaluations


def generate_report(
    result,
    evaluations: list[dict],
    outlook_synced: int,
    outlook_failed: int,
    overall: str,
    reason: str,
) -> str:
    """Generate the markdown readiness report."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        f"# ARIA Demo Readiness Report",
        f"",
        f"**Generated:** {now}",
        f"**Board Demo:** February 28, 2026",
        f"**User ID:** `{USER_ID}`",
        f"**Scan window:** {SINCE_HOURS} hours",
        f"",
        f"## Overall Assessment: {overall}",
        f"",
        f"{reason}",
        f"",
        f"## Pipeline Statistics",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Emails scanned | {result.emails_scanned} |",
        f"| NEEDS_REPLY | {result.emails_needs_reply} |",
        f"| Drafts generated | {result.drafts_generated} |",
        f"| Drafts failed | {result.drafts_failed} |",
        f"| Outlook synced | {outlook_synced} |",
        f"| Outlook failed | {outlook_failed} |",
        f"| Pipeline status | {result.status} |",
        f"",
        f"## Draft Evaluations",
        f"",
    ]

    for e in evaluations:
        lines.append(f"### {e['index']}. {e['subject']}")
        lines.append(f"**To:** {e['recipient']}")
        if not e.get("success", True):
            lines.append(f"**Status:** FAILED — {e.get('error', 'Unknown error')}")
            lines.append("")
            continue

        lines.append(f"**Demo Ready:** {'YES' if e['demo_ready'] else 'NO'}")
        lines.append("")
        lines.append("| Check | Result |")
        lines.append("|-------|--------|")
        lines.append(f"| References sender content | {'YES' if e.get('refs_content') else 'NO'} |")
        lines.append(f"| Sounds like Dhruv | {'YES' if e.get('sounds_human') else 'NO'} |")
        lines.append(f"| Clean HTML | {'YES' if e.get('clean_html') else 'NO'} |")
        lines.append(f"| Hallucinations | {'; '.join(e.get('hallucinations', [])) or 'None'} |")
        lines.append(f"| Confidence | {e.get('confidence', 0):.2f} |")
        lines.append(f"| Style match | {e.get('style_match', 0):.2f} |")
        lines.append("")

        if e.get("body_text"):
            lines.append("<details>")
            lines.append(f"<summary>Draft body (click to expand)</summary>")
            lines.append("")
            lines.append("```")
            lines.append(e["body_text"])
            lines.append("```")
            lines.append("</details>")
            lines.append("")

        if e.get("issues"):
            lines.append("**Issues:**")
            for issue in e["issues"]:
                lines.append(f"- {issue}")
            lines.append("")

        if e.get("aria_notes"):
            lines.append(f"**ARIA Notes:** {e['aria_notes'][:300]}")
            lines.append("")

    lines.append("## Recommendations")
    lines.append("")

    ready_count = sum(1 for e in evaluations if e["demo_ready"])
    total_count = len(evaluations)

    if overall == "DEMO READY":
        lines.append("All drafts passed quality checks. The pipeline is ready for the board demo.")
        lines.append("")
        lines.append("**Pre-demo checklist:**")
        lines.append("- [ ] Verify Outlook drafts appear in Dhruv's drafts folder")
        lines.append("- [ ] Open 2-3 drafts side-by-side with originals to verify quality live")
        lines.append("- [ ] Prepare talking points about context gathering (7 sources)")
        lines.append("- [ ] Have backup emails ready in case inbox is quiet on demo day")
    elif overall == "MOSTLY READY":
        lines.append(f"{ready_count}/{total_count} drafts are demo-quality. Fix the remaining issues:")
        lines.append("")
        for e in evaluations:
            if not e["demo_ready"] and e.get("issues"):
                lines.append(f"- **{e['subject']}**: {'; '.join(e['issues'])}")
    else:
        lines.append("The pipeline needs fixes before the demo. Key issues:")
        lines.append("")
        all_issues = set()
        for e in evaluations:
            for issue in e.get("issues", []):
                all_issues.add(issue)
        for issue in sorted(all_issues):
            lines.append(f"- {issue}")

    lines.append("")
    lines.append("---")
    lines.append(f"*Report generated by ARIA demo validation script at {now}*")

    return "\n".join(lines)


if __name__ == "__main__":
    asyncio.run(run_demo_validation())
