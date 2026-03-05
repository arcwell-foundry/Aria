"""Text cleaning utilities for ARIA.

Provides functions to clean and normalize text scraped from web sources,
removing markup artifacts, navigation elements, and other noise.
"""

import html
import re


def clean_signal_summary(
    raw_text: str,
    headline: str | None = None,
    max_length: int = 500,
) -> str:
    """Clean web scraping markup from signal summary text.

    Performs the following transformations:
    1. Strips <web_link>, <image_link> tags and their closing variants
    2. Strips markdown image syntax: ![...]<...> and standalone ![...]
    3. Strips markdown link syntax: [...]<...> but KEEPS the link text
    4. Strips empty bracket patterns: [], [\n], [text] without meaningful content
    5. Strips stock ticker lines (##### NUMBER patterns)
    6. Decodes HTML entities: &rsquo; -> ', &#39; -> ', &amp; -> &, etc.
    7. Removes navigation/menu artifacts: lines that are just "* [text]" repeated
    8. Removes empty lines and excess whitespace
    9. Strips duplicate headline at start if headline is provided
    10. Truncates to max_length chars with "..." if longer

    Args:
        raw_text: The raw text to clean.
        headline: Optional headline to strip from the beginning if duplicated.
        max_length: Maximum length for the cleaned text (default 500).

    Returns:
        Cleaned text with markup removed, normalized whitespace, and truncated.
    """
    if not raw_text:
        return ""

    text = raw_text

    # Step 1: Strip <web_link>, <image_link>, </web_link>, </image_link> tags
    # These appear in Exa API results and other web scraping sources
    text = re.sub(r"</?web_link>", "", text)
    text = re.sub(r"</?image_link>", "", text)
    # Also strip any remaining angle-bracket tags that look like markup
    text = re.sub(r"</?[a-z_]+>", "", text)

    # Step 2: Strip markdown image syntax: ![alt text]<url> or ![alt text](url)
    text = re.sub(r"!\[[^\]]*\]<[^>]+>", "", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    # Also strip standalone ![...] patterns (image placeholders without URLs)
    text = re.sub(r"!\[[^\]]*\]", "", text)

    # Step 3: Strip markdown link syntax but KEEP the link text
    # Pattern: [link text]<url> or [link text](url) -> link text
    text = re.sub(r"\[([^\]]+)\]<[^>]+>", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)

    # Step 4: Strip empty bracket patterns and navigation noise
    # [] - empty brackets
    text = re.sub(r"\[\s*\]", "", text)
    # [\n] - brackets with just newline/whitespace
    text = re.sub(r"\[\s*\n\s*\]", "", text)
    # [text] without URL - only keep if it looks like meaningful content
    # Remove single-word brackets like [Menu], [Team], [Home], [Login], [Register]
    text = re.sub(r"\[([A-Z][a-z]{0,15})\]", "", text)
    # Remove bracket patterns that are just navigation labels
    nav_labels = [
        "Search", "User", "Menu", "Team", "Home", "Login", "Register",
        "Contact Us", "Newsroom", "Services", "Solutions", "Press Release Distribution",
        "Visibility & Engagement", "Complimentary Features", "Investor Communications",
        "Reporting & Analytics", "PR Professionals", "IR Professionals", "Industry News",
    ]
    for label in nav_labels:
        text = text.replace(f"[{label}]", "")

    # Step 5: Strip stock ticker lines (##### NUMBER patterns)
    # Pattern like "##### SENSEX 82,276.07" or "##### NIFTY 25,482.50"
    text = re.sub(r"^#+\s*[A-Z]+\s+[\d,\.]+\s*$", "", text, flags=re.MULTILINE)
    # Also lines with just "+/- NUMBER" (stock changes)
    text = re.sub(r"^[+-][\d,\.]+\s*$", "", text, flags=re.MULTILINE)

    # Step 6: Decode HTML entities
    # Use html.unescape for standard entities
    text = html.unescape(text)

    # Handle some entities that might slip through or be encoded differently
    text = text.replace("\xa0", " ")  # Non-breaking space
    text = text.replace("\u200b", "")  # Zero-width space

    # Step 7: Remove navigation/menu artifacts
    # Lines that are just "* [text]" or "- [text]" repeated (common in scraped nav)
    lines = text.split("\n")
    cleaned_lines = []
    # Pattern for nav items like "* [Home]" or "- [About Us]"
    nav_pattern = re.compile(r"^\s*[\*\-]\s*\[[^\]]*\]\s*$")

    for line in lines:
        # Skip any line that matches the nav pattern (they're never meaningful content)
        if nav_pattern.match(line):
            continue
        # Skip lines that are mostly markup artifacts (just brackets and asterisks)
        stripped = line.strip()
        if stripped in ["*", "-", "**", "***"]:
            continue
        cleaned_lines.append(line)

    text = "\n".join(cleaned_lines)

    # Step 8: Remove empty lines and excess whitespace
    # Normalize line breaks
    text = re.sub(r"\r\n?", "\n", text)
    # Remove multiple consecutive blank lines
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    # Remove leading/trailing whitespace on each line
    lines = [line.strip() for line in text.split("\n")]
    # Remove completely empty lines at start and end
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    # Join with single newlines, then convert double newlines back
    text = "\n".join(lines)
    text = re.sub(r"\n\n+", "\n\n", text)

    # Step 9: Strip duplicate headline at start
    if headline:
        headline_clean = headline.strip().lower()
        text_start = text[: len(headline) + 20].lower()  # Extra buffer for punctuation

        # Check if text starts with the headline
        if text_start.startswith(headline_clean):
            # Remove the headline from the start
            headline_len = len(headline)
            text = text[headline_len:].lstrip(" .,\n:")

    # Step 10: Clean up orphaned bracket patterns and angle brackets
    # Remove lines that are just leftover markup fragments
    lines = text.split("\n")
    final_lines = []
    for line in lines:
        stripped = line.strip()
        # Skip lines that are just leftover markup fragments
        if stripped in ["[", "]", "<", ">", "*", "-", "**", "***"]:
            continue
        # Skip lines that are just combinations of brackets/asterisks
        if re.match(r"^[\[\]\*\<\>\-\s]+$", stripped):
            continue
        # Skip lines that start with bracket and have no real content
        if re.match(r"^\[[^\]]*$", stripped) or re.match(r"^\*?\s*\<[^>]*$", stripped):
            continue
        final_lines.append(line)
    text = "\n".join(final_lines)

    # Step 11: Final cleanup of empty lines
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)
    lines = [l.strip() for l in text.split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    text = "\n".join(lines)

    # Step 12: Truncate to max_length with "..."
    if len(text) > max_length:
        # Try to truncate at a word boundary
        truncate_at = max_length - 3  # Leave room for "..."
        # Find the last space before the truncation point
        last_space = text.rfind(" ", 0, truncate_at)
        if last_space > max_length // 2:
            # Use word boundary if it's not too far back
            text = text[:last_space].rstrip() + "..."
        else:
            # Just hard truncate
            text = text[:truncate_at].rstrip() + "..."

    return text.strip()
