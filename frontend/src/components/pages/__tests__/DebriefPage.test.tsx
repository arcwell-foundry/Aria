/**
 * Tests for DebriefPage component
 * @see /Users/dhruv/aria/frontend/src/components/pages/DebriefPage.tsx
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";

import type { Debrief } from "@/api/debriefs";

// Mock the hooks
vi.mock("@/hooks/useDebriefs", () => ({
  useDebrief: vi.fn(),
  useUpdateDebrief: vi.fn(),
}));

import { useDebrief, useUpdateDebrief } from "@/hooks/useDebriefs";
import { DebriefPage } from "../DebriefPage";

// Mock data
const mockDebrief: Debrief = {
  id: "debrief-123",
  meeting_id: "meeting-456",
  user_id: "user-1",
  title: "Discovery Call with Acme Corp",
  occurred_at: "2026-02-17T10:00:00Z",
  attendees: ["John Smith", "Jane Doe"],
  lead_id: "lead-789",
  lead_name: "Acme Corp",
  outcome: null,
  notes: null,
  created_at: "2026-02-17T10:00:00Z",
  updated_at: "2026-02-17T10:00:00Z",
};

// Create wrapper with QueryClient and Router
function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return function Wrapper({
    children,
    initialEntries = ["/debriefs/new?meeting_id=meeting-456"],
  }: {
    children: ReactNode;
    initialEntries?: string[];
  }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={initialEntries}>
          {children}
        </MemoryRouter>
      </QueryClientProvider>
    );
  };
}

// Helper to mock useDebrief
function mockUseDebriefLoading() {
  vi.mocked(useDebrief).mockReturnValue({
    data: undefined,
    isLoading: true,
    error: null,
    isError: false,
    isSuccess: false,
    isPending: true,
    isFetching: true,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof useDebrief>);
}

function mockUseDebriefLoaded(data: Debrief) {
  vi.mocked(useDebrief).mockReturnValue({
    data,
    isLoading: false,
    error: null,
    isError: false,
    isSuccess: true,
    isPending: false,
    isFetching: false,
    refetch: vi.fn(),
  } as unknown as ReturnType<typeof useDebrief>);
}

function mockUseUpdateDebrief(mutateAsync?: ReturnType<typeof vi.fn>) {
  vi.mocked(useUpdateDebrief).mockReturnValue({
    mutate: vi.fn(),
    mutateAsync: mutateAsync ?? vi.fn(),
    isPending: false,
    isError: false,
    isSuccess: false,
    reset: vi.fn(),
  } as unknown as ReturnType<typeof useUpdateDebrief>);
}

describe("DebriefPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("loading state", () => {
    it("should show loading skeleton while fetching debrief", () => {
      mockUseDebriefLoading();
      mockUseUpdateDebrief();

      render(<DebriefPage />, { wrapper: createWrapper() });

      // Should show loading skeleton
      expect(screen.getByTestId("debrief-loading") || document.querySelector(".animate-pulse")).toBeTruthy();
    });
  });

  describe("loaded state", () => {
    it("should display meeting title and attendees", () => {
      mockUseDebriefLoaded(mockDebrief);
      mockUseUpdateDebrief();

      render(<DebriefPage />, { wrapper: createWrapper() });

      expect(screen.getByText("Discovery Call with Acme Corp")).toBeTruthy();
      expect(screen.getByText(/John Smith/)).toBeTruthy();
      expect(screen.getByText(/Jane Doe/)).toBeTruthy();
    });

    it("should display lead badge if linked", () => {
      mockUseDebriefLoaded(mockDebrief);
      mockUseUpdateDebrief();

      render(<DebriefPage />, { wrapper: createWrapper() });

      expect(screen.getByText("Acme Corp")).toBeTruthy();
    });

    it("should show three outcome buttons", () => {
      mockUseDebriefLoaded(mockDebrief);
      mockUseUpdateDebrief();

      render(<DebriefPage />, { wrapper: createWrapper() });

      // Check for outcome buttons
      expect(screen.getByRole("button", { name: /positive/i })).toBeTruthy();
      expect(screen.getByRole("button", { name: /neutral/i })).toBeTruthy();
      expect(screen.getByRole("button", { name: /concern/i })).toBeTruthy();
    });

    it("should show notes textarea with placeholder", () => {
      mockUseDebriefLoaded(mockDebrief);
      mockUseUpdateDebrief();

      render(<DebriefPage />, { wrapper: createWrapper() });

      const textarea = screen.getByPlaceholderText(/What happened/i);
      expect(textarea).toBeTruthy();
    });
  });

  describe("submission", () => {
    it("should call updateDebrief when outcome and notes are submitted", async () => {
      const user = userEvent.setup();
      const mockMutateAsync = vi.fn().mockResolvedValue({
        ...mockDebrief,
        outcome: "positive",
        notes: "Great meeting with strong interest",
        ai_analysis: {
          summary: "Positive call",
          action_items: [],
          commitments: { ours: [], theirs: [] },
          insights: [],
        },
      });

      mockUseDebriefLoaded(mockDebrief);
      mockUseUpdateDebrief(mockMutateAsync);

      render(<DebriefPage />, { wrapper: createWrapper() });

      // Click positive outcome
      const positiveBtn = screen.getByRole("button", { name: /positive/i });
      await user.click(positiveBtn);

      // Type notes
      const textarea = screen.getByPlaceholderText(/What happened/i);
      await user.type(textarea, "Great meeting with strong interest");

      // Submit
      const submitBtn = screen.getByRole("button", { name: /process debrief/i });
      await user.click(submitBtn);

      await waitFor(() => {
        expect(mockMutateAsync).toHaveBeenCalledWith({
          debriefId: "debrief-123",
          data: {
            outcome: "positive",
            notes: "Great meeting with strong interest",
          },
        });
      });
    });
  });
});
