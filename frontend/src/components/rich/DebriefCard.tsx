/**
 * DebriefCard - Expandable card for displaying meeting debrief summaries
 *
 * Features:
 * - Compact view: title, date, outcome badge, action item count
 * - Expanded view: full summary, commitments (ours/theirs), insights
 * - Typographic outcome badges (no emojis)
 * - Click to expand inline
 */

import { useState } from "react";
import { ChevronDown, Calendar, CheckCircle, Clock } from "lucide-react";
import { cn } from "@/utils/cn";
import type { DebriefListItem, DebriefOutcome } from "@/api/debriefs";

// Outcome badge configuration with typographic styling
const OUTCOME_CONFIG: Record<
  DebriefOutcome,
  { label: string; bgClass: string; textClass: string }
> = {
  positive: {
    label: "Won",
    bgClass: "bg-emerald-900/20",
    textClass: "text-slate-700",
  },
  neutral: {
    label: "No Decision",
    bgClass: "bg-slate-800/20",
    textClass: "text-slate-500",
  },
  concern: {
    label: "Lost",
    bgClass: "bg-red-900/20",
    textClass: "text-slate-700",
  },
};

function OutcomeBadge({ outcome }: { outcome: DebriefOutcome | null }) {
  if (!outcome) {
    return (
      <span
        className={cn(
          "px-2 py-0.5 rounded text-xs font-medium",
          "bg-amber-900/20 text-slate-700"
        )}
      >
        Pending
      </span>
    );
  }

  const config = OUTCOME_CONFIG[outcome];

  return (
    <span
      className={cn(
        "px-2 py-0.5 rounded text-xs font-medium",
        config.bgClass,
        config.textClass
      )}
    >
      {config.label}
    </span>
  );
}

