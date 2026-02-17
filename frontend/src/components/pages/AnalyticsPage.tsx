/**
 * AnalyticsPage - Full Analytics Dashboard
 *
 * Comprehensive analytics dashboard with:
 * - KPI cards with delta percentages
 * - Conversion funnel visualization
 * - Activity trends line chart
 * - ARIA Impact and Response Time cards
 *
 * Follows ARIA Design System v1.0:
 * - LIGHT THEME (content pages use light background)
 * - Header with status dot
 * - Period selector with comparison toggle
 * - Recharts for all visualizations
 */

import { useState, useMemo } from "react";
import {
  Users,
  Calendar,
  Mail,
  Clock,
  TrendingUp,
  TrendingDown,
  Download,
  Loader2,
  Zap,
  Timer,
  ArrowRight,
} from "lucide-react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { cn } from "@/utils/cn";
import {
  useOverviewMetrics,
  useConversionFunnel,
  useActivityTrends,
  useAriaImpactSummary,
  useResponseTimeMetrics,
  useExportAnalytics,
} from "@/hooks/useAnalytics";
import { EmptyState } from "@/components/common/EmptyState";
import type { AnalyticsPeriod } from "@/api/analytics";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PERIOD_OPTIONS: { label: string; value: AnalyticsPeriod }[] = [
  { label: "7 Days", value: "7d" },
  { label: "30 Days", value: "30d" },
  { label: "90 Days", value: "90d" },
];

