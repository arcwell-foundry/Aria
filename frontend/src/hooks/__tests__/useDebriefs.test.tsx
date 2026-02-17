/**
 * Tests for Debrief React Query Hooks
 * @see /Users/dhruv/aria/frontend/src/hooks/useDebriefs.ts
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

import type { Debrief } from "@/api/debriefs";

// Mock the API functions
vi.mock("@/api/debriefs", () => ({
  getDebrief: vi.fn(),
  updateDebrief: vi.fn(),
}));

import { getDebrief, updateDebrief } from "@/api/debriefs";
import { useDebrief, useUpdateDebrief, debriefKeys } from "../useDebriefs";

// Create wrapper with QueryClient
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
  };
}

// Mock debrief data
const mockDebrief: Debrief = {
  id: "debrief-123",
  meeting_id: "meeting-456",
  user_id: "user-1",
  title: "Discovery Call with Acme",
  occurred_at: "2026-02-17T10:00:00Z",
  attendees: ["John Smith"],
  outcome: null,
  notes: null,
  created_at: "2026-02-17T10:00:00Z",
  updated_at: "2026-02-17T10:00:00Z",
};

describe("useDebriefs hooks", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("debriefKeys", () => {
    it("should generate correct query keys", () => {
      expect(debriefKeys.all).toEqual(["debriefs"]);
      expect(debriefKeys.details()).toEqual(["debriefs", "detail"]);
      expect(debriefKeys.detail("meeting-123")).toEqual(["debriefs", "detail", "meeting-123"]);
    });
  });

  describe("useDebrief", () => {
    it("should fetch debrief by meeting ID", async () => {
      vi.mocked(getDebrief).mockResolvedValueOnce(mockDebrief);

      const { result } = renderHook(() => useDebrief("meeting-456"), {
        wrapper: createWrapper(),
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(result.current.data).toEqual(mockDebrief);
      expect(getDebrief).toHaveBeenCalledWith("meeting-456");
    });

    it("should not fetch when meetingId is empty", () => {
      const { result } = renderHook(() => useDebrief(""), {
        wrapper: createWrapper(),
      });

      expect(result.current.isFetching).toBe(false);
      expect(getDebrief).not.toHaveBeenCalled();
    });
  });

  describe("useUpdateDebrief", () => {
    it("should call updateDebrief with correct parameters", async () => {
      const mockUpdatedDebrief: Debrief = {
        ...mockDebrief,
        outcome: "positive",
        notes: "Great meeting",
        ai_analysis: {
          summary: "Positive call",
          action_items: [],
          commitments: { ours: [], theirs: [] },
          insights: [],
        },
      };

      vi.mocked(updateDebrief).mockResolvedValueOnce(mockUpdatedDebrief);

      const { result } = renderHook(() => useUpdateDebrief(), {
        wrapper: createWrapper(),
      });

      result.current.mutate({
        debriefId: "debrief-123",
        data: { outcome: "positive", notes: "Great meeting" },
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(updateDebrief).toHaveBeenCalledWith("debrief-123", {
        outcome: "positive",
        notes: "Great meeting",
      });
    });
  });
});
