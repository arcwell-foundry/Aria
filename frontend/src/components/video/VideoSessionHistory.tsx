/**
 * VideoSessionHistory - List of past video sessions with filtering.
 *
 * Displays session history in a scrollable, filterable list.
 * Integrates into VideoPage as a collapsible sidebar or tab.
 * Design: Intelligence archive aesthetic — dark, data-rich, precise.
 */

import { useState, useEffect, useCallback, useMemo } from "react";
import {
  History,
  Search,
  ChevronLeft,
  ChevronRight,
  MessageSquare,
  Target,
  ClipboardList,
  Lightbulb,
  Video,
  Clock,
  Loader2,
  AlertCircle,
  Inbox,
} from "lucide-react";
import { listVideoSessions, type VideoSession, type SessionType } from "@/api/video";
import { VideoSessionCard } from "./VideoSessionCard";
import { Badge } from "@/components/primitives/Badge";

// Session type filter options
const SESSION_TYPE_FILTERS: Array<{
  value: SessionType | "all";
  label: string;
  icon: typeof MessageSquare;
}> = [
  { value: "all", label: "All Sessions", icon: Video },
  { value: "chat", label: "Chat", icon: MessageSquare },
  { value: "briefing", label: "Briefing", icon: Target },
  { value: "debrief", label: "Debrief", icon: ClipboardList },
  { value: "consultation", label: "Consultation", icon: Lightbulb },
];

// Date range options
type DateRange = "all" | "today" | "week" | "month";
const DATE_RANGE_OPTIONS: Array<{ value: DateRange; label: string }> = [
  { value: "all", label: "All Time" },
  { value: "today", label: "Today" },
  { value: "week", label: "This Week" },
  { value: "month", label: "This Month" },
];

// Stats display
interface SessionStats {
  total: number;
  totalDuration: number;
  byType: Record<SessionType, number>;
}

function calculateStats(sessions: VideoSession[]): SessionStats {
  const stats: SessionStats = {
    total: sessions.length,
    totalDuration: sessions.reduce(
      (sum, s) => sum + (s.duration_seconds || 0),
      0
    ),
    byType: { chat: 0, briefing: 0, debrief: 0, consultation: 0 },
  };

  for (const session of sessions) {
    stats.byType[session.session_type]++;
  }

  return stats;
}

function formatTotalDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600);
  const mins = Math.floor((seconds % 3600) / 60);

  if (hours === 0) return `${mins}m`;
  return `${hours}h ${mins}m`;
}

interface VideoSessionHistoryProps {
  /** Optional limit on number of sessions to show */
  limit?: number;
  /** Whether to show compact view (no stats) */
  compact?: boolean;
  /** Header title override */
  title?: string;
  /** Additional CSS classes */
  className?: string;
  /** Callback when a session is selected */
  onSelectSession?: (session: VideoSession) => void;
}

type LoadingState = "idle" | "loading" | "error";

