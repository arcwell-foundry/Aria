/**
 * ConversionScoreBadge - Small badge showing conversion probability
 *
 * Follows ARIA Design System v1.0:
 * - Color coding: green (>70%), amber (40-70%), red (<40%)
 * - Shows percentage with confidence indicator
 * - Compact for use in lead list cards and tables
 *
 * @example
 * <ConversionScoreBadge probability={85} confidence={0.9} />
 * <ConversionScoreBadge probability={35} size="sm" />
 */

import { cn } from "@/utils/cn";

export interface ConversionScoreBadgeProps {
  /** Conversion probability (0-100) */
  probability: number;
  /** Confidence level (0-1) - affects opacity/badge style */
  confidence?: number;
  /** Size variant */
  size?: "sm" | "md";
  /** Show confidence indicator */
  showConfidence?: boolean;
  /** Additional CSS classes */
  className?: string;
}

type ScoreLevel = "high" | "medium" | "low";

function getScoreLevel(probability: number): ScoreLevel {
  if (probability >= 70) return "high";
  if (probability >= 40) return "medium";
  return "low";
}

const levelColors: Record<ScoreLevel, { bg: string; text: string; border: string }> = {
  high: {
    bg: "rgba(107, 143, 113, 0.15)",
    text: "var(--success)",
    border: "var(--success)",
  },
  medium: {
    bg: "rgba(184, 149, 106, 0.15)",
    text: "var(--warning)",
    border: "var(--warning)",
  },
  low: {
    bg: "rgba(166, 107, 107, 0.15)",
    text: "var(--critical)",
    border: "var(--critical)",
  },
};

const sizeStyles = {
  sm: {
    container: "px-2 py-0.5 text-xs gap-1",
    icon: "w-3 h-3",
  },
  md: {
    container: "px-2.5 py-1 text-xs gap-1.5",
    icon: "w-3.5 h-3.5",
  },
};

export function ConversionScoreBadge({
  probability,
  confidence = 1,
  size = "md",
  showConfidence = false,
  className = "",
}: ConversionScoreBadgeProps) {
  const clampedProbability = Math.min(100, Math.max(0, probability));
  const level = getScoreLevel(clampedProbability);
  const colors = levelColors[level];

  // Adjust opacity based on confidence (lower confidence = slightly muted)
  const opacityStyle = confidence < 0.5 ? { opacity: 0.7 } : {};

  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border font-medium transition-all duration-200",
        sizeStyles[size].container,
        className
      )}
      style={{
        backgroundColor: colors.bg,
        color: colors.text,
        borderColor: `${colors.border}30`,
        ...opacityStyle,
      }}
      title={
        showConfidence
          ? `Conversion probability: ${Math.round(clampedProbability)}% (confidence: ${Math.round(confidence * 100)}%)`
          : `Conversion probability: ${Math.round(clampedProbability)}%`
      }
    >
      {/* Probability percentage */}
      <span className="font-medium">
        {Math.round(clampedProbability)}%
      </span>

      {/* Confidence indicator (optional) */}
      {showConfidence && (
        <span
          className={cn("opacity-60", sizeStyles[size].icon)}
          style={{ color: colors.text }}
        >
          {confidence >= 0.7 ? "●" : confidence >= 0.4 ? "◐" : "○"}
        </span>
      )}
    </span>
  );
}
