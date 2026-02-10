import { render, screen, act } from "@testing-library/react";
import {
  describe,
  it,
  expect,
  vi,
  beforeEach,
  afterEach,
} from "vitest";
import type { ErrorEvent } from "@/lib/errorEvents";

// Mock framer-motion to render plain divs (avoids animation issues in tests)
vi.mock("framer-motion", () => ({
  motion: {
    div: (props: React.HTMLAttributes<HTMLDivElement> & Record<string, unknown>) => (
      <div className={props.className as string} style={props.style as React.CSSProperties}>
        {props.children}
      </div>
    ),
  },
  AnimatePresence: ({ children }: { children: React.ReactNode }) => (
    <>{children}</>
  ),
}));

// Spy on errorEvents to capture the onError callback
const mockUnsubscribe = vi.fn();
let capturedCallback: ((error: ErrorEvent) => void) | null = null;

vi.mock("@/lib/errorEvents", async () => {
  const actual = await vi.importActual<typeof import("@/lib/errorEvents")>(
    "@/lib/errorEvents"
  );
  return {
    ...actual,
    onError: vi.fn((cb: (error: ErrorEvent) => void) => {
      capturedCallback = cb;
      return mockUnsubscribe;
    }),
  };
});

import { ErrorToaster } from "../ErrorToaster";
import { onError, getColorForErrorType, getDismissDelay } from "@/lib/errorEvents";

/** Helper: create a fake ErrorEvent */
function makeError(
  overrides: Partial<ErrorEvent> = {}
): ErrorEvent {
  return {
    type: "server",
    title: "Server Error",
    description: "Something went wrong on the server.",
    timestamp: Date.now(),
    id: `error-${Math.random().toString(36).slice(2, 9)}`,
    ...overrides,
  };
}

/** Helper: emit an error through the captured callback */
function emitError(error: ErrorEvent): void {
  expect(capturedCallback).not.toBeNull();
  act(() => {
    capturedCallback!(error);
  });
}

