/**
 * AnalyticsPage - ROI Dashboard
 *
 * Follows ARIA Design System v1.0:
 * - LIGHT THEME (content pages use light background)
 * - Header: "Analytics // ROI Dashboard" with status dot
 * - Period selector chips (This Week / Month / Quarter)
 * - Metric cards grid, Recharts trend chart, breakdown sections
 * - Export CSV button
 */

import { useState } from 'react';
import {
  Clock,
  Brain,
  Zap,
  TrendingUp,
  Download,
  Loader2,
} from 'lucide-react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { cn } from '@/utils/cn';
import { useROIMetrics, useROITrend, useExportROIReport } from '@/hooks/useROI';
import { EmptyState } from '@/components/common/EmptyState';
import type { ROIPeriod, ROIMetricsResponse } from '@/api/roi';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const PERIOD_OPTIONS: { label: string; value: ROIPeriod }[] = [
  { label: 'This Week', value: '7d' },
  { label: 'This Month', value: '30d' },
  { label: 'This Quarter', value: '90d' },
];

// ---------------------------------------------------------------------------
// Skeleton
// ---------------------------------------------------------------------------

function AnalyticsSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      {/* Metric cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="border border-[var(--border)] rounded-lg p-5"
            style={{ backgroundColor: 'var(--bg-elevated)' }}
          >
            <div className="h-4 w-20 bg-[var(--border)] rounded mb-3" />
            <div className="h-8 w-16 bg-[var(--border)] rounded mb-2" />
            <div className="h-3 w-24 bg-[var(--border)] rounded" />
          </div>
        ))}
      </div>

      {/* Chart */}
      <div
        className="border border-[var(--border)] rounded-lg p-5"
        style={{ backgroundColor: 'var(--bg-elevated)' }}
      >
        <div className="h-4 w-32 bg-[var(--border)] rounded mb-4" />
        <div className="h-64 bg-[var(--border)] rounded" />
      </div>

      {/* Breakdowns */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="border border-[var(--border)] rounded-lg p-5"
            style={{ backgroundColor: 'var(--bg-elevated)' }}
          >
            <div className="h-4 w-28 bg-[var(--border)] rounded mb-4" />
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((__, j) => (
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
// MetricCard
// ---------------------------------------------------------------------------

function MetricCard({
  icon: Icon,
  title,
  value,
  unit,
  subtitle,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  value: string | number;
  unit?: string;
  subtitle?: string;
}) {
  return (
    <div
      className="border border-[var(--border)] rounded-lg p-5"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
    >
      <div className="flex items-center gap-2 mb-3">
        <span style={{ color: 'var(--accent)' }}>
          <Icon className="w-4 h-4" />
        </span>
        <span
          className="text-xs font-medium uppercase tracking-wider"
          style={{ color: 'var(--text-secondary)' }}
        >
          {title}
        </span>
      </div>
      <div className="flex items-baseline gap-1.5">
        <span
          className="font-display text-3xl italic"
          style={{ color: 'var(--text-primary)' }}
        >
          {value}
        </span>
        {unit && (
          <span
            className="font-mono text-xs"
            style={{ color: 'var(--text-secondary)' }}
          >
            {unit}
          </span>
        )}
      </div>
      {subtitle && (
        <p
          className="text-xs mt-1"
          style={{ color: 'var(--text-secondary)' }}
        >
          {subtitle}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// TrendChart
// ---------------------------------------------------------------------------

function TrendChart({ data }: { data: { week_start: string; hours_saved: number }[] }) {
  const chartData = data.map((d) => ({
    ...d,
    label: new Date(d.week_start).toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
    }),
  }));

  return (
    <div
      className="border border-[var(--border)] rounded-lg p-5"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
    >
      <h3
        className="text-sm font-medium mb-4"
        style={{ color: 'var(--text-primary)' }}
      >
        Hours Saved Over Time
      </h3>
      <ResponsiveContainer width="100%" height={256}>
        <AreaChart data={chartData} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
          <defs>
            <linearGradient id="hoursGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#2E66FF" stopOpacity={0.2} />
              <stop offset="95%" stopColor="#2E66FF" stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis
            dataKey="label"
            tick={{ fontFamily: 'JetBrains Mono', fontSize: 11, fill: 'var(--text-secondary)' }}
            axisLine={{ stroke: 'var(--border)' }}
            tickLine={false}
          />
          <YAxis
            tick={{ fontFamily: 'JetBrains Mono', fontSize: 11, fill: 'var(--text-secondary)' }}
            axisLine={{ stroke: 'var(--border)' }}
            tickLine={false}
          />
          <Tooltip
            contentStyle={{
              backgroundColor: 'var(--bg-elevated)',
              border: '1px solid var(--border)',
              borderRadius: '8px',
              fontFamily: 'JetBrains Mono',
              fontSize: 12,
              color: 'var(--text-primary)',
            }}
            formatter={(value: number) => [`${value} hrs`, 'Saved']}
          />
          <Area
            type="monotone"
            dataKey="hours_saved"
            stroke="#2E66FF"
            strokeWidth={2}
            fill="url(#hoursGradient)"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// BreakdownSection
// ---------------------------------------------------------------------------

function BreakdownSection({
  title,
  rows,
}: {
  title: string;
  rows: { label: string; value: string | number }[];
}) {
  return (
    <div
      className="border border-[var(--border)] rounded-lg p-5"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
    >
      <h3
        className="text-sm font-medium mb-4"
        style={{ color: 'var(--text-primary)' }}
      >
        {title}
      </h3>
      <div className="space-y-3">
        {rows.map((row) => (
          <div key={row.label} className="flex items-center justify-between">
            <span
              className="text-xs"
              style={{ color: 'var(--text-secondary)' }}
            >
              {row.label}
            </span>
            <span
              className="font-mono text-xs font-medium"
              style={{ color: 'var(--text-primary)' }}
            >
              {row.value}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildBreakdowns(data: ROIMetricsResponse) {
  const ts = data.time_saved.breakdown;
  return {
    timeSaved: [
      { label: 'Email Drafts', value: `${ts.email_drafts.estimated_hours.toFixed(1)} hrs` },
      { label: 'Meeting Prep', value: `${ts.meeting_prep.estimated_hours.toFixed(1)} hrs` },
      { label: 'Research Reports', value: `${ts.research_reports.estimated_hours.toFixed(1)} hrs` },
      { label: 'CRM Updates', value: `${ts.crm_updates.estimated_hours.toFixed(1)} hrs` },
    ],
    intelligence: [
      { label: 'Facts Discovered', value: data.intelligence_delivered.facts_discovered },
      { label: 'Signals Detected', value: data.intelligence_delivered.signals_detected },
      { label: 'Gaps Filled', value: data.intelligence_delivered.gaps_filled },
      { label: 'Briefings Generated', value: data.intelligence_delivered.briefings_generated },
    ],
    actions: [
      { label: 'Auto-Approved', value: data.actions_taken.auto_approved },
      { label: 'User-Approved', value: data.actions_taken.user_approved },
      { label: 'Rejected', value: data.actions_taken.rejected },
    ],
    pipeline: [
      { label: 'Leads Discovered', value: data.pipeline_impact.leads_discovered },
      { label: 'Meetings Prepped', value: data.pipeline_impact.meetings_prepped },
      { label: 'Follow-Ups Sent', value: data.pipeline_impact.follow_ups_sent },
    ],
  };
}

// ---------------------------------------------------------------------------
// AnalyticsDashboard (internal)
// ---------------------------------------------------------------------------

function AnalyticsDashboard() {
  const [period, setPeriod] = useState<ROIPeriod>('30d');
  const { data, isLoading, error } = useROIMetrics(period);
  const { data: trendData } = useROITrend(period);
  const exportReport = useExportROIReport();

  const handleExport = () => {
    exportReport.mutate(period);
  };

  const intelTotal = data
    ? data.intelligence_delivered.facts_discovered +
      data.intelligence_delivered.signals_detected +
      data.intelligence_delivered.gaps_filled +
      data.intelligence_delivered.briefings_generated
    : 0;

  const approvalRate = data?.action_approval_rate;

  const breakdowns = data ? buildBreakdowns(data) : null;

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      {/* Header */}
      <div className="flex items-center gap-3">
        <span
          className="w-3 h-3 rounded-full shrink-0"
          style={{ backgroundColor: 'var(--success)' }}
        />
        <div>
          <p
            className="font-mono text-xs uppercase tracking-wider"
            style={{ color: 'var(--text-secondary)' }}
          >
            Analytics
          </p>
          <h1
            className="font-display text-2xl italic"
            style={{ color: 'var(--text-primary)' }}
          >
            ROI Dashboard
          </h1>
        </div>
      </div>

      <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
        Measuring ARIA's impact on your productivity.
      </p>

      {/* Controls row */}
      <div className="flex items-center justify-between">
        <div className="flex gap-2">
          {PERIOD_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setPeriod(opt.value)}
              className={cn(
                'px-3 py-1.5 rounded-full text-xs font-medium transition-colors duration-150',
                period === opt.value
                  ? 'bg-[var(--accent)] text-white'
                  : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)]',
              )}
              style={
                period === opt.value
                  ? undefined
                  : { backgroundColor: 'var(--bg-subtle)' }
              }
            >
              {opt.label}
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={handleExport}
          disabled={exportReport.isPending || !data}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors duration-150 disabled:opacity-50"
          style={{
            backgroundColor: 'var(--bg-subtle)',
            color: 'var(--text-secondary)',
          }}
        >
          {exportReport.isPending ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <Download className="w-3.5 h-3.5" />
          )}
          Export CSV
        </button>
      </div>

      {/* Content */}
      {isLoading && <AnalyticsSkeleton />}

      {error && (
        <p className="text-sm" style={{ color: 'var(--critical)' }}>
          Failed to load analytics data. Please try again.
        </p>
      )}

      {!isLoading && !error && !data && (
        <EmptyState
          title="No analytics data available yet."
          description="As ARIA works alongside you, productivity metrics and ROI data will appear here."
        />
      )}

      {!isLoading && !error && data && (
        <>
          {/* Metric cards */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <MetricCard
              icon={Clock}
              title="Time Saved"
              value={data.time_saved.hours.toFixed(1)}
              unit="hrs"
              subtitle={
                data.time_saved_per_week != null
                  ? `${data.time_saved_per_week.toFixed(1)} hrs/week`
                  : undefined
              }
            />
            <MetricCard
              icon={Brain}
              title="Intelligence"
              value={intelTotal}
              subtitle="facts, signals, gaps, briefings"
            />
            <MetricCard
              icon={Zap}
              title="Actions Taken"
              value={data.actions_taken.total}
              subtitle={
                approvalRate != null
                  ? `${(approvalRate * 100).toFixed(0)}% approval rate`
                  : undefined
              }
            />
            <MetricCard
              icon={TrendingUp}
              title="Pipeline Impact"
              value={data.pipeline_impact.leads_discovered}
              unit="leads"
              subtitle={`${data.pipeline_impact.meetings_prepped} meetings prepped`}
            />
          </div>

          {/* Trend chart */}
          {trendData && trendData.length > 0 && (
            <TrendChart data={trendData} />
          )}

          {/* Breakdowns */}
          {breakdowns && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <BreakdownSection title="Time Saved Breakdown" rows={breakdowns.timeSaved} />
              <BreakdownSection title="Intelligence Breakdown" rows={breakdowns.intelligence} />
              <BreakdownSection title="Actions Breakdown" rows={breakdowns.actions} />
              <BreakdownSection title="Pipeline Breakdown" rows={breakdowns.pipeline} />
            </div>
          )}
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
      style={{ backgroundColor: 'var(--bg-primary)' }}
      data-aria-id="analytics-page"
    >
      <div className="flex-1 overflow-y-auto p-8">
        <AnalyticsDashboard />
      </div>
    </div>
  );
}
