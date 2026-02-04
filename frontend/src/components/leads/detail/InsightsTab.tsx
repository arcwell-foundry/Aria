import {
  AlertTriangle,
  CheckCircle2,
  Lightbulb,
  ShieldAlert,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import type { Insight, InsightType } from "@/api/leads";

interface InsightsTabProps {
  insights: Insight[];
  isLoading: boolean;
}

// Configuration for each insight type
const insightConfig: Record<
  InsightType,
  {
    label: string;
    icon: React.ComponentType<{ className?: string }>;
    color: string;
    bg: string;
  }
> = {
  objection: {
    label: "Objections",
    icon: AlertTriangle,
    color: "text-amber-400",
    bg: "bg-amber-500/20",
  },
  buying_signal: {
    label: "Buying Signals",
    icon: TrendingUp,
    color: "text-emerald-400",
    bg: "bg-emerald-500/20",
  },
  commitment: {
    label: "Commitments",
    icon: CheckCircle2,
    color: "text-blue-400",
    bg: "bg-blue-500/20",
  },
  risk: {
    label: "Risks",
    icon: ShieldAlert,
    color: "text-red-400",
    bg: "bg-red-500/20",
  },
  opportunity: {
    label: "Opportunities",
    icon: Sparkles,
    color: "text-purple-400",
    bg: "bg-purple-500/20",
  },
};

// Display order for insight types
const insightTypeOrder: InsightType[] = [
  "objection",
  "buying_signal",
  "commitment",
  "risk",
  "opportunity",
];

function formatDate(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    return "Today";
  } else if (diffDays === 1) {
    return "Yesterday";
  } else if (diffDays < 7) {
    return `${diffDays} days ago`;
  } else if (diffDays < 30) {
    const weeks = Math.floor(diffDays / 7);
    return `${weeks} week${weeks > 1 ? "s" : ""} ago`;
  } else {
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    });
  }
}

interface InsightCardProps {
  insight: Insight;
}

function InsightCard({ insight }: InsightCardProps) {
  const config = insightConfig[insight.insight_type];
  const Icon = config.icon;
  const isAddressed = insight.addressed_at !== null;
  const confidencePercent = Math.round(insight.confidence * 100);

  return (
    <div
      className={`group relative bg-slate-800/40 backdrop-blur-sm border border-slate-700/50 rounded-xl p-4 transition-all duration-300 hover:bg-slate-800/60 hover:border-slate-600/50 ${
        isAddressed ? "opacity-60" : ""
      }`}
    >
      <div className="flex items-start gap-3">
        {/* Icon */}
        <div
          className={`flex-shrink-0 w-9 h-9 ${config.bg} rounded-lg flex items-center justify-center`}
        >
          <Icon className={`w-5 h-5 ${config.color}`} />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <p className="text-sm text-slate-200 mb-2 leading-relaxed">
            {insight.content}
          </p>

          {/* Meta info row */}
          <div className="flex items-center flex-wrap gap-x-3 gap-y-1.5">
            {/* Detection date */}
            <span className="text-xs text-slate-500">
              Detected {formatDate(insight.detected_at)}
            </span>

            {/* Confidence indicator */}
            <div className="flex items-center gap-1.5">
              <div className="w-12 h-1.5 bg-slate-700/50 rounded-full overflow-hidden">
                <div
                  className={`h-full ${config.bg.replace("/20", "/60")} rounded-full transition-all duration-300`}
                  style={{ width: `${confidencePercent}%` }}
                />
              </div>
              <span className="text-xs text-slate-500">
                {confidencePercent}%
              </span>
            </div>

            {/* Addressed badge */}
            {isAddressed && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 bg-emerald-500/10 text-emerald-400 text-xs rounded-full">
                <CheckCircle2 className="w-3 h-3" />
                Addressed
              </span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

interface InsightGroupProps {
  type: InsightType;
  insights: Insight[];
}

function InsightGroup({ type, insights }: InsightGroupProps) {
  const config = insightConfig[type];
  const Icon = config.icon;

  return (
    <div className="mb-6 last:mb-0">
      {/* Group heading */}
      <div className="flex items-center gap-2 mb-3">
        <Icon className={`w-4 h-4 ${config.color}`} />
        <h3 className={`text-sm font-semibold ${config.color}`}>
          {config.label}
        </h3>
        <span className="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 bg-slate-700/50 text-slate-300 text-xs font-medium rounded-full">
          {insights.length}
        </span>
      </div>

      {/* Insight cards */}
      <div className="space-y-3">
        {insights.map((insight) => (
          <InsightCard key={insight.id} insight={insight} />
        ))}
      </div>
    </div>
  );
}

function InsightsSkeleton() {
  return (
    <div className="space-y-6">
      {[...Array(3)].map((_, groupIdx) => (
        <div key={groupIdx}>
          {/* Group heading skeleton */}
          <div className="flex items-center gap-2 mb-3 animate-pulse">
            <div className="w-4 h-4 bg-slate-700 rounded" />
            <div className="h-4 bg-slate-700 rounded w-24" />
            <div className="w-5 h-5 bg-slate-700 rounded-full" />
          </div>

          {/* Cards skeleton */}
          <div className="space-y-3">
            {[...Array(2)].map((_, cardIdx) => (
              <div
                key={cardIdx}
                className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-4 animate-pulse"
              >
                <div className="flex items-start gap-3">
                  <div className="w-9 h-9 bg-slate-700 rounded-lg shrink-0" />
                  <div className="flex-1">
                    <div className="h-4 bg-slate-700 rounded w-full mb-2" />
                    <div className="h-4 bg-slate-700 rounded w-3/4 mb-3" />
                    <div className="flex items-center gap-3">
                      <div className="h-3 bg-slate-700 rounded w-20" />
                      <div className="w-12 h-1.5 bg-slate-700 rounded-full" />
                      <div className="h-3 bg-slate-700 rounded w-8" />
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyInsights() {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4">
      <div className="w-16 h-16 bg-slate-800/50 rounded-2xl flex items-center justify-center mb-4 border border-slate-700/50">
        <Lightbulb className="w-8 h-8 text-slate-500" />
      </div>
      <h3 className="text-lg font-semibold text-white mb-2">No insights yet</h3>
      <p className="text-slate-400 text-center max-w-sm">
        ARIA will automatically detect objections, buying signals, commitments,
        risks, and opportunities as you interact with this lead.
      </p>
    </div>
  );
}

export function InsightsTab({ insights, isLoading }: InsightsTabProps) {
  if (isLoading) {
    return <InsightsSkeleton />;
  }

  if (insights.length === 0) {
    return <EmptyInsights />;
  }

  // Group insights by type
  const insightsByType = insights.reduce(
    (acc, insight) => {
      const type = insight.insight_type;
      if (!acc[type]) {
        acc[type] = [];
      }
      acc[type].push(insight);
      return acc;
    },
    {} as Record<InsightType, Insight[]>
  );

  // Sort insights within each group by detection date (most recent first)
  for (const type of Object.keys(insightsByType) as InsightType[]) {
    insightsByType[type].sort(
      (a, b) =>
        new Date(b.detected_at).getTime() - new Date(a.detected_at).getTime()
    );
  }

  return (
    <div>
      {insightTypeOrder.map((type) => {
        const typeInsights = insightsByType[type];
        if (!typeInsights || typeInsights.length === 0) {
          return null;
        }
        return <InsightGroup key={type} type={type} insights={typeInsights} />;
      })}
    </div>
  );
}
