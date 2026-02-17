import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";
import { showError } from "@/lib/errorEvents";
import {
  handleApiError,
  isRetryableError,
  getRetryAfterMs,
  getBackoffDelay,
  redirectToLogin,
} from "@/api/errorHandler";

const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

// Retry configuration
const MAX_RETRIES = 3;

/**
 * Sleep for a specified duration
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

// Flag to prevent concurrent token refresh attempts
let isRefreshing = false;

// Response interceptor for token refresh and retry logic
apiClient.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const originalRequest = error.config as RetryableAxiosRequestConfig;

    // Handle 401 Unauthorized - token refresh
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      // If already on login page, don't attempt refresh or redirect
      if (window.location.pathname === "/login") {
        return Promise.reject(error);
      }

      // If another request is already refreshing, wait for it rather than
      // firing a second refresh call.
      if (isRefreshing) {
        return Promise.reject(error);
      }

      const refreshToken = localStorage.getItem("refresh_token");
      if (refreshToken) {
        isRefreshing = true;
        try {
          const response = await axios.post(
            `${API_BASE_URL}/api/v1/auth/refresh`,
            { refresh_token: refreshToken },
          );

          const { access_token, refresh_token: newRefreshToken } = response.data;
          localStorage.setItem("access_token", access_token);
          localStorage.setItem("refresh_token", newRefreshToken);

          originalRequest.headers.Authorization = `Bearer ${access_token}`;
          return apiClient(originalRequest);
        } catch {
          // Refresh failed — clear tokens and redirect
          showError("auth", "Session expired", "Please log in again to continue.");
          redirectToLogin();
        } finally {
          isRefreshing = false;
        }
      } else {
        // No refresh token — redirect to login
        showError("auth", "Authentication required", "Please log in to continue.");
        redirectToLogin();
      }
      return Promise.reject(error);
    }

    // Handle retryable errors with exponential back-off
    if (
      originalRequest &&
      isRetryableError(error) &&
      (originalRequest._retryCount ?? 0) < MAX_RETRIES
    ) {
      originalRequest._retryCount = originalRequest._retryCount ?? 0;

      const retryAfterDelay = getRetryAfterMs(error);
      const calculatedDelay = getBackoffDelay(originalRequest._retryCount);
      const delay = retryAfterDelay > 0 ? retryAfterDelay : calculatedDelay;

      originalRequest._retryCount += 1;

      // Notify user on first retry attempt
      if (originalRequest._retryCount === 1) {
        showError("retry", "Connection issue", `Retrying... (${originalRequest._retryCount}/${MAX_RETRIES})`);
      }

      await sleep(delay);
      return apiClient(originalRequest);
    }

    // Delegate to the centralized error handler for non-retryable errors
    handleApiError(error);

    return Promise.reject(error);
  },
);
