import { useState } from "react";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useReadiness } from "@/hooks/useOnboarding";

type ConfidenceModifier = "low" | "moderate" | "high" | "very_high";

interface ReadinessScoreBarProps {
  score: number;
  label: string;
  color: string;
}

function ReadinessScoreBar({ score, label, color }: ReadinessScoreBarProps) {
  const clampedScore = Math.max(0, Math.min(100, score));

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between">
        <span className="font-sans text-[13px] text-[#8B92A5]">{label}</span>
        <span className="font-mono text-[13px]" style={{ color }}>
          {Math.round(clampedScore)}%
        </span>
      </div>
      <div className="h-1.5 w-full bg-[#1E2235] rounded-full overflow-hidden">
        <div
          className="h-full rounded-full transition-all duration-300 ease-out"
          style={{
            width: `${clampedScore}%`,
            backgroundColor: color,
          }}
        />
      </div>
    </div>
  );
}

export function ReadinessIndicator() {
  const [isExpanded, setIsExpanded] = useState(false);
  const { data: readiness, isLoading } = useReadiness();

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#161B2E] border border-[#2A2F42]">
        <div className="h-4 w-20 bg-[#1E2235] rounded animate-pulse" />
      </div>
    );
  }

  if (!readiness) {
    return null;
  }

  const getColor = (score: number): string => {
    if (score < 30) return "#A66B6B"; // critical (red/muted)
    if (score < 60) return "#B8956A"; // warning (amber)
    if (score < 80) return "#6B7FA3"; // info (blue)
    return "#6B8F71"; // success (green)
  };

  const color = getColor(readiness.overall);
  const modifierLabel: Record<ConfidenceModifier, string> = {
    low: "Building understanding",
    moderate: "Getting to know you",
    high: "Well initialized",
    very_high: "Fully operational",
  };

  return (
    <div className="relative">
      {/* Compact indicator - always visible */}
      <button
        type="button"
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[#161B2E] border border-[#2A2F42] hover:border-[#7B8EAA] transition-colors duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-[#7B8EAA] focus:ring-offset-2 focus:ring-offset-[#0F1117] min-h-[36px]"
        aria-expanded={isExpanded}
        aria-label={`ARIA readiness: ${Math.round(readiness.overall)}% — click for details`}
      >
        {/* Status dot */}
        <div
          className="w-2 h-2 rounded-full"
          style={{ backgroundColor: color }}
          aria-hidden="true"
        />
        {/* Percentage */}
        <span className="font-mono text-[13px] text-[#E8E6E1]">
          {Math.round(readiness.overall)}%
        </span>
        {/* Expand/collapse icon */}
        {isExpanded ? (
          <ChevronUp size={14} strokeWidth={1.5} className="text-[#8B92A5]" aria-hidden="true" />
        ) : (
          <ChevronDown size={14} strokeWidth={1.5} className="text-[#8B92A5]" aria-hidden="true" />
        )}
      </button>

      {/* Expanded panel - shows on click */}
      {isExpanded && (
        <div
          className="absolute top-full right-0 mt-2 w-72 bg-[#161B2E] border border-[#2A2F42] rounded-xl shadow-lg p-4 z-50 animate-in fade-in slide-in-from-top-2 duration-200"
          role="dialog"
          aria-label="Readiness breakdown"
        >
          {/* Header with overall score */}
          <div className="flex flex-col gap-1 pb-4 border-b border-[#2A2F42]">
            <div className="flex items-center justify-between">
              <span className="font-display text-[18px] text-[#E8E6E1]">
                ARIA Readiness
              </span>
              <div
                className="w-3 h-3 rounded-full"
                style={{ backgroundColor: color }}
                aria-hidden="true"
              />
            </div>
            <p className="font-sans text-[13px] text-[#8B92A5]">
              {modifierLabel[readiness.confidence_modifier as ConfidenceModifier]}
            </p>
          </div>

          {/* Domain breakdown */}
          <div className="flex flex-col gap-4 pt-4">
            <ReadinessScoreBar
              score={readiness.corporate_memory}
              label="Corporate Memory"
              color={getColor(readiness.corporate_memory)}
            />
            <ReadinessScoreBar
              score={readiness.digital_twin}
              label="Digital Twin"
              color={getColor(readiness.digital_twin)}
            />
            <ReadinessScoreBar
              score={readiness.relationship_graph}
              label="Relationship Graph"
              color={getColor(readiness.relationship_graph)}
            />
            <ReadinessScoreBar
              score={readiness.integrations}
              label="Integrations"
              color={getColor(readiness.integrations)}
            />
            <ReadinessScoreBar
              score={readiness.goal_clarity}
              label="Goal Clarity"
              color={getColor(readiness.goal_clarity)}
            />
          </div>

          {/* Footer note */}
          <div className="pt-4 mt-2 border-t border-[#2A2F42]">
            <p className="font-sans text-[11px] text-[#8B92A5] leading-relaxed">
              Readiness reflects how well ARIA understands your company, your style, and your goals.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}
