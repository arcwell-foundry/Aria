/**
 * PendingDebriefBanner - Collapsible banner showing meetings without debriefs
 *
 * Features:
 * - Yellow/amber tinted background to catch attention
 * - Collapsible with dismiss button (stores dismissal in localStorage, expires daily)
 * - "Start debrief" button sends WebSocket event to trigger ARIA conversation
 * - Shows meeting title, relative time, and lead name
 */

import { useState } from "react";
import { X, Clock, Users } from "lucide-react";
import { cn } from "@/utils/cn";
import { usePendingDebriefs } from "@/hooks/useDebriefs";
import { wsManager } from "@/core/WebSocketManager";
import type { PendingDebrief } from "@/api/debriefs";

const STORAGE_KEY = "aria:pending-debriefs-dismissed";

function getStoredDismissal(): string | null {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) return null;

    const { date, dismissed } = JSON.parse(stored);
    const today = new Date().toDateString();

    // Clear if it's a new day
    if (date !== today) {
      localStorage.removeItem(STORAGE_KEY);
      return null;
    }

    return dismissed ? date : null;
  } catch {
    return null;
  }
}

function setStoredDismissal() {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        date: new Date().toDateString(),
        dismissed: true,
      })
    );
  } catch {
    // Ignore storage errors
  }
}

// Format relative time
function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays} days ago`;

  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function PendingDebriefItem({
  meeting,
  onStartDebrief,
}: {
  meeting: PendingDebrief;
  onStartDebrief: (meetingId: string) => void;
}) {
  return (
    <div
      className={cn(
        "flex items-center justify-between gap-4 py-2.5 px-3 rounded-lg",
        "bg-amber-100/50 hover:bg-amber-100/70 transition-colors"
      )}
    >
      <div className="min-w-0 flex-1">
        <p
          className="text-sm font-medium truncate"
          style={{ color: "var(--text-primary)" }}
        >
          {meeting.title}
        </p>
        <div
          className="flex items-center gap-3 text-xs mt-0.5"
          style={{ color: "var(--text-secondary)" }}
        >
          <span className="flex items-center gap-1">
            <Clock className="w-3 h-3" />
            {formatRelativeTime(meeting.start_time || "")}
          </span>
          {meeting.lead_name && (
            <span className="flex items-center gap-1">
              <Users className="w-3 h-3" />
              {meeting.lead_name}
            </span>
          )}
        </div>
      </div>

      <button
        onClick={() => meeting.meeting_id && onStartDebrief(meeting.meeting_id)}
        className={cn(
          "flex-shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium",
          "bg-amber-600 text-white hover:bg-amber-700 transition-colors",
          "focus:outline-none focus:ring-2 focus:ring-amber-500/50"
        )}
      >
        Start debrief
      </button>
    </div>
  );
}

export function PendingDebriefBanner() {
  const { data: pendingMeetings, isLoading } = usePendingDebriefs();
  const [isDismissed, setIsDismissed] = useState(() => !!getStoredDismissal());
  const [isCollapsed, setIsCollapsed] = useState(false);

  const handleDismiss = () => {
    setStoredDismissal();
    setIsDismissed(true);
  };

  const handleStartDebrief = (meetingId: string) => {
    // Send WebSocket event to trigger ARIA conversation
    wsManager.send("debrief:start", { meeting_id: meetingId });
  };

  // Don't render if dismissed, loading, or no pending meetings
  if (isDismissed || isLoading || !pendingMeetings || pendingMeetings.length === 0) {
    return null;
  }

  const count = pendingMeetings.length;

  return (
    <div
      data-aria-id="pending-debriefs-banner"
      className={cn(
        "rounded-xl border overflow-hidden transition-all",
        "bg-amber-50 border-amber-200"
      )}
    >
      {/* Header */}
      <div
        className={cn(
          "flex items-center justify-between px-4 py-3",
          "bg-amber-100/80 border-b border-amber-200"
        )}
      >
        <div className="flex items-center gap-2">
          <div
            className="w-5 h-5 rounded-full flex items-center justify-center text-xs font-medium"
            style={{ backgroundColor: "var(--accent)", color: "white" }}
          >
            {count}
          </div>
          <span
            className="text-sm font-medium"
            style={{ color: "var(--text-primary)" }}
          >
            {count === 1 ? "1 meeting without a debrief" : `${count} meetings without debriefs`}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsCollapsed(!isCollapsed)}
            className={cn(
              "text-xs px-2 py-1 rounded hover:bg-amber-200/50 transition-colors",
              "focus:outline-none focus:ring-2 focus:ring-amber-500/30"
            )}
            style={{ color: "var(--text-secondary)" }}
          >
            {isCollapsed ? "Show" : "Hide"}
          </button>
          <button
            onClick={handleDismiss}
            className={cn(
              "p-1 rounded hover:bg-amber-200/50 transition-colors",
              "focus:outline-none focus:ring-2 focus:ring-amber-500/30"
            )}
            style={{ color: "var(--text-secondary)" }}
            aria-label="Dismiss"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Meeting list */}
      {!isCollapsed && (
        <div className="p-3 space-y-2">
          {pendingMeetings.slice(0, 5).map((meeting) => (
            <PendingDebriefItem
              key={meeting.meeting_id}
              meeting={meeting}
              onStartDebrief={handleStartDebrief}
            />
          ))}

          {pendingMeetings.length > 5 && (
            <p
              className="text-xs text-center pt-2"
              style={{ color: "var(--text-secondary)" }}
            >
              +{pendingMeetings.length - 5} more meetings
            </p>
          )}
        </div>
      )}
    </div>
  );
}