const STAGE_COLORS: Record<string, string> = {
  lead: "#94A3B8",
  opportunity: "#3B82F6",
  account: "#22C55E",
};

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function AnalyticsSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      {/* KPI cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="border border-[var(--border)] rounded-lg p-5"
            style={{ backgroundColor: "var(--bg-elevated)" }}
          >
            <div className="h-4 w-20 bg-[var(--border)] rounded mb-3" />
            <div className="h-8 w-16 bg-[var(--border)] rounded mb-2" />
            <div className="h-3 w-24 bg-[var(--border)] rounded" />
          </div>
        ))}
      </div>

      {/* Middle section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div
          className="border border-[var(--border)] rounded-lg p-5"
          style={{ backgroundColor: "var(--bg-elevated)" }}
        >
          <div className="h-4 w-32 bg-[var(--border)] rounded mb-4" />
          <div className="h-48 bg-[var(--border)] rounded" />
        </div>
        <div
          className="border border-[var(--border)] rounded-lg p-5"
          style={{ backgroundColor: "var(--bg-elevated)" }}
        >
          <div className="h-4 w-32 bg-[var(--border)] rounded mb-4" />
          <div className="h-48 bg-[var(--border)] rounded" />
        </div>
      </div>

      {/* Bottom section */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {Array.from({ length: 2 }).map((_, i) => (
          <div
            key={i}
            className="border border-[var(--border)] rounded-lg p-5"
            style={{ backgroundColor: "var(--bg-elevated)" }}
          >
            <div className="h-4 w-28 bg-[var(--border)] rounded mb-4" />
            <div className="space-y-3">
              {Array.from({ length: 4 }).map((__, j) => (
                <div key={j} className="flex justify-between">
                  <div className="h-3 w-24 bg-[var(--border)] rounded" />
                  <div className="h-3 w-12 bg-[var(--border)] rounded" />
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// KPICard
// ---------------------------------------------------------------------------

function KPICard({
  icon: Icon,
  title,
  value,
  unit,
  delta,
  comparisonEnabled,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  value: string | number;
  unit?: string;
  delta?: number | null;
  comparisonEnabled: boolean;
}) {
  const showDelta = comparisonEnabled && delta !== null && delta !== undefined;
  const isPositive = (delta ?? 0) >= 0;

  return (
    <div
      className="border border-[var(--border)] rounded-lg p-5"
      style={{ backgroundColor: "var(--bg-elevated)" }}
    >
      <div className="flex items-center gap-2 mb-3">
        <span style={{ color: "var(--accent)" }}>
          <Icon className="w-4 h-4" />
        </span>
        <span
          className="text-xs font-medium uppercase tracking-wider"
          style={{ color: "var(--text-secondary)" }}
        >
          {title}
        </span>
      </div>
      <div className="flex items-baseline gap-1.5">
        <span
          className="font-display text-3xl italic"
          style={{ color: "var(--text-primary)" }}
        >
          {value}
        </span>
        {unit && (
          <span
            className="font-mono text-xs"
            style={{ color: "var(--text-secondary)" }}
          >
            {unit}
          </span>
        )}
      </div>
      {showDelta && (
        <div
          className={cn(
            "flex items-center gap-1 mt-2 text-xs font-medium",
            isPositive ? "text-[var(--success)]" : "text-[var(--critical)]"
          )}
        >
          {isPositive ? (
            <TrendingUp className="w-3.5 h-3.5" />
          ) : (
            <TrendingDown className="w-3.5 h-3.5" />
          )}
          <span>{isPositive ? "+" : ""}{delta.toFixed(1)}%</span>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ConversionFunnelChart
// ---------------------------------------------------------------------------

function ConversionFunnelChart({
  data,
}: {
  data: { stages: Record<string, number>; conversion_rates: Record<string, number | null> };
}) {
  const { stages, conversion_rates } = data;
  const stageOrder = ["lead", "opportunity", "account"];
  const stageLabels: Record<string, string> = {
    lead: "Leads",
    opportunity: "Opportunities",
    account: "Accounts",
  };

  const chartData = stageOrder.map((stage) => ({
    name: stageLabels[stage] || stage,
    value: stages[stage] || 0,
    stage,
  }));

  const maxValue = Math.max(...chartData.map((d) => d.value), 1);

  return (
    <div
      className="border border-[var(--border)] rounded-lg p-5"
      style={{ backgroundColor: "var(--bg-elevated)" }}
    >
      <h3
        className="text-sm font-medium mb-4"
        style={{ color: "var(--text-primary)" }}
      >
        Conversion Funnel
      </h3>

      {/* Horizontal bar chart */}
      <div className="space-y-4">
        {chartData.map((item, index) => {
          const widthPercent = maxValue > 0 ? (item.value / maxValue) * 100 : 0;
          const prevStage = stageOrder[index - 1];
          const convKey = prevStage ? `${prevStage}_to_${item.stage}` : null;
          const convRate = convKey ? conversion_rates[convKey] : null;

          return (
            <div key={item.stage}>
              <div className="flex items-center justify-between mb-1.5">
                <span
                  className="text-xs font-medium"
                  style={{ color: "var(--text-primary)" }}
                >
                  {item.name}
                </span>
                <div className="flex items-center gap-3">
                  {convRate !== null && convRate !== undefined && (
                    <span
                      className="text-xs"
                      style={{ color: "var(--text-secondary)" }}
                    >
                      {index === 0 ? "" : `${(convRate * 100).toFixed(0)}% conv`}
                    </span>
                  )}
                  <span
                    className="font-mono text-xs font-medium"
                    style={{ color: "var(--text-primary)" }}
                  >
                    {item.value}
                  </span>
                </div>
              </div>
              <div
                className="h-8 rounded"
                style={{ backgroundColor: "var(--bg-subtle)" }}
              >
                <div
                  className="h-full rounded flex items-center justify-end pr-2 transition-all duration-300"
                  style={{
                    width: `${Math.max(widthPercent, item.value > 0 ? 8 : 0)}%`,
                    backgroundColor: STAGE_COLORS[item.stage] || "#94A3B8",
                  }}
                >
                  {item.value > 0 && widthPercent > 15 && (
                    <span className="text-xs text-white font-medium">
                      {item.value}
                    </span>
                  )}
                </div>
              </div>
              {index < chartData.length - 1 && (
                <div className="flex justify-center py-1">
                  <ArrowRight
                    className="w-4 h-4 rotate-90"
                    style={{ color: "var(--text-secondary)" }}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-4 pt-4 border-t border-[var(--border)]">
        {stageOrder.map((stage) => (
          <div key={stage} className="flex items-center gap-1.5">
            <div
              className="w-3 h-3 rounded-sm"
              style={{ backgroundColor: STAGE_COLORS[stage] }}
            />
            <span
              className="text-xs"
              style={{ color: "var(--text-secondary)" }}
            >
              {stageLabels[stage]}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ActivityTrendsChart
// ---------------------------------------------------------------------------

function ActivityTrendsChart({
  data,
}: {
  data: { series: Record<string, Record<string, number>> };
}) {
  const { series } = data;

  // Merge all series into unified data points
  const allDates = new Set<string>();
  Object.values(series).forEach((s) => {
    Object.keys(s).forEach((date) => allDates.add(date));
  });

  const sortedDates = Array.from(allDates).sort();
  const chartData = sortedDates.map((date) => ({
    date,
    label: new Date(date).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    }),
    emails: series.emails_sent[date] || 0,
    meetings: series.meetings[date] || 0,
    actions: series.aria_actions[date] || 0,
    leads: series.leads_created[date] || 0,
  }));

  // Take last 14 data points for readability
  const displayData = chartData.slice(-14);

  return (
    <div
      className="border border-[var(--border)] rounded-lg p-5"
      style={{ backgroundColor: "var(--bg-elevated)" }}
    >
      <h3
        className="text-sm font-medium mb-4"
        style={{ color: "var(--text-primary)" }}
      >
        Activity Trends
      </h3>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={displayData} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
          <defs>
            <linearGradient id="emailsGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#3B82F6" stopOpacity={0.2} />
              <stop offset="95%" stopColor="#3B82F6" stopOpacity={0} />
            </linearGradient>
            <linearGradient id="meetingsGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#22C55E" stopOpacity={0.2} />
              <stop offset="95%" stopColor="#22C55E" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis
            dataKey="label"
            tick={{ fontFamily: "JetBrains Mono", fontSize: 10, fill: "var(--text-secondary)" }}
            axisLine={{ stroke: "var(--border)" }}
            tickLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fontFamily: "JetBrains Mono", fontSize: 10, fill: "var(--text-secondary)" }}
            axisLine={{ stroke: "var(--border)" }}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: "var(--bg-elevated)",
              border: "1px solid var(--border)",
              borderRadius: "8px",
              fontFamily: "JetBrains Mono",
              fontSize: 11,
            }}
          />
          <Area
            type="monotone"
            dataKey="emails"
            name="Emails"
            stroke="#3B82F6"
            strokeWidth={2}
            fill="url(#emailsGradient)"
          />
          <Area
            type="monotone"
            dataKey="meetings"
            name="Meetings"
            stroke="#22C55E"
            strokeWidth={2}
            fill="url(#meetingsGradient)"
          />
        </AreaChart>
      </ResponsiveContainer>

      {/* Legend */}
      <div className="flex items-center gap-4 mt-4">
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-0.5 rounded" style={{ backgroundColor: "#3B82F6" }} />
          <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
            Emails Sent
          </span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-0.5 rounded" style={{ backgroundColor: "#22C55E" }} />
          <span className="text-xs" style={{ color: "var(--text-secondary)" }}>
            Meetings
          </span>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// AriaImpactCard
// ---------------------------------------------------------------------------

function AriaImpactCard({
  data,
}: {
  data: { total_actions: number; by_action_type: Record<string, number>; estimated_time_saved_minutes: number; pipeline_impact: Record<string, { count: number; estimated_value: number }> };
}) {
  const { total_actions, by_action_type, estimated_time_saved_minutes, pipeline_impact } = data;

  const hoursSaved = (estimated_time_saved_minutes / 60).toFixed(1);
  const actionTypes = Object.entries(by_action_type).slice(0, 5);
  const totalPipelineValue = Object.values(pipeline_impact).reduce(
    (sum, item) => sum + (item.estimated_value || 0),
    0
  );

  return (
    <div
      className="border border-[var(--border)] rounded-lg p-5"
      style={{ backgroundColor: "var(--bg-elevated)" }}
    >
      <div className="flex items-center gap-2 mb-4">
        <span style={{ color: "var(--accent)" }}>
          <Zap className="w-4 h-4" />
        </span>
        <h3
          className="text-sm font-medium"
          style={{ color: "var(--text-primary)" }}
        >
          ARIA Impact
        </h3>
      </div>

      {/* Summary metrics */}
      <div className="grid grid-cols-2 gap-4 mb-4">
        <div>
          <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
            Total Actions
          </p>
          <p className="text-xl font-semibold" style={{ color: "var(--text-primary)" }}>
            {total_actions}
          </p>
        </div>
        <div>
          <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
            Time Saved
          </p>
          <p className="text-xl font-semibold" style={{ color: "var(--text-primary)" }}>
            {hoursSaved} hrs
          </p>
        </div>
      </div>

      {/* Actions breakdown */}
      {actionTypes.length > 0 && (
        <div className="space-y-2">
          <p className="text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
            Actions by Type
          </p>
          {actionTypes.map(([type, count]) => (
            <div key={type} className="flex items-center justify-between">
              <span className="text-xs capitalize" style={{ color: "var(--text-secondary)" }}>
                {type.replace(/_/g, " ")}
              </span>
              <span
                className="font-mono text-xs font-medium"
                style={{ color: "var(--text-primary)" }}
              >
                {count}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* Pipeline value */}
      {totalPipelineValue > 0 && (
        <div className="mt-4 pt-4 border-t border-[var(--border)]">
          <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
            Pipeline Value Influenced
          </p>
          <p className="text-lg font-semibold" style={{ color: "var(--success)" }}>
            ${totalPipelineValue.toLocaleString()}
          </p>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ResponseTimeCard
// ---------------------------------------------------------------------------

function ResponseTimeCard({
  data,
}: {
  data: { avg_response_minutes: number | null; trend: Array<{ date: string; avg_response_minutes: number }> };
}) {
  const { avg_response_minutes, trend } = data;

  // Calculate trend direction
  let trendDirection: "up" | "down" | "stable" = "stable";
  if (trend.length >= 2) {
    const recent = trend.slice(-3);
    const older = trend.slice(-6, -3);
    if (recent.length > 0 && older.length > 0) {
      const recentAvg = recent.reduce((s, r) => s + r.avg_response_minutes, 0) / recent.length;
      const olderAvg = older.reduce((s, r) => s + r.avg_response_minutes, 0) / older.length;
      if (recentAvg < olderAvg * 0.9) trendDirection = "down";
      else if (recentAvg > olderAvg * 1.1) trendDirection = "up";
    }
  }

  const formatTime = (minutes: number | null) => {
    if (minutes === null) return "--";
    if (minutes < 60) return `${Math.round(minutes)}m`;
    const hours = Math.floor(minutes / 60);
    const mins = Math.round(minutes % 60);
    return mins > 0 ? `${hours}h ${mins}m` : `${hours}h`;
  };

  return (
    <div
      className="border border-[var(--border)] rounded-lg p-5"
      style={{ backgroundColor: "var(--bg-elevated)" }}
    >
      <div className="flex items-center gap-2 mb-4">
        <span style={{ color: "var(--accent)" }}>
          <Timer className="w-4 h-4" />
        </span>
        <h3
          className="text-sm font-medium"
          style={{ color: "var(--text-primary)" }}
        >
          Response Time
        </h3>
      </div>

      {/* Main metric */}
      <div className="mb-4">
        <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
          Average Response Time
        </p>
        <div className="flex items-center gap-2">
          <p className="text-2xl font-semibold" style={{ color: "var(--text-primary)" }}>
            {formatTime(avg_response_minutes)}
          </p>
          {avg_response_minutes !== null && (
            <span
              className={cn(
                "text-xs px-2 py-0.5 rounded-full",
                trendDirection === "down"
                  ? "bg-[var(--success)]/10 text-[var(--success)]"
                  : trendDirection === "up"
                    ? "bg-[var(--critical)]/10 text-[var(--critical)]"
                    : "bg-[var(--text-secondary)]/10 text-[var(--text-secondary)]"
              )}
            >
              {trendDirection === "down" ? "Improving" : trendDirection === "up" ? "Slower" : "Stable"}
            </span>
          )}
        </div>
      </div>

      {/* Mini trend chart */}
      {trend.length > 1 && (
        <ResponsiveContainer width="100%" height={60}>
          <AreaChart data={trend.slice(-14)} margin={{ top: 0, right: 0, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id="responseGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#64748B" stopOpacity={0.2} />
                <stop offset="95%" stopColor="#64748B" stopOpacity={0} />
              </linearGradient>
            </defs>
            <Area
              type="monotone"
              dataKey="avg_response_minutes"
              stroke="#64748B"
              strokeWidth={1.5}
              fill="url(#responseGradient)"
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// AnalyticsDashboard (internal)
// ---------------------------------------------------------------------------

function AnalyticsDashboard() {
  const [period, setPeriod] = useState<AnalyticsPeriod>("30d");
  const [comparisonEnabled, setComparisonEnabled] = useState(true);

  const { data: overview, isLoading: overviewLoading } = useOverviewMetrics(period);
  const { data: funnel } = useConversionFunnel(period);
  const { data: trends } = useActivityTrends(period, "day");
  const { data: impact } = useAriaImpactSummary(period);
  const { data: responseTimes } = useResponseTimeMetrics(period);
  const exportMutation = useExportAnalytics();

  const isLoading = overviewLoading;

  const handleExport = () => {
    exportMutation.mutate({ period, format: "csv" });
  };

  // Calculate deltas for KPIs (using previous period comparison)
  const deltas = useMemo(() => {
    if (!overview) return {};
    // These would come from a period comparison endpoint
    // For now, we'll show placeholders
    return {
      leads_created: null,
      meetings_booked: null,
      emails_sent: null,
      time_saved_minutes: null,
    };
  }, [overview]);

  return (
    <div className="max-w-6xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span
            className="w-3 h-3 rounded-full shrink-0"
            style={{ backgroundColor: "var(--success)" }}
          />
          <div>
            <p
              className="font-mono text-xs uppercase tracking-wider"
              style={{ color: "var(--text-secondary)" }}
            >
              Dashboard
            </p>
            <h1
              className="font-display text-2xl italic"
              style={{ color: "var(--text-primary)" }}
            >
              Analytics
            </h1>
          </div>
        </div>

        <button
          type="button"
          onClick={handleExport}
          disabled={exportMutation.isPending || !overview}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors duration-150 disabled:opacity-50"
          style={{
            backgroundColor: "var(--bg-subtle)",
            color: "var(--text-secondary)",
          }}
        >
          {exportMutation.isPending ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Download className="w-3.5 h-3.5" />
          )}
          Export CSV
        </button>
      </div>

      <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
        Track your team&apos;s performance and ARIA&apos;s impact on your workflow.
      </p>

      {/* Controls row */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-4">
          {/* Period selector */}
          <div className="flex gap-2">
            {PERIOD_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                type="button"
                onClick={() => setPeriod(opt.value)}
                className={cn(
                  "px-3 py-1.5 rounded-full text-xs font-medium transition-colors duration-150",
                  period === opt.value
                    ? "bg-[var(--accent)] text-white"
                    : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
                )}
                style={
                  period === opt.value
                    ? undefined
                    : { backgroundColor: "var(--bg-subtle)" }
                }
              >
                {opt.label}
              </button>
            ))}
          </div>

          {/* Comparison toggle */}
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={comparisonEnabled}
              onChange={(e) => setComparisonEnabled(e.target.checked)}
              className="w-4 h-4 rounded border-[var(--border)] accent-[var(--accent)]"
            />
            <span
              className="text-xs"
              style={{ color: "var(--text-secondary)" }}
            >
              Show comparison
            </span>
          </label>
        </div>
      </div>

      {/* Content */}
      {isLoading && <AnalyticsSkeleton />}

      {!isLoading && !overview && (
        <EmptyState
          title="No analytics data available yet."
          description="As you use ARIA, performance metrics and activity data will appear here."
        />
      )}

      {!isLoading && overview && (
        <>
          {/* KPI cards row */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <KPICard
              icon={Users}
              title="Leads Created"
              value={overview.leads_created}
              delta={deltas.leads_created}
              comparisonEnabled={comparisonEnabled}
            />
            <KPICard
              icon={Calendar}
              title="Meetings Booked"
              value={overview.meetings_booked}
              delta={deltas.meetings_booked}
              comparisonEnabled={comparisonEnabled}
            />
            <KPICard
              icon={Mail}
              title="Emails Sent"
              value={overview.emails_sent}
              delta={deltas.emails_sent}
              comparisonEnabled={comparisonEnabled}
            />
            <KPICard
              icon={Clock}
              title="Time Saved by ARIA"
              value={(overview.time_saved_minutes / 60).toFixed(1)}
              unit="hrs"
              delta={deltas.time_saved_minutes}
              comparisonEnabled={comparisonEnabled}
            />
          </div>

          {/* Middle section: Funnel + Trends */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {funnel && <ConversionFunnelChart data={funnel} />}
            {trends && <ActivityTrendsChart data={trends} />}
          </div>

          {/* Bottom section: Impact + Response Time */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {impact && <AriaImpactCard data={impact} />}
            {responseTimes && <ResponseTimeCard data={responseTimes} />}
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// AnalyticsPage (exported wrapper)
// ---------------------------------------------------------------------------

export function AnalyticsPage() {
  return (
    <div
      className="flex-1 flex flex-col h-full"
      style={{ backgroundColor: "var(--bg-primary)" }}
      data-aria-id="analytics-page"
    >
      <div className="flex-1 overflow-y-auto p-8">
        <AnalyticsDashboard />
      </div>
    </div>
  );
}
