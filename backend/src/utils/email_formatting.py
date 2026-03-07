"""Email formatting utilities for converting plain text to HTML."""


def plain_text_to_email_html(text: str) -> str:
    """Convert plain text email body to properly formatted HTML for email clients.

    This ensures emails look the same in Outlook/Gmail as they do in ARIA's UI.
    Email clients ignore \\n characters in plain text, so we must convert to HTML.

    Handles:
    - Paragraph breaks (\\n\\n → <p> tags with margin)
    - Single line breaks (\\n → <br>)
    - HTML entity escaping

    Args:
        text: Plain text email body with \\n line breaks

    Returns:
        Complete HTML document with styled paragraphs
    """
    import html

    if not text:
        return ""

    # Escape HTML entities first to prevent XSS
    text = html.escape(text)

    # Split into paragraphs (double newline)
    paragraphs = text.split("\n\n")

    # Convert each paragraph
    html_parts = []
    for para in paragraphs:
        if not para.strip():
            continue
        # Convert single newlines within a paragraph to <br>
        para_html = para.strip().replace("\n", "<br>")
        html_parts.append(
            f'<p style="margin: 0 0 16px 0; line-height: 1.5; font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Arial, sans-serif;">{para_html}</p>'
        )

    body_html = "\n".join(html_parts)

    # Wrap in a basic email HTML template
    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<style>
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Arial, sans-serif;
    font-size: 14px;
    color: #333333;
    line-height: 1.5;
    margin: 0;
    padding: 16px;
  }}
  p {{ margin: 0 0 16px 0; }}
</style>
</head>
<body>
{body_html}
</body>
</html>"""