export function VideoSessionHistory({
  limit = 20,
  compact = false,
  title = "Session History",
  className = "",
  onSelectSession,
}: VideoSessionHistoryProps) {
  // State
  const [sessions, setSessions] = useState<VideoSession[]>([]);
  const [loadingState, setLoadingState] = useState<LoadingState>("idle");
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [totalSessions, setTotalSessions] = useState(0);

  // Filters
  const [typeFilter, setTypeFilter] = useState<SessionType | "all">("all");
  const [dateRange, setDateRange] = useState<DateRange>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [retryCount, setRetryCount] = useState(0);

  // Fetch sessions
  useEffect(() => {
    let isMounted = true;

    async function loadSessions() {
      setLoadingState("loading");
      setError(null);

      try {
        const offset = page * limit;
        const response = await listVideoSessions({
          limit,
          offset,
          session_type: typeFilter === "all" ? undefined : typeFilter,
        });

        if (isMounted) {
          setSessions(response.items);
          setTotalSessions(response.total);
          setLoadingState("idle");
        }
      } catch (err) {
        console.error("Failed to fetch video sessions:", err);
        if (isMounted) {
          setError("Unable to load session history. Please try again.");
          setLoadingState("error");
        }
      }
    }

    loadSessions();

    return () => {
      isMounted = false;
    };
  }, [page, limit, typeFilter, retryCount]);

  // Retry handler
  const handleRetry = useCallback(() => {
    setRetryCount((c) => c + 1);
  }, []);

  // Filter sessions by date range (client-side)
  const filteredSessions = useMemo(() => {
    if (dateRange === "all") return sessions;

    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const weekAgo = new Date(today.getTime() - 7 * 24 * 60 * 60 * 1000);
    const monthAgo = new Date(today.getTime() - 30 * 24 * 60 * 60 * 1000);

    let cutoff: Date;
    switch (dateRange) {
      case "today":
        cutoff = today;
        break;
      case "week":
        cutoff = weekAgo;
        break;
      case "month":
        cutoff = monthAgo;
        break;
      default:
        return sessions;
    }

    return sessions.filter((s) => {
      const date = new Date(s.started_at || s.created_at);
      return date >= cutoff;
    });
  }, [sessions, dateRange]);

  // Search filtering (client-side)
  const searchedSessions = useMemo(() => {
    if (!searchQuery.trim()) return filteredSessions;

    const query = searchQuery.toLowerCase();
    return filteredSessions.filter((s) => {
      // Search in transcripts if available
      const transcriptMatch = s.transcripts?.some((t) =>
        t.content.toLowerCase().includes(query)
      );

      // Search in perception analysis stringified
      const perceptionMatch = s.perception_analysis
        ? JSON.stringify(s.perception_analysis).toLowerCase().includes(query)
        : false;

      return transcriptMatch || perceptionMatch;
    });
  }, [filteredSessions, searchQuery]);

  // Calculate stats
  const stats = useMemo(() => calculateStats(sessions), [sessions]);

  // Pagination
  const totalPages = Math.ceil(totalSessions / limit);
  const canGoBack = page > 0;
  const canGoForward = page < totalPages - 1;

  return (
    <div
      className={`
        flex flex-col h-full bg-primary text-content
        ${className}
      `}
    >
      {/* Header */}
      <div className="px-4 py-3 border-b border-border">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-content flex items-center gap-2">
            <History size={16} className="text-accent" />
            {title}
          </h2>
          {!compact && (
            <Badge variant="default" size="sm">
              {totalSessions} sessions
            </Badge>
          )}
        </div>

        {/* Search */}
        <div className="relative mb-3">
          <Search
            size={14}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-secondary"
          />
          <input
            type="text"
            placeholder="Search transcripts..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="
              w-full pl-9 pr-3 py-2 text-sm
              bg-subtle border border-border rounded-lg
              text-content placeholder:text-secondary
              focus:outline-none focus:border-accent focus:ring-1 focus:ring-accent/30
              transition-colors
            "
          />
        </div>

        {/* Filters Row */}
        <div className="flex items-center gap-2 flex-wrap">
          {/* Type Filter */}
          <div className="flex items-center gap-1 bg-subtle/50 rounded-lg p-1">
            {SESSION_TYPE_FILTERS.slice(0, 3).map((filter) => (
              <button
                key={filter.value}
                type="button"
                onClick={() => {
                  setTypeFilter(filter.value);
                  setPage(0);
                }}
                className={`
                  px-2 py-1 text-xs font-medium rounded transition-colors
                  ${typeFilter === filter.value
                    ? "bg-accent text-white"
                    : "text-secondary hover:text-content"
                  }
                `}
                title={filter.label}
              >
                <filter.icon size={14} />
              </button>
            ))}
            <select
              value={typeFilter}
              onChange={(e) => {
                setTypeFilter(e.target.value as SessionType | "all");
                setPage(0);
              }}
              className="
                px-2 py-1 text-xs font-medium rounded
                bg-transparent text-secondary
                border-none outline-none cursor-pointer
                hover:text-content transition-colors
              "
            >
              {SESSION_TYPE_FILTERS.slice(3).map((filter) => (
                <option key={filter.value} value={filter.value}>
                  {filter.label}
                </option>
              ))}
              <option value="all">All Types</option>
            </select>
          </div>

          {/* Date Range */}
          <select
            value={dateRange}
            onChange={(e) => setDateRange(e.target.value as DateRange)}
            className="
              px-2 py-1.5 text-xs font-medium
              bg-subtle/50 border border-border rounded-lg
              text-secondary hover:text-content
              focus:outline-none focus:border-accent
              transition-colors cursor-pointer
            "
          >
            {DATE_RANGE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Stats Bar (non-compact only) */}
      {!compact && sessions.length > 0 && (
        <div className="px-4 py-2 bg-subtle/30 border-b border-border/50">
          <div className="flex items-center gap-4 text-xs">
            <div className="flex items-center gap-1.5">
              <Clock size={12} className="text-secondary" />
              <span className="text-secondary">Total time:</span>
              <span className="font-mono text-content">
                {formatTotalDuration(stats.totalDuration)}
              </span>
            </div>
            <div className="h-3 w-px bg-border" />
            <div className="flex items-center gap-2">
              {Object.entries(stats.byType).map(([type, count]) => {
                if (count === 0) return null;
                return (
                  <span key={type} className="flex items-center gap-1">
                    <span className="text-secondary capitalize">{type}:</span>
                    <span className="font-mono text-content">{count}</span>
                  </span>
                );
              })}
            </div>
          </div>
        </div>
      )}

      {/* Session List */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
        {/* Loading State */}
        {loadingState === "loading" && (
          <div className="flex flex-col items-center justify-center py-12 text-secondary">
            <Loader2 size={24} className="animate-spin mb-3" />
            <span className="text-sm">Loading session history...</span>
          </div>
        )}

        {/* Error State */}
        {loadingState === "error" && (
          <div className="flex flex-col items-center justify-center py-12 text-critical">
            <AlertCircle size={24} className="mb-3" />
            <span className="text-sm mb-3">{error}</span>
            <button
              type="button"
              onClick={handleRetry}
              className="
                px-3 py-1.5 text-sm
                bg-critical/10 border border-critical/30 rounded-lg
                hover:bg-critical/20 transition-colors
              "
            >
              Try Again
            </button>
          </div>
        )}

        {/* Empty State */}
        {loadingState === "idle" && searchedSessions.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-secondary">
            <Inbox size={32} className="mb-3 opacity-50" />
            <span className="text-sm mb-1">No sessions found</span>
            <span className="text-xs">
              {searchQuery
                ? "Try a different search term"
                : "Start a video session to see history here"}
            </span>
          </div>
        )}

        {/* Session Cards */}
        {loadingState === "idle" &&
          searchedSessions.map((session) => (
            <VideoSessionCard
              key={session.id}
              session={session}
              onClick={() => onSelectSession?.(session)}
            />
          ))}
      </div>

      {/* Pagination */}
      {loadingState === "idle" && totalPages > 1 && (
        <div className="px-4 py-3 border-t border-border flex items-center justify-between">
          <span className="text-xs text-secondary">
            Page {page + 1} of {totalPages}
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPage((p) => Math.max(0, p - 1))}
              disabled={!canGoBack}
              className={`
                p-1.5 rounded-lg border border-border
                transition-colors
                ${canGoBack
                  ? "text-secondary hover:text-content hover:border-accent/50"
                  : "text-secondary/30 cursor-not-allowed"
                }
              `}
            >
              <ChevronLeft size={16} />
            </button>
            <button
              type="button"
              onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
              disabled={!canGoForward}
              className={`
                p-1.5 rounded-lg border border-border
                transition-colors
                ${canGoForward
                  ? "text-secondary hover:text-content hover:border-accent/50"
                  : "text-secondary/30 cursor-not-allowed"
                }
              `}
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
