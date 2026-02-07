/**
 * Tests for Error Event System
 * @see /Users/dhruv/aria/frontend/src/lib/errorEvents.ts
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  showError,
  onError,
  clearAllErrorListeners,
  getIconForErrorType,
  getColorForErrorType,
  getDismissDelay,
  type ErrorEvent,
} from "../errorEvents";

describe("Error Event System", () => {
  beforeEach(() => {
    // Clear all listeners before each test
    clearAllErrorListeners();
  });

  afterEach(() => {
    // Clean up after each test
    clearAllErrorListeners();
  });

  describe("showError", () => {
    it("should create error event with correct structure", () => {
      const listener = vi.fn();
      onError(listener);

      showError("network", "Test error", "Test description");

      expect(listener).toHaveBeenCalledTimes(1);

      const errorEvent = listener.mock.calls[0][0] as ErrorEvent;
      expect(errorEvent.type).toBe("network");
      expect(errorEvent.title).toBe("Test error");
      expect(errorEvent.description).toBe("Test description");
      expect(errorEvent.timestamp).toBeTypeOf("number");
      expect(errorEvent.id).toMatch(/^error-\d+-[a-z0-9]+$/);
    });

    it("should notify all registered listeners", () => {
      const listener1 = vi.fn();
      const listener2 = vi.fn();
      const listener3 = vi.fn();

      onError(listener1);
      onError(listener2);
      onError(listener3);

      showError("auth", "Auth error", "Please log in");

      expect(listener1).toHaveBeenCalledTimes(1);
      expect(listener2).toHaveBeenCalledTimes(1);
      expect(listener3).toHaveBeenCalledTimes(1);
    });

    it("should handle listener errors gracefully", () => {
      const errorListener = vi.fn(() => {
        throw new Error("Listener error");
      });
      const normalListener = vi.fn();

      onError(errorListener);
      onError(normalListener);

      // Should not throw despite listener error
      expect(() => {
        showError("test", "Test", "Description");
      }).not.toThrow();

      // Normal listener should still be called
      expect(normalListener).toHaveBeenCalledTimes(1);
    });
  });

  describe("onError", () => {
    it("should register listener and return unsubscribe function", () => {
      const listener = vi.fn();
      const unsubscribe = onError(listener);

      expect(typeof unsubscribe).toBe("function");

      showError("test", "Test", "Description");
      expect(listener).toHaveBeenCalledTimes(1);

      unsubscribe();

      showError("test", "Test 2", "Description 2");
      expect(listener).toHaveBeenCalledTimes(1); // Should not increase
    });

    it("should allow removing specific listener", () => {
      const listener1 = vi.fn();
      const listener2 = vi.fn();

      const unsubscribe1 = onError(listener1);
      onError(listener2);

      unsubscribe1();

      showError("test", "Test", "Description");

      expect(listener1).not.toHaveBeenCalled();
      expect(listener2).toHaveBeenCalledTimes(1);
    });

    it("should support multiple independent subscriptions", () => {
      const listener1 = vi.fn();
      const listener2 = vi.fn();
      const listener3 = vi.fn();

      const unsub1 = onError(listener1);
      const unsub2 = onError(listener2);
      onError(listener3);

      // Remove middle listener
      unsub2();

      showError("test", "Test 1", "Description 1");

      expect(listener1).toHaveBeenCalledTimes(1);
      expect(listener2).not.toHaveBeenCalled();
      expect(listener3).toHaveBeenCalledTimes(1);

      // Remove first listener
      unsub1();

      showError("test", "Test 2", "Description 2");

      expect(listener1).toHaveBeenCalledTimes(1); // No increase
      expect(listener2).not.toHaveBeenCalled();
      expect(listener3).toHaveBeenCalledTimes(2); // Increased
    });
  });

  describe("clearAllErrorListeners", () => {
    it("should remove all registered listeners", () => {
      const listener1 = vi.fn();
      const listener2 = vi.fn();

      onError(listener1);
      onError(listener2);

      clearAllErrorListeners();

      showError("test", "Test", "Description");

      expect(listener1).not.toHaveBeenCalled();
      expect(listener2).not.toHaveBeenCalled();
    });
  });

  describe("getIconForErrorType", () => {
    it("should return correct icon for each error type", () => {
      expect(getIconForErrorType("auth")).toBe("Lock");
      expect(getIconForErrorType("network")).toBe("WifiOff");
      expect(getIconForErrorType("server")).toBe("Server");
      expect(getIconForErrorType("client")).toBe("AlertTriangle");
      expect(getIconForErrorType("retry")).toBe("RefreshCw");
      expect(getIconForErrorType("rate_limit")).toBe("Clock");
      expect(getIconForErrorType("permission")).toBe("ShieldAlert");
      expect(getIconForErrorType("not_found")).toBe("SearchX");
      expect(getIconForErrorType("validation")).toBe("AlertCircle");
    });
  });

  describe("getColorForErrorType", () => {
    it("should return correct colors for auth errors", () => {
      const colors = getColorForErrorType("auth");
      expect(colors.bg).toBe("bg-amber-500/10");
      expect(colors.border).toBe("border-amber-500/20");
      expect(colors.icon).toBe("text-amber-400");
    });

    it("should return correct colors for network errors", () => {
      const colors = getColorForErrorType("network");
      expect(colors.bg).toBe("bg-orange-500/10");
      expect(colors.border).toBe("border-orange-500/20");
      expect(colors.icon).toBe("text-orange-400");
    });

    it("should return correct colors for retry errors", () => {
      const colors = getColorForErrorType("retry");
      expect(colors.bg).toBe("bg-blue-500/10");
      expect(colors.border).toBe("border-blue-500/20");
      expect(colors.icon).toBe("text-blue-400");
    });

    it("should return correct colors for rate limit errors", () => {
      const colors = getColorForErrorType("rate_limit");
      expect(colors.bg).toBe("bg-purple-500/10");
      expect(colors.border).toBe("border-purple-500/20");
      expect(colors.icon).toBe("text-purple-400");
    });

    it("should return correct colors for server errors", () => {
      const colors = getColorForErrorType("server");
      expect(colors.bg).toBe("bg-red-500/10");
      expect(colors.border).toBe("border-red-500/20");
      expect(colors.icon).toBe("text-red-400");
    });
  });

  describe("getDismissDelay", () => {
    it("should return short delay for retry errors", () => {
      expect(getDismissDelay("retry")).toBe(2000);
    });

    it("should return long delay for auth errors", () => {
      expect(getDismissDelay("auth")).toBe(6000);
    });

    it("should return default delay for other errors", () => {
      expect(getDismissDelay("network")).toBe(4000);
      expect(getDismissDelay("server")).toBe(4000);
      expect(getDismissDelay("client")).toBe(4000);
    });
  });

  describe("error event ID generation", () => {
    it("should generate unique IDs for each error", () => {
      const listener = vi.fn();
      onError(listener);

      showError("test", "Error 1", "Description 1");
      showError("test", "Error 2", "Description 2");

      const id1 = listener.mock.calls[0][0].id;
      const id2 = listener.mock.calls[1][0].id;

      expect(id1).not.toBe(id2);
      expect(id1).toMatch(/^error-\d+-[a-z0-9]+$/);
      expect(id2).toMatch(/^error-\d+-[a-z0-9]+$/);
    });
  });
});
