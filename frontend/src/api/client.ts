import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";
import { showError } from "@/lib/errorEvents";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Retry configuration
const MAX_RETRIES = 3;
const BASE_DELAY = 1000; // 1 second

// Status codes that should trigger a retry
const RETRYABLE_STATUS_CODES = [408, 429, 500, 502, 503, 504];

/**
 * Calculate delay with exponential backoff
 * @param attemptNumber - The retry attempt number (0-based)
 * @returns Delay in milliseconds
 */
function getRetryDelay(attemptNumber: number): number {
  return BASE_DELAY * Math.pow(2, attemptNumber);
}

/**
 * Check if error is retryable based on status code or network error
 * @param error - The axios error
 * @returns True if the error should be retried
 */
function isRetryableError(error: AxiosError): boolean {
  // Network errors (no response) are retryable
  if (!error.response) {
    return true;
  }

  // Check for retryable status codes
  return RETRYABLE_STATUS_CODES.includes(error.response.status);
}

/**
 * Get retry delay from retry-after header if present
 * @param error - The axios error
 * @returns Delay in milliseconds from header or 0
 */
function getRetryAfterDelay(error: AxiosError): number {
  const retryAfter = error.response?.headers["retry-after"];
  if (typeof retryAfter === "string") {
    const seconds = parseInt(retryAfter, 10);
    if (!Number.isNaN(seconds)) {
      return seconds * 1000;
    }
  }
  return 0;
}

/**
 * Sleep for a specified duration
 * @param ms - Milliseconds to sleep
 */
function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/**
 * Extended axios request config with retry metadata
 */
interface RetryableAxiosRequestConfig extends InternalAxiosRequestConfig {
  _retry?: boolean;
  _retryCount?: number;
}

export const apiClient = axios.create({
  baseURL: `${API_BASE_URL}/api/v1`,
  timeout: 30_000,
  headers: {
    "Content-Type": "application/json",
  },
});

// Request interceptor to add auth token
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor for token refresh and retry logic
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as RetryableAxiosRequestConfig;

    // Handle 401 Unauthorized - token refresh
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      const refreshToken = localStorage.getItem("refresh_token");
      if (refreshToken) {
        try {
          const response = await axios.post(
            `${API_BASE_URL}/api/v1/auth/refresh`,
            { refresh_token: refreshToken }
          );

          const { access_token, refresh_token: newRefreshToken } =
            response.data;
          localStorage.setItem("access_token", access_token);
          localStorage.setItem("refresh_token", newRefreshToken);

          originalRequest.headers.Authorization = `Bearer ${access_token}`;
          return apiClient(originalRequest);
        } catch {
          // Refresh failed, clear tokens and redirect to login
          localStorage.removeItem("access_token");
          localStorage.removeItem("refresh_token");
          showError(
            "auth",
            "Session expired",
            "Please log in again to continue."
          );
          window.location.href = "/login";
        }
      } else {
        // No refresh token, redirect to login
        showError(
          "auth",
          "Authentication required",
          "Please log in to continue."
        );
        window.location.href = "/login";
      }
      return Promise.reject(error);
    }

    // Handle retryable errors with exponential backoff
    if (
      originalRequest &&
      isRetryableError(error) &&
      (originalRequest._retryCount ?? 0) < MAX_RETRIES
    ) {
      // Initialize retry count if not set
      originalRequest._retryCount = originalRequest._retryCount ?? 0;

      // Check for retry-after header (especially for 429)
      const retryAfterDelay = getRetryAfterDelay(error);
      const calculatedDelay = getRetryDelay(originalRequest._retryCount);
      const delay = retryAfterDelay > 0 ? retryAfterDelay : calculatedDelay;

      // Increment retry count
      originalRequest._retryCount += 1;

      // Show retry notification for user feedback
      const retryNumber = originalRequest._retryCount;
      if (retryNumber === 1) {
        showError(
          "retry",
          "Connection issue",
          `Retrying... (${retryNumber}/${MAX_RETRIES})`
        );
      }

      // Wait before retrying
      await sleep(delay);

      // Retry the request
      return apiClient(originalRequest);
    }

    // Show error notification for non-retryable errors
    if (error.response) {
      const status = error.response.status;
      const statusText = error.response.statusText || "Unknown error";

      if (status >= 500) {
        showError(
          "server",
          "Server error",
          `The server encountered an error (${status}). Please try again.`
        );
      } else if (status === 429) {
        showError(
          "rate_limit",
          "Too many requests",
          "You're making too many requests. Please wait a moment."
        );
      } else if (status === 403) {
        showError(
          "permission",
          "Access denied",
          "You don't have permission to perform this action."
        );
      } else if (status === 404) {
        showError(
          "not_found",
          "Not found",
          "The requested resource was not found."
        );
      } else if (status >= 400 && status < 500) {
        showError(
          "client",
          "Request error",
          `${statusText}. Please check your request and try again.`
        );
      }
    } else if (error.request) {
      // Network error (request made but no response received)
      showError(
        "network",
        "Network error",
        "Unable to connect to the server. Please check your internet connection."
      );
    }

    return Promise.reject(error);
  }
);
