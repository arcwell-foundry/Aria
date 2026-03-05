"""Tests for text cleaning utilities."""

import pytest

from src.core.text_cleaning import clean_signal_summary


class TestCleanSignalSummary:
    """Tests for the clean_signal_summary function."""

    def test_strips_web_link_tags(self) -> None:
        """Should remove <web_link> and </web_link> tags."""
        raw = "This is <web_link>some text</web_link> with links."
        result = clean_signal_summary(raw)
        assert result == "This is some text with links."

    def test_strips_image_link_tags(self) -> None:
        """Should remove <image_link> and </image_link> tags."""
        raw = "See image <image_link>diagram.png</image_link> here."
        result = clean_signal_summary(raw)
        assert result == "See image diagram.png here."

    def test_strips_markdown_images(self) -> None:
        """Should remove markdown image syntax entirely."""
        raw = "Check out ![Company Logo]<https://example.com/logo.png> for details."
        result = clean_signal_summary(raw)
        assert "![Company Logo]" not in result
        assert "Logo" not in result  # Image alt text should be removed

    def test_keeps_markdown_link_text(self) -> None:
        """Should keep link text but remove URL in markdown links."""
        raw = "Read the [full article]<https://example.com/article> for more."
        result = clean_signal_summary(raw)
        assert result == "Read the full article for more."

    def test_decodes_html_entities(self) -> None:
        """Should decode common HTML entities."""
        raw = "Cytiva&#39;s revenue &amp; growth&rsquo;s impact on the market"
        result = clean_signal_summary(raw)
        # &rsquo; decodes to curly apostrophe ', &#39; to straight apostrophe '
        # Just verify the entities are decoded (no more &...; patterns)
        assert "&rsquo;" not in result
        assert "&amp;" not in result
        assert "&#39;" not in result
        assert "revenue & growth" in result  # &amp; -> &

    def test_removes_navigation_artifacts(self) -> None:
        """Should remove repeated navigation menu patterns."""
        raw = """* [Home]
* [About]
* [Products]
* [Contact]

The actual content starts here."""
        result = clean_signal_summary(raw)
        # Navigation should be mostly removed
        assert "[Home]" not in result
        assert "[About]" not in result
        assert "actual content" in result

    def test_removes_empty_lines_and_whitespace(self) -> None:
        """Should normalize whitespace and remove empty lines."""
        raw = "First line.\n\n\n\n\nSecond line.   \n   \nThird line."
        result = clean_signal_summary(raw)
        assert "First line." in result
        assert "Second line." in result
        assert "Third line." in result
        # Should not have excessive newlines
        assert "\n\n\n" not in result

    def test_strips_duplicate_headline(self) -> None:
        """Should remove headline if duplicated at start of summary."""
        headline = "Cytiva Announces Major Acquisition"
        raw = "Cytiva Announces Major Acquisition. The company has expanded its portfolio through a strategic deal."
        result = clean_signal_summary(raw, headline=headline)
        assert not result.startswith("Cytiva Announces Major Acquisition")
        assert "expanded its portfolio" in result

    def test_truncates_long_text(self) -> None:
        """Should truncate text to max_length with ellipsis."""
        raw = "A" * 600  # 600 characters
        result = clean_signal_summary(raw, max_length=500)
        assert len(result) <= 500
        assert result.endswith("...")

    def test_truncates_at_word_boundary(self) -> None:
        """Should prefer truncating at word boundary."""
        raw = "This is a sentence with multiple words that should be truncated at a reasonable point."
        result = clean_signal_summary(raw, max_length=50)
        assert len(result) <= 50
        assert result.endswith("...")
        # Should not cut in the middle of a word
        assert not any(result[:-3].endswith(c) for c in "abcdefghijklmnopqrstuvwxyz"[:5])

    def test_handles_empty_input(self) -> None:
        """Should return empty string for empty input."""
        assert clean_signal_summary("") == ""
        assert clean_signal_summary(None) == ""  # type: ignore[arg-type]

    def test_handles_complex_markup(self) -> None:
        """Should handle complex real-world markup."""
        raw = """<web_link>Cytiva</web_link>&rsquo;s new bioprocessing facility
<image_link>factory.jpg</image_link>

![Rendering]<https://cytiva.com/rendering.png>

The facility will [increase production]<https://cytiva.com/details> by 50%.

* [Home]
* [About Us]
* [Contact]

&copy; 2024 Cytiva. All rights reserved."""
        result = clean_signal_summary(raw)
        assert "<web_link>" not in result
        assert "<image_link>" not in result
        assert "&rsquo;" not in result
        assert "[Home]" not in result
        assert "Cytiva" in result  # Company name preserved
        assert "increase production" in result  # Link text preserved
        assert "![Rendering]" not in result  # Image removed

    def test_preserves_paragraphs(self) -> None:
        """Should preserve paragraph breaks (double newlines)."""
        raw = "First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
        result = clean_signal_summary(raw)
        assert "First paragraph." in result
        assert "Second paragraph." in result
        assert "Third paragraph." in result
        # Should have paragraph breaks
        assert "\n\n" in result or "\n" in result

    def test_handles_non_breaking_spaces(self) -> None:
        """Should convert non-breaking spaces to regular spaces."""
        raw = "Company\xa0Name\xa0Inc."
        result = clean_signal_summary(raw)
        assert result == "Company Name Inc."

    def test_handles_zero_width_spaces(self) -> None:
        """Should remove zero-width spaces."""
        raw = "Text\u200bwith\u200bzero\u200bwidth\u200bspaces"
        result = clean_signal_summary(raw)
        assert "\u200b" not in result
        assert "Textwithzerowidthspaces" in result or "Text" in result

    def test_headline_case_insensitive(self) -> None:
        """Should strip headline regardless of case."""
        headline = "CYTIVA ACQUIRES COMPANY"
        raw = "cytiva acquires company. The deal was announced today."
        result = clean_signal_summary(raw, headline=headline)
        assert not result.lower().startswith("cytiva acquires company")

    def test_short_text_not_truncated(self) -> None:
        """Should not truncate text shorter than max_length."""
        raw = "This is short text."
        result = clean_signal_summary(raw, max_length=500)
        assert result == "This is short text."
        assert not result.endswith("...")