describe("ErrorToaster", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    capturedCallback = null;
    mockUnsubscribe.mockClear();
    vi.mocked(onError).mockClear();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  // ─── Rendering ─────────────────────────────────────────────

  describe("rendering", () => {
    it("renders empty when no errors have been emitted", () => {
      render(<ErrorToaster />);
      // The container div exists, but no toast text is present
      expect(screen.queryByText("Server Error")).not.toBeInTheDocument();
    });

    it("subscribes to error events on mount", () => {
      render(<ErrorToaster />);
      expect(onError).toHaveBeenCalledTimes(1);
      expect(onError).toHaveBeenCalledWith(expect.any(Function));
    });

    it("unsubscribes from error events on unmount", () => {
      const { unmount } = render(<ErrorToaster />);
      expect(mockUnsubscribe).not.toHaveBeenCalled();
      unmount();
      expect(mockUnsubscribe).toHaveBeenCalledTimes(1);
    });
  });

  // ─── Toast Display ─────────────────────────────────────────

  describe("toast display", () => {
    it("shows a toast when an error is emitted", () => {
      render(<ErrorToaster />);
      emitError(makeError({ title: "Oops", description: "Something broke" }));

      expect(screen.getByText("Oops")).toBeInTheDocument();
      expect(screen.getByText("Something broke")).toBeInTheDocument();
    });

    it("shows multiple toasts simultaneously", () => {
      render(<ErrorToaster />);
      emitError(makeError({ id: "e1", title: "Error 1" }));
      emitError(makeError({ id: "e2", title: "Error 2" }));

      expect(screen.getByText("Error 1")).toBeInTheDocument();
      expect(screen.getByText("Error 2")).toBeInTheDocument();
    });

    it("limits visible toasts to 3, removing the oldest", () => {
      render(<ErrorToaster />);
      emitError(makeError({ id: "e1", title: "Error 1" }));
      emitError(makeError({ id: "e2", title: "Error 2" }));
      emitError(makeError({ id: "e3", title: "Error 3" }));
      emitError(makeError({ id: "e4", title: "Error 4" }));

      // Oldest (Error 1) should be evicted
      expect(screen.queryByText("Error 1")).not.toBeInTheDocument();
      // Latest three should remain
      expect(screen.getByText("Error 2")).toBeInTheDocument();
      expect(screen.getByText("Error 3")).toBeInTheDocument();
      expect(screen.getByText("Error 4")).toBeInTheDocument();
    });
  });

  // ─── Toast Dismissal ──────────────────────────────────────

  describe("toast dismissal", () => {
    it("auto-dismisses a toast after the correct delay", () => {
      render(<ErrorToaster />);
      const error = makeError({ type: "server", title: "Will vanish" });
      emitError(error);
      expect(screen.getByText("Will vanish")).toBeInTheDocument();

      const delay = getDismissDelay("server"); // 4000
      act(() => {
        vi.advanceTimersByTime(delay);
      });

      expect(screen.queryByText("Will vanish")).not.toBeInTheDocument();
    });

    it("uses different dismiss delays based on error type", () => {
      render(<ErrorToaster />);

      // Auth errors have a longer delay (6000ms)
      const authError = makeError({
        id: "auth-1",
        type: "auth",
        title: "Auth Error",
      });
      emitError(authError);
      expect(screen.getByText("Auth Error")).toBeInTheDocument();

      // After 4000ms the auth toast should still be visible
      act(() => {
        vi.advanceTimersByTime(4000);
      });
      expect(screen.getByText("Auth Error")).toBeInTheDocument();

      // After the full 6000ms it should be gone
      act(() => {
        vi.advanceTimersByTime(2000);
      });
      expect(screen.queryByText("Auth Error")).not.toBeInTheDocument();
    });

    it("dismisses a toast when the X button is clicked", () => {
      render(<ErrorToaster />);
      emitError(makeError({ title: "Dismiss me" }));
      expect(screen.getByText("Dismiss me")).toBeInTheDocument();

      const dismissButton = screen.getByRole("button", { name: /dismiss/i });
      act(() => {
        dismissButton.click();
      });

      expect(screen.queryByText("Dismiss me")).not.toBeInTheDocument();
    });

    it("only dismisses the clicked toast, leaving others intact", () => {
      render(<ErrorToaster />);
      emitError(makeError({ id: "keep", title: "Keep me" }));
      emitError(makeError({ id: "remove", title: "Remove me" }));

      expect(screen.getByText("Keep me")).toBeInTheDocument();
      expect(screen.getByText("Remove me")).toBeInTheDocument();

      // There should be two dismiss buttons; click the second one
      const dismissButtons = screen.getAllByRole("button", {
        name: /dismiss/i,
      });
      act(() => {
        dismissButtons[1].click();
      });

      expect(screen.getByText("Keep me")).toBeInTheDocument();
      expect(screen.queryByText("Remove me")).not.toBeInTheDocument();
    });
  });

  // ─── Error Type Rendering ─────────────────────────────────

  describe("error type rendering", () => {
    it("renders an icon element inside the toast", () => {
      render(<ErrorToaster />);
      emitError(makeError({ type: "network", title: "Network Issue" }));

      // Lucide icons render as <svg> elements
      const toast = screen.getByText("Network Issue").closest("div")!
        .parentElement!;
      const svg = toast.querySelector("svg");
      expect(svg).not.toBeNull();
    });

    it("applies correct color classes for the error type", () => {
      render(<ErrorToaster />);
      const error = makeError({ type: "auth", title: "Auth Error" });
      emitError(error);

      const colors = getColorForErrorType("auth");
      // Walk up from the title text to find the toast wrapper with color classes
      const toastTitle = screen.getByText("Auth Error");
      let el: HTMLElement | null = toastTitle;
      let toastWrapper: HTMLElement | null = null;
      while (el) {
        if (el.className && el.className.includes(colors.bg)) {
          toastWrapper = el;
          break;
        }
        el = el.parentElement;
      }

      expect(toastWrapper).not.toBeNull();
      expect(toastWrapper!.className).toContain(colors.bg);
      expect(toastWrapper!.className).toContain(colors.border);
    });
  });

  // ─── Positioning ───────────────────────────────────────────

  describe("positioning", () => {
    it("renders with fixed positioning at bottom-right", () => {
      const { container } = render(<ErrorToaster />);
      const wrapper = container.firstElementChild as HTMLElement;

      expect(wrapper.className).toContain("fixed");
      expect(wrapper.style.bottom).toBe("24px");
      expect(wrapper.style.right).toBe("24px");
    });
  });
});
