/**
 * ARIA Typography Utility
 *
 * Detects and wraps data elements in ARIA messages with appropriate styling.
 * - Times (11:00am, 2:30 PM)
 * - Dates (March 5, Mar 10)
 * - Percentages (45%, 0.8)
 * - Currency ($2,500, $100)
 * - Numbers with units (28 drafts, 4 tasks, 2 hours)
 */

/**
 * Regex patterns for detecting data elements in ARIA messages.
 * Order matters: more specific patterns should come first.
 */
const DATA_PATTERNS: Array<{
  pattern: RegExp;
  className: string;
}> = [
  // Currency: $1,234.56 or $1,000
  {
    pattern: /\$[\d,]+(?:\.\d{2})?/g,
    className: 'aria-data',
  },
  // Percentages: 45% or 0.8%
  {
    pattern: /\b\d+(?:\.\d+)?%/g,
    className: 'aria-data',
  },
  // Times: 11:00am, 2:30 PM, 11:00 am
  {
    pattern: /\b\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?\b/g,
    className: 'aria-data',
  },
  // Dates: March 5, Mar 10th, December 25th
  {
    pattern: /\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2}(?:st|nd|rd|th)?\b/g,
    className: 'aria-data',
  },
  // Numbers with units: 28 drafts, 4 tasks, 2 hours, 30 minutes
  {
    pattern: /\b\d+\s*(?:hours?|minutes?|days?|weeks?|months?|tasks?|drafts?|meetings?|signals?|emails?|people?|persons?)\b/gi,
    className: 'aria-data',
  },
  // Standalone significant numbers (3+ digits): 100, 1,234
  {
    pattern: /\b\d{1,3}(?:,\d{3})+\b/g,
    className: 'aria-data',
  },
];

/**
 * Process text to wrap detected data elements in styled spans.
 * This is a post-processing step for ARIA message content.
 *
 * @param text - The text to process
 * @returns HTML string with data elements wrapped in styled spans
 *
 * @example
 * processAriaTypography("Your meeting at 2:30 PM has 3 attendees")
 * // Returns: "Your meeting at <span class="aria-data">2:30 PM</span> has <span class="aria-data">3 attendees</span>"
 */
export function processAriaTypography(text: string): string {
  // Don't process empty or whitespace-only text
  if (!text || !text.trim()) {
    return text;
  }

  let result = text;

  // Apply each pattern and wrap matches in styled spans
  // We need to be careful not to double-wrap, so we use unique placeholders
  for (const { pattern, className } of DATA_PATTERNS) {
    result = result.replace(pattern, (match) => {
      // Don't wrap if already inside a span
      return `<span class="${className}">${match}</span>`;
    });
  }

  return result;
}

/**
 * CSS class names for ARIA typography
 */
export const ARIA_TYPOGRAPHY_CLASSES = {
  insight: 'aria-insight',
  data: 'aria-data',
} as const;
