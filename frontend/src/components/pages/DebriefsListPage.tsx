/**
 * DebriefsListPage - Browsable list of all meeting debriefs
 *
 * Route: /dashboard/debriefs
 *
 * Features:
 * - Pending debriefs banner at top (collapsible, yellow highlighted)
 * - Filter bar: date range picker + search
 * - 2-column grid of DebriefCards (responsive)
 * - Pagination
 *
 * Follows ARIA Design System:
 * - LIGHT THEME (content pages use light background)
 * - Header with status dot and subtitle
 * - Empty state drives to ARIA conversation
 */

import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { Calendar, Search, FileText } from "lucide-react";
import { cn } from "@/utils/cn";
import { useDebriefs, type DebriefFilters } from "@/hooks/useDebriefs";
import { PendingDebriefBanner } from "@/components/debriefs";
import { DebriefCard, DebriefCardSkeleton } from "@/components/rich/DebriefCard";
import { EmptyState } from "@/components/common/EmptyState";

// Date range presets
const DATE_PRESETS = [
  { label: "All time", value: "all" },
  { label: "Today", value: "today" },
  { label: "This week", value: "week" },
  { label: "This month", value: "month" },
  { label: "Last 3 months", value: "quarter" },
];

function getDateRange(preset: string): { start?: string; end?: string } {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());

  switch (preset) {
    case "today":
      return { start: today.toISOString() };
    case "week": {
      const weekAgo = new Date(today);
      weekAgo.setDate(weekAgo.getDate() - 7);
      return { start: weekAgo.toISOString() };
    }
    case "month": {
      const monthAgo = new Date(today);
      monthAgo.setMonth(monthAgo.getMonth() - 1);
      return { start: monthAgo.toISOString() };
    }
    case "quarter": {
      const quarterAgo = new Date(today);
      quarterAgo.setMonth(quarterAgo.getMonth() - 3);
      return { start: quarterAgo.toISOString() };
    }
    default:
      return {};
  }
}

// Skeleton grid for loading state
function DebriefsSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      {/* Pending banner skeleton */}
      <div className="h-24 bg-slate-200 rounded-xl" />

      {/* Filter bar skeleton */}
      <div className="flex gap-4">
        <div className="h-9 w-40 bg-slate-200 rounded-lg" />
        <div className="h-9 w-64 bg-slate-200 rounded-lg" />
      </div>

      {/* Grid skeleton */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {Array.from({ length: 6 }).map((_, i) => (
          <DebriefCardSkeleton key={i} />
        ))}
      </div>
    </div>
  );
}

