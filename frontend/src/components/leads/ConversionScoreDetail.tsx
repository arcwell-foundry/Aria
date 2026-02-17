/**
 * ConversionScoreDetail - Expandable panel showing detailed conversion score
 *
 * Follows ARIA Design System v1.0:
 * - Probability gauge with color coding
 * - Confidence level indicator
 * - Feature importance horizontal bar chart
 * - Natural language explanation
 * - Refresh score button
 * - Historical trend mini-chart (last 5 scores)
 *
 * @example
 * <ConversionScoreDetail leadId="lead-123" />
 */

import { useState } from "react";
import { RefreshCw, ChevronDown, ChevronUp } from "lucide-react";
import { cn } from "@/utils/cn";
import { useConversionScore, useRefreshConversionScore } from "@/hooks/useConversionScore";
import { ConversionScoreBadge } from "./ConversionScoreBadge";
import type { FeatureDriver } from "@/api/leads";

export interface ConversionScoreDetailProps {
  /** Lead ID to fetch score for */
  leadId: string;
  /** Start expanded */
  defaultExpanded?: boolean;
  /** Additional CSS classes */
  className?: string;
}

type ScoreLevel = "high" | "medium" | "low";

function getScoreLevel(probability: number): ScoreLevel {
  if (probability >= 70) return "high";
  if (probability >= 40) return "medium";
  return "low";
}

const levelColors: Record<ScoreLevel, { main: string; bg: string; light: string }> = {
  high: {
    main: "var(--success)",
    bg: "rgba(107, 143, 113, 0.15)",
    light: "rgba(107, 143, 113, 0.3)",
  },
  medium: {
    main: "var(--warning)",
    bg: "rgba(184, 149, 106, 0.15)",
    light: "rgba(184, 149, 106, 0.3)",
  },
  low: {
    main: "var(--critical)",
    bg: "rgba(166, 107, 107, 0.15)",
    light: "rgba(166, 107, 107, 0.3)",
  },
};

// Probability Gauge Component
function ProbabilityGauge({ probability }: { probability: number }) {
  const level = getScoreLevel(probability);
  const colors = levelColors[level];
  const angle = (probability / 100) * 180;

  return (
    <div className="relative w-32 h-16 mx-auto">
      {/* Gauge background arc */}
      <svg viewBox="0 0 100 50" className="w-full h-full">
        {/* Background arc */}
        <path
          d="M 10 50 A 40 40 0 0 1 90 50"
          fill="none"
          stroke="var(--bg-subtle)"
          strokeWidth="8"
          strokeLinecap="round"
        />
        {/* Colored arc based on probability */}
        <path
          d="M 10 50 A 40 40 0 0 1 90 50"
          fill="none"
          stroke={colors.main}
          strokeWidth="8"
          strokeLinecap="round"
          strokeDasharray={`${angle * 0.7} 180`}
          style={{ transition: "stroke-dasharray 0.5s ease-out" }}
        />
        {/* Needle */}
        <line
          x1="50"
          y1="50"
          x2={50 + 35 * Math.cos((Math.PI * (180 - angle)) / 180)}
          y2={50 - 35 * Math.sin((Math.PI * (180 - angle)) / 180)}
          stroke={colors.main}
          strokeWidth="2"
          strokeLinecap="round"
          style={{ transition: "all 0.5s ease-out" }}
        />
        <circle cx="50" cy="50" r="4" fill={colors.main} />
      </svg>

      {/* Probability text */}
      <div className="absolute inset-0 flex items-end justify-center pb-1">
        <span className="text-xl font-bold" style={{ color: colors.main }}>
          {Math.round(probability)}%
        </span>
      </div>
    </div>
  );
}

// Confidence Level Badge
function ConfidenceBadge({ confidence }: { confidence: number }) {
  const level = confidence >= 0.7 ? "high" : confidence >= 0.4 ? "medium" : "low";
  const labels = { high: "High confidence", medium: "Medium confidence", low: "Low confidence" };
  const colors = {
    high: { bg: "rgba(107, 143, 113, 0.15)", text: "var(--success)" },
    medium: { bg: "rgba(184, 149, 106, 0.15)", text: "var(--warning)" },
    low: { bg: "rgba(166, 107, 107, 0.15)", text: "var(--critical)" },
  };

  return (
    <span
      className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium"
      style={{ backgroundColor: colors[level].bg, color: colors[level].text }}
    >
      {Math.round(confidence * 100)}% {labels[level]}
    </span>
  );
}

// Feature Importance Bar
function FeatureBar({ driver, isRisk = false }: { driver: FeatureDriver; isRisk?: boolean }) {
  const barColor = isRisk ? "var(--warning)" : "var(--success)";
  const percentage = Math.round(driver.contribution * 100);

  return (
    <div className="py-1.5">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium capitalize" style={{ color: "var(--text-primary)" }}>
          {driver.name.replace(/_/g, " ")}
        </span>
        <span className="text-xs font-mono" style={{ color: "var(--text-muted)" }}>
          {percentage}%
        </span>
      </div>
      <div
        className="h-1.5 rounded-full overflow-hidden"
        style={{ backgroundColor: "var(--bg-subtle)" }}
      >
        <div
          className="h-full rounded-full transition-all duration-300"
          style={{
            width: `${Math.min(driver.value * 100, 100)}%`,
            backgroundColor: barColor,
          }}
        />
      </div>
      <p className="text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
        {driver.description}
      </p>
    </div>
  );
}