function formatDate(dateString: string | null): string {
  if (!dateString) return "Unknown date";

  const date = new Date(dateString);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

interface DebriefCardProps {
  debrief: DebriefListItem;
  expandedContent?: {
    summary: string;
    commitments: {
      ours: string[];
      theirs: string[];
    };
    insights: string[];
  };
}

export function DebriefCard({ debrief, expandedContent }: DebriefCardProps) {
  const [isExpanded, setIsExpanded] = useState(false);

  const hasExpandedContent = expandedContent && (
    expandedContent.summary ||
    (expandedContent.commitments?.ours ?? []).length > 0 ||
    (expandedContent.commitments?.theirs ?? []).length > 0 ||
    (expandedContent.insights ?? []).length > 0
  );

  return (
    <div
      data-aria-id={`debrief-${debrief.id}`}
      className={cn(
        "rounded-xl border transition-all",
        "bg-white hover:border-slate-300",
        isExpanded ? "border-slate-300" : "border-slate-200"
      )}
    >
      {/* Compact header - always visible */}
      <button
        onClick={() => hasExpandedContent && setIsExpanded(!isExpanded)}
        disabled={!hasExpandedContent}
        className={cn(
          "w-full text-left px-4 py-3 focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/30",
          hasExpandedContent && "cursor-pointer"
        )}
      >
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h3
              className="text-sm font-medium truncate"
              style={{ color: "var(--text-primary)" }}
            >
              {debrief.meeting_title || "Untitled Meeting"}
            </h3>

            <div
              className="flex items-center gap-3 mt-1.5 text-xs"
              style={{ color: "var(--text-secondary)" }}
            >
              <span className="flex items-center gap-1">
                <Calendar className="w-3 h-3" />
                {formatDate(debrief.meeting_time)}
              </span>

              {debrief.linked_lead_name && (
                <span className="truncate">{debrief.linked_lead_name}</span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2 flex-shrink-0">
            <OutcomeBadge outcome={debrief.outcome} />

            {hasExpandedContent && (
              <ChevronDown
                className={cn(
                  "w-4 h-4 transition-transform",
                  isExpanded && "rotate-180"
                )}
                style={{ color: "var(--text-secondary)" }}
              />
            )}
          </div>
        </div>

        {/* Action items count */}
        <div
          className="flex items-center gap-4 mt-3 text-xs"
          style={{ color: "var(--text-secondary)" }}
        >
          <span className="flex items-center gap-1.5">
            <CheckCircle className="w-3.5 h-3.5" />
            {debrief.action_items_count} action item{debrief.action_items_count !== 1 ? "s" : ""}
          </span>

          {expandedContent?.insights && expandedContent.insights.length > 0 && (
            <span className="flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5" />
              {expandedContent.insights.length} insight{expandedContent.insights.length !== 1 ? "s" : ""}
            </span>
          )}
        </div>
      </button>

      {/* Expanded content */}
      {isExpanded && expandedContent && (
        <div
          className={cn(
            "px-4 pb-4 pt-0 space-y-4",
            "border-t border-slate-100 mt-2 pt-4"
          )}
        >
          {/* Summary */}
          {expandedContent.summary && (
            <div>
              <h4
                className="text-xs font-medium uppercase tracking-wide mb-2"
                style={{ color: "var(--text-secondary)" }}
              >
                Summary
              </h4>
              <p
                className="text-sm leading-relaxed"
                style={{ color: "var(--text-primary)" }}
              >
                {expandedContent.summary}
              </p>
            </div>
          )}

          {/* Commitments */}
          {((expandedContent.commitments?.ours ?? []).length > 0 ||
            (expandedContent.commitments?.theirs ?? []).length > 0) && (
            <div className="grid grid-cols-2 gap-4">
              {/* Our commitments */}
              {(expandedContent.commitments?.ours ?? []).length > 0 && (
                <div>
                  <h4
                    className="text-xs font-medium uppercase tracking-wide mb-2"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    Our Commitments ({(expandedContent.commitments?.ours ?? []).length})
                  </h4>
                  <ul className="space-y-1">
                    {(expandedContent.commitments?.ours ?? []).map((item, index) => (
                      <li
                        key={index}
                        className="text-sm flex items-start gap-2"
                        style={{ color: "var(--text-primary)" }}
                      >
                        <span className="text-emerald-600 mt-0.5">-</span>
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Their commitments */}
              {(expandedContent.commitments?.theirs ?? []).length > 0 && (
                <div>
                  <h4
                    className="text-xs font-medium uppercase tracking-wide mb-2"
                    style={{ color: "var(--text-secondary)" }}
                  >
                    Their Commitments ({(expandedContent.commitments?.theirs ?? []).length})
                  </h4>
                  <ul className="space-y-1">
                    {(expandedContent.commitments?.theirs ?? []).map((item, index) => (
                      <li
                        key={index}
                        className="text-sm flex items-start gap-2"
                        style={{ color: "var(--text-primary)" }}
                      >
                        <span className="text-blue-600 mt-0.5">-</span>
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Insights */}
          {(expandedContent.insights ?? []).length > 0 && (
            <div>
              <h4
                className="text-xs font-medium uppercase tracking-wide mb-2"
                style={{ color: "var(--text-secondary)" }}
              >
                Insights ({(expandedContent.insights ?? []).length})
              </h4>
              <div className="flex flex-wrap gap-2">
                {(expandedContent.insights ?? []).map((insight, index) => (
                  <span
                    key={index}
                    className={cn(
                      "px-2.5 py-1 rounded-full text-xs",
                      "bg-slate-100 text-slate-600"
                    )}
                  >
                    {insight}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// Skeleton for loading state
export function DebriefCardSkeleton() {
  return (
    <div
      className="rounded-xl border border-slate-200 bg-white p-4 animate-pulse"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 space-y-2">
          <div className="h-4 w-3/4 bg-slate-200 rounded" />
          <div className="h-3 w-1/2 bg-slate-100 rounded" />
        </div>
        <div className="h-5 w-12 bg-slate-100 rounded" />
      </div>
      <div className="mt-3 h-3 w-24 bg-slate-100 rounded" />
    </div>
  );
}
