/**
 * Centralized API Error Handler
 *
 * Intercepts all API errors and routes them to the appropriate handling:
 * - 401 → redirect to login
 * - 429 → show rate limit message
 * - 500 → show retry option
 * - Network error → show offline indicator
 *
 * Used by the Axios response interceptor in client.ts.
 */

import type { AxiosError } from "axios";
import { showError } from "@/lib/errorEvents";

/** Redirect to login, clearing tokens. Prevents concurrent redirects. */
let isRedirectingToLogin = false;

export function redirectToLogin(): void {
  if (isRedirectingToLogin) return;
  if (window.location.pathname === "/login") return;

  isRedirectingToLogin = true;
  localStorage.removeItem("access_token");
  localStorage.removeItem("refresh_token");
  window.location.href = "/login";
}

/** Reset the redirect guard (e.g. after successful login). */
export function resetRedirectGuard(): void {
  isRedirectingToLogin = false;
}

/** Status codes eligible for automatic retry with back-off. */
export const RETRYABLE_STATUS_CODES = [408, 429, 500, 502, 503, 504];

/**
 * Determine whether an Axios error is retryable.
 */
export function isRetryableError(error: AxiosError): boolean {
  // Network errors (no response) are retryable
  if (!error.response) return true;
  return RETRYABLE_STATUS_CODES.includes(error.response.status);
}

/**
 * Parse `Retry-After` header into milliseconds.
 * Returns 0 when the header is absent or unparseable.
 */
export function getRetryAfterMs(error: AxiosError): number {
  const retryAfter = error.response?.headers["retry-after"];
  if (typeof retryAfter === "string") {
    const seconds = parseInt(retryAfter, 10);
    if (!Number.isNaN(seconds)) return seconds * 1000;
  }
  return 0;
}

/**
 * Exponential back-off delay.
 * @param attempt 0-based retry attempt number
 * @param baseMs  base delay in milliseconds (default 1 000)
 */
export function getBackoffDelay(attempt: number, baseMs = 1000): number {
  return baseMs * Math.pow(2, attempt);
}

/**
 * Handle a non-retryable API error by showing the appropriate
 * user-facing notification via the error event system.
 *
 * Background/non-user-initiated requests (marked with X-Background: true header)
 * will NOT show error toasts — only auth errors and network errors are shown
 * since those affect the entire session.
 *
 * Returns `true` when a notification was emitted so callers can
 * decide whether to add their own handling.
 */
export function handleApiError(error: AxiosError): boolean {
  // Check if this was a background request — suppress most toasts
  const isBackground = error.config?.headers?.["X-Background"] === "true";

  if (error.response) {
    const { status } = error.response;
    const statusText = error.response.statusText || "Unknown error";

    if (status === 401) {
      showError("auth", "Authentication required", "Please log in to continue.");
      redirectToLogin();
      return true;
    }

    // Suppress non-critical toasts for background fetches
    if (isBackground) {
      return false;
    }

    if (status === 429) {
      showError(
        "rate_limit",
        "Too many requests",
        "You're sending requests too quickly. Please wait a moment and try again.",
      );
      return true;
    }

    if (status === 403) {
      showError("permission", "Access denied", "You don't have permission to perform this action.");
      return true;
    }

    if (status === 404) {
      showError("not_found", "Not found", "The requested resource was not found.");
      return true;
    }

    if (status >= 500) {
      showError(
        "server",
        "Server error",
        `The server encountered an error (${status}). Please try again.`,
      );
      return true;
    }

    if (status >= 400) {
      showError("client", "Request error", `${statusText}. Please check your request and try again.`);
      return true;
    }
  } else if (error.request) {
    // Network errors affect the entire session — always show
    const isOffline = typeof navigator !== "undefined" && !navigator.onLine;
    showError(
      "network",
      isOffline ? "You are offline" : "Network error",
      isOffline
        ? "Your internet connection appears to be down. Changes will sync when you reconnect."
        : "Unable to connect to the server. Please check your internet connection.",
    );
    return true;
  }

  return false;
}

/**
 * Report a client-side error to the backend feedback endpoint.
 * Fire-and-forget; failures are silently logged to the console.
 */
export async function reportErrorToBackend(error: Error, context?: string): Promise<void> {
  try {
    const token = localStorage.getItem("access_token");
    if (!token) return; // Can't report without auth

    const apiBase = import.meta.env.VITE_API_URL || "http://localhost:8000";
    await fetch(`${apiBase}/api/v1/feedback/general`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        type: "bug",
        message: `[Auto-reported] ${error.name}: ${error.message}\n\nStack: ${error.stack?.slice(0, 1500) ?? "N/A"}`,
        page: context ?? window.location.pathname,
      }),
    });
  } catch {
    // Swallow — we don't want error reporting to cause more errors
    console.warn("[errorHandler] Failed to report error to backend");
  }
}
