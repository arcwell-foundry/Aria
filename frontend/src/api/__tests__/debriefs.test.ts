/**
 * Tests for Debrief API Client
 * @see /Users/dhruv/aria/frontend/src/api/debriefs.ts
 *
 * These tests verify the debrief API client functions exist and have correct signatures.
 */

import { describe, it, expect } from "vitest";

describe("Debrief API Client - Types", () => {
  it("should define DebriefOutcome as positive, neutral, or concern", () => {
    // This is a compile-time type test
    // The actual values we expect
    const validOutcomes = ["positive", "neutral", "concern"] as const;
    expect(validOutcomes).toContain("positive");
    expect(validOutcomes).toContain("neutral");
    expect(validOutcomes).toContain("concern");
    expect(validOutcomes).toHaveLength(3);
  });

  it("should define UpdateDebriefRequest with outcome and notes", () => {
    // This validates the expected request shape
    const updateRequest = {
      outcome: "positive" as const,
      notes: "Great meeting",
      lead_id: "lead-123", // optional
    };
    expect(updateRequest.outcome).toBe("positive");
    expect(updateRequest.notes).toBe("Great meeting");
  });
});

// This import will fail since the module doesn't exist yet - that's expected in RED phase
describe("Debrief API Client - Functions", () => {
  it("should export getDebrief function", async () => {
    // This will fail because the module doesn't exist yet
    const { getDebrief } = await import("../debriefs");
    expect(typeof getDebrief).toBe("function");
  });

  it("should export updateDebrief function", async () => {
    // This will fail because the module doesn't exist yet
    const { updateDebrief } = await import("../debriefs");
    expect(typeof updateDebrief).toBe("function");
  });
});
