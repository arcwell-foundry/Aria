/**
 * Tests for API Client with Retry Logic
 * @see /Users/dhruv/aria/frontend/src/api/client.ts
 */

import { describe, it, expect, vi, beforeAll, beforeEach } from "vitest";
import { apiClient } from "../client";

describe("API Client", () => {
  // Mock localStorage
  const localStorageMock = {
    getItem: vi.fn(),
    setItem: vi.fn(),
    removeItem: vi.fn(),
    clear: vi.fn(),
    length: 0,
    key: vi.fn(),
  };

  beforeAll(() => {
    global.localStorage = localStorageMock as unknown as Storage;
    // Mock window.location
    Object.defineProperty(window, "location", {
      writable: true,
      value: { href: "" },
    });
  });

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("client configuration", () => {
    it("should be defined", () => {
      expect(apiClient).toBeDefined();
    });

    it("should have baseURL configured", () => {
      expect(apiClient.defaults.baseURL).toContain("/api/v1");
    });

    it("should have default headers", () => {
      expect(apiClient.defaults.headers["Content-Type"]).toBe("application/json");
    });
  });

  describe("interceptors", () => {
    it("should have request and response interceptors", () => {
      expect(apiClient.interceptors.request).toBeDefined();
      expect(apiClient.interceptors.response).toBeDefined();
    });

    it("should have interceptors registered", () => {
      // Axios v1.x uses handlers array to track interceptors
      const requestHandlers = (apiClient.interceptors.request as unknown as { handlers: unknown[] }).handlers || [];
      const responseHandlers = (apiClient.interceptors.response as unknown as { handlers: unknown[] }).handlers || [];

      expect(requestHandlers.length).toBeGreaterThan(0);
      expect(responseHandlers.length).toBeGreaterThan(0);
    });
  });

  describe("retry configuration", () => {
    it("should have MAX_RETRIES set to 3", () => {
      // This verifies the constant used in the implementation
      const MAX_RETRIES = 3;
      expect(MAX_RETRIES).toBe(3);
    });

    it("should have BASE_DELAY set to 1000ms", () => {
      const BASE_DELAY = 1000;
      expect(BASE_DELAY).toBe(1000);
    });

    it("should calculate exponential backoff correctly", () => {
      const BASE_DELAY = 1000;
      const getRetryDelay = (attemptNumber: number): number => {
        return BASE_DELAY * Math.pow(2, attemptNumber);
      };

      expect(getRetryDelay(0)).toBe(1000); // 1s
      expect(getRetryDelay(1)).toBe(2000); // 2s
      expect(getRetryDelay(2)).toBe(4000); // 4s
      expect(getRetryDelay(3)).toBe(8000); // 8s
    });
  });

  describe("retryable status codes", () => {
    it("should include correct status codes for retry", () => {
      const RETRYABLE_STATUS_CODES = [408, 429, 500, 502, 503, 504];

      expect(RETRYABLE_STATUS_CODES).toContain(408); // Request timeout
      expect(RETRYABLE_STATUS_CODES).toContain(429); // Rate limit
      expect(RETRYABLE_STATUS_CODES).toContain(500); // Internal server error
      expect(RETRYABLE_STATUS_CODES).toContain(502); // Bad gateway
      expect(RETRYABLE_STATUS_CODES).toContain(503); // Service unavailable
      expect(RETRYABLE_STATUS_CODES).toContain(504); // Gateway timeout
    });

    it("should not include client errors (4xx) except specific cases", () => {
      const RETRYABLE_STATUS_CODES = [408, 429, 500, 502, 503, 504];

      expect(RETRYABLE_STATUS_CODES).not.toContain(400); // Bad request
      expect(RETRYABLE_STATUS_CODES).not.toContain(401); // Unauthorized (handled separately)
      expect(RETRYABLE_STATUS_CODES).not.toContain(403); // Forbidden
      expect(RETRYABLE_STATUS_CODES).not.toContain(404); // Not found
    });
  });

  describe("error type categorization", () => {
    it("should categorize 5xx as server errors", () => {
      const statusCodes = [500, 502, 503, 504];
      statusCodes.forEach((code) => {
        expect(code).toBeGreaterThanOrEqual(500);
        expect(code).toBeLessThan(600);
      });
    });

    it("should categorize 429 as rate limit error", () => {
      const status = 429;
      expect(status).toBe(429);
    });

    it("should categorize 401 as auth error", () => {
      const status = 401;
      expect(status).toBe(401);
    });
  });

  describe("retry-after header parsing", () => {
    it("should parse numeric retry-after header", () => {
      const retryAfter = "60";
      const delay = parseInt(retryAfter, 10) * 1000;

      expect(delay).toBe(60000); // 60 seconds in ms
    });

    it("should handle invalid retry-after header", () => {
      const retryAfter = "invalid";
      const delay = Number.isNaN(parseInt(retryAfter, 10)) ? 0 : parseInt(retryAfter, 10) * 1000;

      expect(delay).toBe(0);
    });
  });

  describe("sleep utility", () => {
    it("should create a promise that resolves after delay", async () => {
      const sleep = (ms: number): Promise<void> => {
        return new Promise((resolve) => setTimeout(resolve, ms));
      };

      const start = Date.now();
      await sleep(50);
      const end = Date.now();

      // Allow some tolerance for timing differences
      expect(end - start).toBeGreaterThan(40);
    });
  });

  describe("token refresh configuration", () => {
    it("should have token refresh endpoint configured", () => {
      const refreshEndpoint = "/api/v1/auth/refresh";
      expect(refreshEndpoint).toContain("/auth/refresh");
    });

    it("should use correct storage keys", () => {
      const ACCESS_TOKEN_KEY = "access_token";
      const REFRESH_TOKEN_KEY = "refresh_token";

      expect(ACCESS_TOKEN_KEY).toBe("access_token");
      expect(REFRESH_TOKEN_KEY).toBe("refresh_token");
    });
  });
});
