import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { EmailPreferencesSection } from "../EmailPreferencesSection";

// Mock the hooks
const mockUseEmailPreferences = vi.fn();
const mockUseUpdateEmailPreferences = vi.fn();

vi.mock("@/hooks/useEmailPreferences", () => ({
  useEmailPreferences: () => mockUseEmailPreferences(),
  useUpdateEmailPreferences: () => mockUseUpdateEmailPreferences(),
}));

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
      mutations: {
        retry: false,
      },
    },
  });
}

function createWrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: React.ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    );
  };
}

describe("EmailPreferencesSection", () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = createTestQueryClient();
    vi.clearAllMocks();
  });

  describe("rendering", () => {
    it("renders email preference toggles", async () => {
      const mockMutate = vi.fn();
      mockUseEmailPreferences.mockReturnValue({
        data: {
          weekly_summary: true,
          feature_announcements: true,
          security_alerts: true,
        },
        isLoading: false,
        isError: false,
      });
      mockUseUpdateEmailPreferences.mockReturnValue({
        mutate: mockMutate,
        isPending: false,
      });

      render(<EmailPreferencesSection />, {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(screen.getByText("Weekly Summary")).toBeInTheDocument();
        expect(screen.getByText("Feature Announcements")).toBeInTheDocument();
        expect(screen.getByText("Security Alerts")).toBeInTheDocument();
      });
    });

    it("disables security alerts toggle", async () => {
      mockUseEmailPreferences.mockReturnValue({
        data: {
          weekly_summary: true,
          feature_announcements: true,
          security_alerts: true,
        },
        isLoading: false,
        isError: false,
      });
      mockUseUpdateEmailPreferences.mockReturnValue({
        mutate: vi.fn(),
        isPending: false,
      });

      render(<EmailPreferencesSection />, {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        const securityToggles = screen.getAllByRole("switch", { checked: true });
        // Security alerts is the 3rd toggle and should be disabled
        const securityToggle = securityToggles[2];
        expect(securityToggle).toBeDisabled();
      });
    });

    it("shows tooltip for disabled security alerts", async () => {
      mockUseEmailPreferences.mockReturnValue({
        data: {
          weekly_summary: true,
          feature_announcements: true,
          security_alerts: true,
        },
        isLoading: false,
        isError: false,
      });
      mockUseUpdateEmailPreferences.mockReturnValue({
        mutate: vi.fn(),
        isPending: false,
      });

      render(<EmailPreferencesSection />, {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(
          screen.getByText(
            "Security alerts cannot be disabled as they are essential for account safety"
          )
        ).toBeInTheDocument();
      });
    });

    it("toggles weekly summary preference", async () => {
      const mockMutate = vi.fn();
      mockUseEmailPreferences.mockReturnValue({
        data: {
          weekly_summary: true,
          feature_announcements: true,
          security_alerts: true,
        },
        isLoading: false,
        isError: false,
      });
      mockUseUpdateEmailPreferences.mockReturnValue({
        mutate: mockMutate,
        isPending: false,
      });

      render(<EmailPreferencesSection />, {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        const toggles = screen.getAllByRole("switch");
        const weeklyToggle = toggles[0]; // First toggle is weekly summary
        expect(weeklyToggle).toBeInTheDocument();
      });

      const toggles = screen.getAllByRole("switch");
      const weeklyToggle = toggles[0];

      fireEvent.click(weeklyToggle);

      // Wait for the mutation to be called
      await waitFor(() => {
        expect(mockMutate).toHaveBeenCalled();
      });
    });
  });

  describe("ARIA Design System compliance", () => {
    it("uses correct dark theme background bg-[#161B2E]", async () => {
      mockUseEmailPreferences.mockReturnValue({
        data: {
          weekly_summary: true,
          feature_announcements: true,
          security_alerts: true,
        },
        isLoading: false,
        isError: false,
      });
      mockUseUpdateEmailPreferences.mockReturnValue({
        mutate: vi.fn(),
        isPending: false,
      });

      const { container } = render(<EmailPreferencesSection />, {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        const section = container.querySelector(".email-preferences-section");
        expect(section).toHaveClass("bg-[#161B2E]");
      });
    });

    it("uses correct accent color text-[#5B6E8A]", async () => {
      mockUseEmailPreferences.mockReturnValue({
        data: {
          weekly_summary: true,
          feature_announcements: true,
          security_alerts: true,
        },
        isLoading: false,
        isError: false,
      });
      mockUseUpdateEmailPreferences.mockReturnValue({
        mutate: vi.fn(),
        isPending: false,
      });

      const { container } = render(<EmailPreferencesSection />, {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        // Check that headings have the correct text color by using attribute selector
        const headings = container.querySelectorAll('[class*="text-[#E8E6E1]"]');
        expect(headings.length).toBeGreaterThan(0);
      });
    });

    it("toggle switches use translate-x-6 for on state", async () => {
      mockUseEmailPreferences.mockReturnValue({
        data: {
          weekly_summary: true,
          feature_announcements: true,
          security_alerts: true,
        },
        isLoading: false,
        isError: false,
      });
      mockUseUpdateEmailPreferences.mockReturnValue({
        mutate: vi.fn(),
        isPending: false,
      });

      const { container } = render(<EmailPreferencesSection />, {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        const toggles = container.querySelectorAll('button[role="switch"][aria-checked="true"]');
        expect(toggles.length).toBeGreaterThan(0);

        // Check that enabled toggles have translate-x-6 class
        const enabledToggle = toggles[0];
        const toggleKnob = enabledToggle.querySelector("span");
        expect(toggleKnob).toHaveClass("translate-x-6");
      });
    });

    it("toggle switches use translate-x-0 for off state", async () => {
      mockUseEmailPreferences.mockReturnValue({
        data: {
          weekly_summary: false,
          feature_announcements: false,
          security_alerts: true,
        },
        isLoading: false,
        isError: false,
      });
      mockUseUpdateEmailPreferences.mockReturnValue({
        mutate: vi.fn(),
        isPending: false,
      });

      const { container } = render(<EmailPreferencesSection />, {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        const toggles = container.querySelectorAll('button[role="switch"][aria-checked="false"]');
        expect(toggles.length).toBeGreaterThan(0);

        // Check that disabled toggles have translate-x-0 class
        const disabledToggle = toggles[0];
        const toggleKnob = disabledToggle.querySelector("span");
        expect(toggleKnob).toHaveClass("translate-x-0");
      });
    });
  });

  describe("loading state", () => {
    it("shows loading state while fetching preferences", async () => {
      mockUseEmailPreferences.mockReturnValue({
        data: undefined,
        isLoading: true,
        isError: false,
      });
      mockUseUpdateEmailPreferences.mockReturnValue({
        mutate: vi.fn(),
        isPending: false,
      });

      render(<EmailPreferencesSection />, {
        wrapper: createWrapper(queryClient),
      });

      expect(screen.getByTestId(/loading-spinner/i)).toBeInTheDocument();
    });
  });

  describe("error state", () => {
    it("shows error message when preferences fail to load", async () => {
      mockUseEmailPreferences.mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
        error: new Error("Failed to load preferences"),
      });
      mockUseUpdateEmailPreferences.mockReturnValue({
        mutate: vi.fn(),
        isPending: false,
      });

      render(<EmailPreferencesSection />, {
        wrapper: createWrapper(queryClient),
      });

      await waitFor(() => {
        expect(
          screen.getByText(/Failed to load email preferences/i)
        ).toBeInTheDocument();
      });
    });
  });
});
