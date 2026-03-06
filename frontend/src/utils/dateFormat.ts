/**
 * Robust date parsing and formatting utilities
 *
 * Handles multiple ISO 8601 date formats including:
 * - Standard ISO: "2026-03-04T16:00:00Z"
 * - With timezone offset: "2026-03-05T11:00:00-05:00"
 * - With 7-digit fractional seconds (Outlook): "2026-03-04T16:00:00.0000000"
 * - Without timezone: "2026-03-04T16:00:00"
 */

/**
 * Parse an ISO date string into a Date object, handling multiple formats.
 * Returns null if parsing fails.
 */
export function parseISODate(dateString: string | null | undefined): Date | null {
  if (!dateString) return null;

  let normalized = dateString.trim();

  // Handle Microsoft Graph API format with 7-digit fractional seconds
  // e.g., "2026-03-04T16:00:00.0000000" -> "2026-03-04T16:00:00.000Z"
  const fractionalMatch = normalized.match(/^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})\.(\d+)$/);
  if (fractionalMatch) {
    // Keep only milliseconds (3 digits)
    const ms = fractionalMatch[2].slice(0, 3).padEnd(3, '0');
    normalized = `${fractionalMatch[1]}.${ms}Z`;
  }

  // Handle 'Z' suffix
  if (normalized.endsWith('Z')) {
    normalized = normalized.replace('Z', '+00:00');
  }

  // Try parsing with the Date constructor
  const parsed = new Date(normalized);

  // Check for invalid date
  if (isNaN(parsed.getTime())) {
    // Last resort: try the original string
    const fallback = new Date(dateString);
    if (isNaN(fallback.getTime())) {
      return null;
    }
    return fallback;
  }

  return parsed;
}

/**
 * Format a date string or Date object to a time string.
 * Returns "Time TBD" if parsing fails.
 */
export function formatTime(
  dateString: string | Date | null | undefined,
  options?: {
    hour12?: boolean;
    showTimezone?: boolean;
    fallback?: string;
  }
): string {
  const fallback = options?.fallback ?? 'Time TBD';

  let date: Date | null;
  if (dateString instanceof Date) {
    date = isNaN(dateString.getTime()) ? null : dateString;
  } else {
    date = parseISODate(dateString);
  }

  if (!date) return fallback;

  try {
    return date.toLocaleTimeString([], {
      hour: options?.hour12 !== false ? 'numeric' : '2-digit',
      minute: '2-digit',
      hour12: options?.hour12 !== false,
    });
  } catch {
    return fallback;
  }
}

/**
 * Format a date string or Date object to a date string.
 * Returns empty string if parsing fails.
 */
export function formatDate(
  dateString: string | Date | null | undefined,
  options?: {
    format?: 'short' | 'long' | 'relative';
    fallback?: string;
  }
): string {
  const fallback = options?.fallback ?? '';
  const format = options?.format ?? 'short';

  let date: Date | null;
  if (dateString instanceof Date) {
    date = isNaN(dateString.getTime()) ? null : dateString;
  } else {
    date = parseISODate(dateString);
  }

  if (!date) return fallback;

  try {
    const now = new Date();
    const isToday = date.toDateString() === now.toDateString();

    const tomorrow = new Date(now);
    tomorrow.setDate(tomorrow.getDate() + 1);
    const isTomorrow = date.toDateString() === tomorrow.toDateString();

    if (format === 'relative') {
      if (isToday) return 'Today';
      if (isTomorrow) return 'Tomorrow';
    }

    if (format === 'long') {
      return date.toLocaleDateString([], {
        weekday: 'short',
        month: 'short',
        day: 'numeric',
        year: date.getFullYear() !== now.getFullYear() ? 'numeric' : undefined,
      });
    }

    return date.toLocaleDateString([], {
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return fallback;
  }
}

/**
 * Format a meeting time with both time and date components.
 */
export function formatMeetingTime(
  dateString: string | Date | null | undefined
): { time: string; date: string } {
  let date: Date | null;
  if (dateString instanceof Date) {
    date = isNaN(dateString.getTime()) ? null : dateString;
  } else {
    date = parseISODate(dateString);
  }

  if (!date) {
    return { time: 'Time TBD', date: '' };
  }

  return {
    time: formatTime(date),
    date: formatDate(date, { format: 'relative' }),
  };
}
