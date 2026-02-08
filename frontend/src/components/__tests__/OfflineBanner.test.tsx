import { render, screen, waitFor } from "@testing-library/react";
import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { OfflineBanner } from "../OfflineBanner";

describe("OfflineBanner", () => {
  // Store original navigator.onLine state
  const originalOnLine = navigator.onLine;

  beforeEach(() => {
    // Reset to online before each test
    Object.defineProperty(navigator, "onLine", {
      writable: true,
      value: true,
    });
  });

  afterEach(() => {
    // Restore original state
    Object.defineProperty(navigator, "onLine", {
      writable: true,
      value: originalOnLine,
    });
  });

  it("does not render when online", () => {
    Object.defineProperty(navigator, "onLine", {
      writable: true,
      value: true,
    });

    render(<OfflineBanner />);

    const banner = screen.queryByRole("status");
    expect(banner).not.toBeInTheDocument();
  });

  it("renders when offline", async () => {
    Object.defineProperty(navigator, "onLine", {
      writable: true,
      value: false,
    });

    render(<OfflineBanner />);

    await waitFor(() => {
      const banner = screen.getByRole("status");
      expect(banner).toBeInTheDocument();
      expect(banner).toHaveAttribute("aria-label", "You are currently offline");
    });
  });

  it("dismisses when connection restored", async () => {
    // Start offline
    Object.defineProperty(navigator, "onLine", {
      writable: true,
      value: false,
    });

    render(<OfflineBanner />);

    // Wait for banner to appear
    await waitFor(() => {
      expect(screen.getByRole("status")).toBeInTheDocument();
    });

    // Simulate coming back online
    Object.defineProperty(navigator, "onLine", {
      writable: true,
      value: true,
    });

    // Dispatch online event
    window.dispatchEvent(new Event("online"));

    // Banner should disappear
    await waitFor(() => {
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
  });

  it("shows when going offline", async () => {
    // Start online
    Object.defineProperty(navigator, "onLine", {
      writable: true,
      value: true,
    });

    render(<OfflineBanner />);

    // Initially should not show
    expect(screen.queryByRole("status")).not.toBeInTheDocument();

    // Simulate going offline
    Object.defineProperty(navigator, "onLine", {
      writable: true,
      value: false,
    });

    // Dispatch offline event
    window.dispatchEvent(new Event("offline"));

    // Banner should appear
    await waitFor(() => {
      expect(screen.getByRole("status")).toBeInTheDocument();
    });
  });

  it("uses correct styling classes", async () => {
    Object.defineProperty(navigator, "onLine", {
      writable: true,
      value: false,
    });

    render(<OfflineBanner />);

    await waitFor(() => {
      const banner = screen.getByRole("status");
      expect(banner).toHaveClass(
        "fixed",
        "top-0",
        "left-0",
        "right-0",
        "z-50",
        "bg-warning/10",
        "border-b",
        "border-warning/20"
      );
    });
  });

  it("displays correct message and icon", async () => {
    Object.defineProperty(navigator, "onLine", {
      writable: true,
      value: false,
    });

    render(<OfflineBanner />);

    await waitFor(() => {
      const message = screen.getByText(/you are currently offline/i);
      expect(message).toBeInTheDocument();
    });
  });

  it("has dismiss button with correct aria-label", async () => {
    Object.defineProperty(navigator, "onLine", {
      writable: true,
      value: false,
    });

    render(<OfflineBanner />);

    await waitFor(() => {
      const dismissButton = screen.getByRole("button", {
        name: /dismiss offline notification/i,
      });
      expect(dismissButton).toBeInTheDocument();
    });
  });

  it("dismisses when dismiss button is clicked", async () => {
    Object.defineProperty(navigator, "onLine", {
      writable: true,
      value: false,
    });

    render(<OfflineBanner />);

    // Wait for banner to appear
    await waitFor(() => {
      expect(screen.getByRole("status")).toBeInTheDocument();
    });

    // Click dismiss button
    const dismissButton = screen.getByRole("button", {
      name: /dismiss offline notification/i,
    });
    dismissButton.click();

    // Banner should disappear
    await waitFor(() => {
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });
  });

  it("resets dismissed state when coming back online then offline again", async () => {
    // Start offline
    Object.defineProperty(navigator, "onLine", {
      writable: true,
      value: false,
    });

    render(<OfflineBanner />);

    // Wait for banner to appear
    await waitFor(() => {
      expect(screen.getByRole("status")).toBeInTheDocument();
    });

    // Dismiss the banner
    const dismissButton = screen.getByRole("button", {
      name: /dismiss offline notification/i,
    });
    dismissButton.click();

    // Banner should disappear
    await waitFor(() => {
      expect(screen.queryByRole("status")).not.toBeInTheDocument();
    });

    // Come back online
    Object.defineProperty(navigator, "onLine", {
      writable: true,
      value: true,
    });
    window.dispatchEvent(new Event("online"));

    // Go offline again
    Object.defineProperty(navigator, "onLine", {
      writable: true,
      value: false,
    });
    window.dispatchEvent(new Event("offline"));

    // Banner should reappear
    await waitFor(() => {
      expect(screen.getByRole("status")).toBeInTheDocument();
    });
  });

  it("has aria-live attribute for screen readers", async () => {
    Object.defineProperty(navigator, "onLine", {
      writable: true,
      value: false,
    });

    render(<OfflineBanner />);

    await waitFor(() => {
      const banner = screen.getByRole("status");
      expect(banner).toHaveAttribute("aria-live", "polite");
    });
  });
});
