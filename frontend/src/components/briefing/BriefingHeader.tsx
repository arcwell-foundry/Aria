import { RefreshCw, History } from "lucide-react";

interface BriefingHeaderProps {
  userName?: string;
  generatedAt?: string;
  onRefresh: () => void;
  onViewHistory: () => void;
  isRefreshing?: boolean;
}

function getGreeting(): string {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 17) return "Good afternoon";
  return "Good evening";
}

function formatGeneratedTime(isoString: string): string {
  const date = new Date(isoString);
  const now = new Date();
  const isToday = date.toDateString() === now.toDateString();

  if (isToday) {
    return date.toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
    });
  }

  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function BriefingHeader({
  userName,
  generatedAt,
  onRefresh,
  onViewHistory,
  isRefreshing,
}: BriefingHeaderProps) {
  const greeting = getGreeting();
  const displayName = userName?.split(" ")[0] || "there";

  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <h1 className="text-3xl font-bold text-white">
          {greeting}, {displayName}
        </h1>
        <p className="mt-1 text-slate-400">
          Here's your daily briefing
          {generatedAt && (
            <span className="text-slate-500">
              {" "}
              · Updated {formatGeneratedTime(generatedAt)}
            </span>
          )}
        </p>
      </div>
      <div className="flex items-center gap-2">
        <button
          onClick={onViewHistory}
          className="p-2.5 text-slate-400 hover:text-white hover:bg-slate-700/50 rounded-lg transition-colors"
          title="View past briefings"
        >
          <History className="w-5 h-5" />
        </button>
        <button
          onClick={onRefresh}
          disabled={isRefreshing}
          className="inline-flex items-center gap-2 px-4 py-2.5 bg-slate-700/50 hover:bg-slate-700 disabled:opacity-60 disabled:cursor-not-allowed text-white font-medium rounded-lg border border-slate-600/50 transition-colors"
        >
          <RefreshCw className={`w-4 h-4 ${isRefreshing ? "animate-spin" : ""}`} />
          <span className="hidden sm:inline">{isRefreshing ? "Refreshing..." : "Refresh"}</span>
        </button>
      </div>
    </div>
  );
}
