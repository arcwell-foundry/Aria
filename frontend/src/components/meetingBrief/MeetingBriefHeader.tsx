import { ArrowLeft, Calendar, Clock, Printer, RefreshCw } from "lucide-react";
import { Link } from "react-router-dom";
import type { MeetingBriefStatus } from "@/api/meetingBriefs";

interface MeetingBriefHeaderProps {
  meetingTitle: string | null;
  meetingTime: string;
  status: MeetingBriefStatus;
  generatedAt: string | null;
  onRefresh: () => void;
  onPrint: () => void;
  isRefreshing?: boolean;
}

function formatMeetingTime(isoString: string): string {
  const date = new Date(isoString);
  return date.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatGeneratedTime(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffMins < 1440) return `${Math.floor(diffMins / 60)}h ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function StatusBadge({ status }: { status: MeetingBriefStatus }) {
  const styles = {
    pending: "bg-slate-600/50 text-slate-300",
    generating: "bg-amber-500/20 text-amber-400",
    completed: "bg-green-500/20 text-green-400",
    failed: "bg-red-500/20 text-red-400",
  };

  const labels = {
    pending: "Pending",
    generating: "Generating...",
    completed: "Ready",
    failed: "Failed",
  };

  return (
    <span className={`px-2.5 py-1 text-xs font-medium rounded-full ${styles[status]}`}>
      {labels[status]}
    </span>
  );
}

export function MeetingBriefHeader({
  meetingTitle,
  meetingTime,
  status,
  generatedAt,
  onRefresh,
  onPrint,
  isRefreshing,
}: MeetingBriefHeaderProps) {
  return (
    <div className="space-y-4">
      {/* Back link */}
      <Link
        to="/dashboard"
        className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to Dashboard
      </Link>

      {/* Title row */}
      <div className="flex items-start justify-between gap-4">
        <div className="space-y-2">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl font-bold text-white">
              {meetingTitle || "Meeting Brief"}
            </h1>
            <StatusBadge status={status} />
          </div>
          <div className="flex items-center gap-4 text-sm text-slate-400">
            <span className="flex items-center gap-1.5">
              <Calendar className="w-4 h-4" />
              {formatMeetingTime(meetingTime)}
            </span>
            {generatedAt && (
              <span className="flex items-center gap-1.5">
                <Clock className="w-4 h-4" />
                Updated {formatGeneratedTime(generatedAt)}
              </span>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          <button
            onClick={onPrint}
            className="p-2.5 text-slate-400 hover:text-white hover:bg-slate-700/50 rounded-lg transition-colors"
            title="Print brief"
          >
            <Printer className="w-5 h-5" />
          </button>
          <button
            onClick={onRefresh}
            disabled={isRefreshing || status === "generating"}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-slate-700/50 hover:bg-slate-700 disabled:opacity-60 disabled:cursor-not-allowed text-white font-medium rounded-lg border border-slate-600/50 transition-colors"
          >
            <RefreshCw
              className={`w-4 h-4 ${isRefreshing || status === "generating" ? "animate-spin" : ""}`}
            />
            <span className="hidden sm:inline">
              {status === "generating" ? "Generating..." : "Regenerate"}
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}