export function DebriefsListPage() {
  const navigate = useNavigate();

  // Filter state
  const [datePreset, setDatePreset] = useState("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [page, setPage] = useState(1);

  // Build filters
  const dateRange = getDateRange(datePreset);
  const filters: DebriefFilters = useMemo(
    () => ({
      page,
      pageSize: 20,
      startDate: dateRange.start,
      endDate: dateRange.end,
      search: searchQuery || undefined,
    }),
    [page, dateRange.start, dateRange.end, searchQuery]
  );

  // Fetch debriefs
  const { data, isLoading, error } = useDebriefs(filters);

  // Extract data
  const debriefs = data?.items ?? [];
  const totalDebriefs = data?.total ?? 0;
  const totalPages = data?.total_pages ?? 1;

  // Handle empty state
  const hasDebriefs = debriefs.length > 0;

  return (
    <div
      className="flex-1 flex flex-col h-full"
      style={{ backgroundColor: "var(--bg-primary)" }}
    >
      <div className="flex-1 overflow-y-auto p-8">
        {/* Header */}
        <div className="mb-6">
          <div className="flex items-center gap-3 mb-1">
            <div
              className="w-2 h-2 rounded-full"
              style={{ backgroundColor: "var(--accent)" }}
            />
            <h1
              className="font-display text-2xl italic"
              style={{ color: "var(--text-primary)" }}
            >
              Debriefs
            </h1>
          </div>
          <p
            className="text-sm ml-5"
            style={{ color: "var(--text-secondary)" }}
          >
            {totalDebriefs} meeting debrief{totalDebriefs !== 1 ? "s" : ""}
          </p>
        </div>

        {/* Loading State */}
        {isLoading && <DebriefsSkeleton />}

        {/* Error State */}
        {error && (
          <div
            className="text-center py-8"
            style={{ color: "var(--text-secondary)" }}
          >
            Error loading debriefs. Please try again.
          </div>
        )}

        {/* Content */}
        {!isLoading && !error && (
          <div className="space-y-6">
            {/* Pending Debriefs Banner */}
            <PendingDebriefBanner />

            {/* Filter Bar */}
            <div className="flex flex-wrap items-center gap-4">
              {/* Date range picker */}
              <div className="flex items-center gap-2">
                <Calendar
                  className="w-4 h-4"
                  style={{ color: "var(--text-secondary)" }}
                />
                <select
                  value={datePreset}
                  onChange={(e) => {
                    setDatePreset(e.target.value);
                    setPage(1); // Reset to first page on filter change
                  }}
                  className={cn(
                    "h-9 px-3 rounded-lg border text-sm",
                    "border-[var(--border)] bg-white",
                    "focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/30"
                  )}
                  style={{ color: "var(--text-primary)" }}
                >
                  {DATE_PRESETS.map((preset) => (
                    <option key={preset.value} value={preset.value}>
                      {preset.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Search input */}
              <div className="relative flex-1 max-w-md">
                <Search
                  className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4"
                  style={{ color: "var(--text-secondary)" }}
                />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value);
                    setPage(1); // Reset to first page on search change
                  }}
                  placeholder="Search by meeting title or lead..."
                  className={cn(
                    "w-full h-9 pl-9 pr-4 rounded-lg border text-sm",
                    "border-[var(--border)] bg-white",
                    "focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/30",
                    "placeholder:text-[var(--text-muted)]"
                  )}
                  style={{ color: "var(--text-primary)" }}
                />
              </div>
            </div>

            {/* Debriefs Grid or Empty State */}
            {!hasDebriefs ? (
              <EmptyState
                title="No debriefs yet."
                description="ARIA will help you debrief after your first meeting. Debriefs capture key takeaways, action items, and insights."
                suggestion="Go to ARIA Workspace"
                onSuggestion={() => navigate("/")}
                icon={<FileText className="w-8 h-8" />}
              />
            ) : (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {debriefs.map((debrief) => (
                    <DebriefCard
                      key={debrief.id}
                      debrief={debrief}
                      // Note: For now, expanded content is not available in list view
                      // In a future iteration, we could fetch full debrief details on expand
                    />
                  ))}
                </div>

                {/* Pagination */}
                {totalPages > 1 && (
                  <div
                    className="flex items-center justify-center gap-2 pt-4"
                  >
                    <button
                      onClick={() => setPage((p) => Math.max(1, p - 1))}
                      disabled={page === 1}
                      className={cn(
                        "px-3 py-1.5 rounded-lg text-sm border",
                        "border-[var(--border)] bg-white",
                        "disabled:opacity-50 disabled:cursor-not-allowed",
                        "hover:bg-slate-50 transition-colors"
                      )}
                      style={{ color: "var(--text-primary)" }}
                    >
                      Previous
                    </button>

                    <span
                      className="text-sm px-3"
                      style={{ color: "var(--text-secondary)" }}
                    >
                      Page {page} of {totalPages}
                    </span>

                    <button
                      onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                      disabled={page === totalPages}
                      className={cn(
                        "px-3 py-1.5 rounded-lg text-sm border",
                        "border-[var(--border)] bg-white",
                        "disabled:opacity-50 disabled:cursor-not-allowed",
                        "hover:bg-slate-50 transition-colors"
                      )}
                      style={{ color: "var(--text-primary)" }}
                    >
                      Next
                    </button>
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