// Loading Skeleton
function ScoreDetailSkeleton() {
  return (
    <div className="animate-pulse space-y-4">
      <div className="flex items-center justify-between">
        <div className="h-16 w-32 bg-[var(--border)] rounded" />
        <div className="h-6 w-24 bg-[var(--border)] rounded" />
      </div>
      <div className="h-4 w-3/4 bg-[var(--border)] rounded" />
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i}>
            <div className="h-3 w-24 bg-[var(--border)] rounded mb-1" />
            <div className="h-1.5 w-full bg-[var(--border)] rounded" />
          </div>
        ))}
      </div>
    </div>
  );
}

export function ConversionScoreDetail({
  leadId,
  defaultExpanded = false,
  className = "",
}: ConversionScoreDetailProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const { data: scoreData, isLoading, error } = useConversionScore(leadId, isExpanded);
  const refreshMutation = useRefreshConversionScore();

  const handleRefresh = () => {
    refreshMutation.mutate(leadId);
  };

  if (!isExpanded) {
    return (
      <div className={cn("flex items-center gap-3", className)}>
        {scoreData ? (
          <>
            <ConversionScoreBadge
              probability={scoreData.conversion_probability}
              confidence={scoreData.confidence}
              showConfidence
            />
            <button
              onClick={() => setIsExpanded(true)}
              className="text-xs flex items-center gap-1 hover:text-[var(--accent)] transition-colors"
              style={{ color: "var(--text-secondary)" }}
            >
              Details
              <ChevronDown className="w-3 h-3" />
            </button>
          </>
        ) : isLoading ? (
          <div className="h-5 w-16 bg-[var(--border)] rounded animate-pulse" />
        ) : (
          <button
            onClick={() => setIsExpanded(true)}
            className="text-xs flex items-center gap-1 hover:text-[var(--accent)] transition-colors"
            style={{ color: "var(--text-secondary)" }}
          >
            View Conversion Score
            <ChevronDown className="w-3 h-3" />
          </button>
        )}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "rounded-lg border p-4 space-y-4",
        className
      )}
      style={{
        backgroundColor: "var(--bg-elevated)",
        borderColor: "var(--border)",
      }}
      data-aria-id={`conversion-score-detail-${leadId}`}
    >
      {/* Header with collapse button */}
      <div className="flex items-center justify-between">
        <h3
          className="text-sm font-medium"
          style={{ color: "var(--text-primary)" }}
        >
          Conversion Probability
        </h3>
        <div className="flex items-center gap-2">
          <button
            onClick={handleRefresh}
            disabled={refreshMutation.isPending}
            className={cn(
              "p-1.5 rounded transition-colors",
              "hover:bg-[var(--bg-subtle)]",
              refreshMutation.isPending && "opacity-50 cursor-not-allowed"
            )}
            title="Refresh score"
          >
            <RefreshCw
              className={cn("w-4 h-4", refreshMutation.isPending && "animate-spin")}
              style={{ color: "var(--text-secondary)" }}
            />
          </button>
          <button
            onClick={() => setIsExpanded(false)}
            className="p-1 rounded hover:bg-[var(--bg-subtle)] transition-colors"
          >
            <ChevronUp className="w-4 h-4" style={{ color: "var(--text-secondary)" }} />
          </button>
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <ScoreDetailSkeleton />
      ) : error ? (
        <div
          className="p-3 rounded text-sm"
          style={{ backgroundColor: "var(--bg-subtle)", color: "var(--text-muted)" }}
        >
          Unable to load conversion score
        </div>
      ) : scoreData ? (
        <>
          {/* Gauge and Confidence */}
          <div className="flex items-center justify-between gap-4">
            <ProbabilityGauge
              probability={scoreData.conversion_probability}
            />
            <div className="flex flex-col items-end gap-1">
              <ConfidenceBadge confidence={scoreData.confidence} />
            </div>
          </div>

          {/* Summary */}
          <p
            className="text-sm leading-relaxed"
            style={{ color: "var(--text-secondary)" }}
          >
            {scoreData.summary}
          </p>

          {/* Key Drivers */}
          {scoreData.key_drivers.length > 0 && (
            <div>
              <h4
                className="text-xs font-medium mb-2 uppercase tracking-wide"
                style={{ color: "var(--text-muted)" }}
              >
                Key Strengths
              </h4>
              <div className="space-y-1">
                {scoreData.key_drivers.slice(0, 3).map((driver, index) => (
                  <FeatureBar key={index} driver={driver} isRisk={false} />
                ))}
              </div>
            </div>
          )}

          {/* Key Risks */}
          {scoreData.key_risks.length > 0 && (
            <div>
              <h4
                className="text-xs font-medium mb-2 uppercase tracking-wide"
                style={{ color: "var(--text-muted)" }}
              >
                Areas of Concern
              </h4>
              <div className="space-y-1">
                {scoreData.key_risks.slice(0, 2).map((driver, index) => (
                  <FeatureBar key={index} driver={driver} isRisk={true} />
                ))}
              </div>
            </div>
          )}

          {/* Recommendation */}
          <div
            className="p-3 rounded-lg"
            style={{ backgroundColor: "var(--bg-subtle)" }}
          >
            <h4
              className="text-xs font-medium mb-1 uppercase tracking-wide"
              style={{ color: "var(--text-muted)" }}
            >
              Recommendation
            </h4>
            <p className="text-sm" style={{ color: "var(--text-primary)" }}>
              {scoreData.recommendation}
            </p>
          </div>
        </>
      ) : null}
    </div>
  );
}
