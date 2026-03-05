/**
 * sanitizeSignalText - Frontend safety net for signal/insight card text
 *
 * Removes web scraping markup that might slip through backend cleaning.
 * This is a defensive measure to ensure raw markup is never displayed.
 */

// HTML entity decoding map
const HTML_ENTITIES: Record<string, string> = {
  '&rsquo;': "'",
  '&lsquo;': "'",
  '&rdquo;': '"',
  '&ldquo;': '"',
  '&apos;': "'",
  '&quot;': '"',
  '&amp;': '&',
  '&nbsp;': ' ',
  '&#39;': "'",
  '&#x27;': "'",
  '&#34;': '"',
  '&#x22;': '"',
};

/**
 * Sanitizes signal/insight text for display in cards
 *
 * Cleaning steps:
 * 1. Remove <web_link> tags and their bracket wrappers
 * 2. Remove <image_link> tags and their bracket wrappers
 * 3. Decode HTML entities
 * 4. Remove markdown image syntax
 * 5. Collapse whitespace
 * 6. Truncate to max length (default 300 chars for card view)
 */
export function sanitizeSignalText(text: string, maxLength = 300): string {
  if (!text || typeof text !== 'string') {
    return '';
  }

  let cleaned = text;

  // 1. Remove <web_link> tags with content: [<web_link>...</web_link>](url)
  cleaned = cleaned.replace(/\[<web_link>[^\]]*<\/web_link>\]\([^)]*\)/gi, '');

  // 2. Remove standalone <web_link>...</web_link> tags
  cleaned = cleaned.replace(/<web_link[^>]*>[\s\S]*?<\/web_link>/gi, '');

  // 3. Remove <image_link> tags with content
  cleaned = cleaned.replace(/\[<image_link>[^\]]*<\/image_link>\]\([^)]*\)/gi, '');
  cleaned = cleaned.replace(/<image_link[^>]*>[\s\S]*?<\/image_link>/gi, '');

  // 4. Remove any remaining angle-bracket tags (navigation artifacts)
  cleaned = cleaned.replace(/<[^>]+>/g, '');

  // 5. Decode HTML entities
  for (const [entity, char] of Object.entries(HTML_ENTITIES)) {
    cleaned = cleaned.split(entity).join(char);
  }
  // Handle numeric entities like &#39; &#x27; etc.
  cleaned = cleaned.replace(/&#(\d+);/g, (_, code) =>
    String.fromCharCode(parseInt(code, 10))
  );
  cleaned = cleaned.replace(/&#x([0-9a-fA-F]+);/g, (_, code) =>
    String.fromCharCode(parseInt(code, 16))
  );

  // 6. Remove markdown image syntax: ![alt](url)
  cleaned = cleaned.replace(/!\[.*?\]\([^)]*\)/g, '');

  // 7. Remove markdown links but keep the text: [text](url) -> text
  cleaned = cleaned.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1');

  // 8. Remove markdown without URL: [link text](no-url) patterns
  cleaned = cleaned.replace(/\[([^\]]+)\]\([^)]*\)/gi, '$1');

  // 9. Remove orphaned brackets from broken markdown
  cleaned = cleaned.replace(/\[\s*\]/g, '');

  // 10. Remove stock tickers like $NASDAQ, $NYSE
  cleaned = cleaned.replace(/\$[A-Z]{2,6}\b/g, '');

  // 11. Collapse multiple whitespace to single space
  cleaned = cleaned.replace(/\s+/g, ' ').trim();

  // 12. Truncate to max length, preserving word boundary
  if (cleaned.length > maxLength) {
    cleaned = cleaned.slice(0, maxLength);
    const lastSpace = cleaned.lastIndexOf(' ');
    if (lastSpace > maxLength * 0.7) {
      cleaned = cleaned.slice(0, lastSpace);
    }
    cleaned = cleaned.trim() + '...';
  }

  return cleaned;
}

export default sanitizeSignalText;
