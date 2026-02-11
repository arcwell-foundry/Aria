/** ROI Dashboard page - US-943. */

import { useState } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { HelpTooltip } from "@/components/HelpTooltip";
import { useROIMetrics, useROITrend, useExportROIReport } from "@/hooks/useROI";
import type { TimeSavedBreakdown } from "@/types/roi";
import {
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
  PieChart,
  Pie,
  LineChart,
  Line,
} from "recharts";

type Period = "7d" | "30d" | "90d" | "all";

const PERIODS: { value: Period; label: string }[] = [
  { value: "7d", label: "7 days" },
  { value: "30d", label: "30 days" },
  { value: "90d", label: "90 days" },
  { value: "all", label: "All time" },
];

// Colors for charts (desaturated, per design system)
const CHART_COLORS = {
  emailDrafts: "#5B6E8A",
  meetingPrep: "#6B7FA3",
  researchReports: "#8B92A5",
  crmUpdates: "#7B8EAA",
  trend: "#5B6E8A",
};

// Data for pie chart from time saved breakdown
function getTimeSavedData(breakdown: TimeSavedBreakdown) {
  return [
    { name: "Email drafts", hours: breakdown.email_drafts.estimated_hours, color: CHART_COLORS.emailDrafts },
    { name: "Meeting prep", hours: breakdown.meeting_prep.estimated_hours, color: CHART_COLORS.meetingPrep },
    { name: "Research reports", hours: breakdown.research_reports.estimated_hours, color: CHART_COLORS.researchReports },
    { name: "CRM updates", hours: breakdown.crm_updates.estimated_hours, color: CHART_COLORS.crmUpdates },
  ].filter((item) => item.hours > 0);
}

export function ROIDashboardPage() {
  const [selectedPeriod, setSelectedPeriod] = useState<Period>("30d");

  const { data: roiData, isLoading, error } = useROIMetrics(selectedPeriod);
  const { data: trendData } = useROITrend(selectedPeriod);
  const exportReport = useExportROIReport();

  return (
    <DashboardLayout>
      <div className="p-4 lg:p-8 min-h-screen bg-primary">
        <div className="max-w-6xl mx-auto">
          {/* Header */}
          <div className="flex items-center justify-between mb-8">
            <div className="flex items-center gap-2">
              <h1 className="font-display text-3xl text-content">Your ARIA ROI</h1>
              <HelpTooltip
                content="Track the measurable value ARIA delivers: time saved, intelligence discovered, and impact on your pipeline."
                placement="right"
              />
            </div>

            {/* Period Selector */}
            <div className="flex bg-elevated rounded-lg p-1 border border-border">
              {PERIODS.map((period) => (
                <button
                  key={period.value}
                  onClick={() => setSelectedPeriod(period.value)}
                  className={`px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                    selectedPeriod === period.value
                      ? "bg-interactive text-white"
                      : "text-secondary hover:text-content"
                  }`}
                >
                  {period.label}
                </button>
              ))}
            </div>
          </div>

          {/* Loading State */}
          {isLoading && (
            <div className="text-center py-12">
              <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-interactive"></div>
              <p className="mt-4 text-secondary">Calculating your ROI...</p>
            </div>
          )}

          {/* Error State */}
          {error && (
            <div className="bg-critical/10 border border-critical/30 rounded-lg p-6 text-center">
              <p className="text-critical">Unable to load ROI metrics. Please try again later.</p>
            </div>
          )}

          {/* ROI Dashboard Content */}
          {roiData && (
            <div className="space-y-6">
              {/* Hero Metric - Time Saved */}
              <div className="bg-elevated border border-border rounded-xl p-8">
                <p className="text-secondary text-sm uppercase tracking-wide mb-2">Total Time Saved</p>
                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-6xl text-interactive">
                    {roiData.time_saved.hours}
                  </span>
                  <span className="text-secondary text-xl">hours</span>
                </div>
                <p className="text-secondary mt-2">
                  in the {selectedPeriod === "all" ? "lifetime" : `last ${PERIODS.find((p) => p.value === selectedPeriod)?.label.toLowerCase()}`}
                </p>
              </div>

              {/* Metrics Grid - 2x2 */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Time Saved Breakdown */}
                <div className="bg-elevated border border-border rounded-xl p-6">
                  <h3 className="font-display text-lg text-content mb-4">Time Saved by Activity</h3>
                  {roiData.time_saved.hours > 0 ? (
                    <ResponsiveContainer width="100%" height={200}>
                      <PieChart>
                        <Pie
                          data={getTimeSavedData(roiData.time_saved.breakdown)}
                          cx="50%"
                          cy="50%"
                          labelLine={false}
                          label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                          outerRadius={70}
                          dataKey="hours"
                        >
                          {getTimeSavedData(roiData.time_saved.breakdown).map((entry, index) => (
                            <Cell key={`cell-${index}`} fill={entry.color} />
                          ))}
                        </Pie>
                        <Tooltip
                          contentStyle={{
                            backgroundColor: "#161B2E",
                            border: "1px solid #2A2F42",
                            borderRadius: "8px",
                            color: "#E8E6E1",
                          }}
                          formatter={(value: number) => [`${value.toFixed(1)}h`, "Time saved"]}
                        />
                      </PieChart>
                    </ResponsiveContainer>
                  ) : (
                    <p className="text-secondary text-center py-8">No data yet for this period</p>
                  )}
                </div>

                {/* Intelligence Delivered */}
                <div className="bg-elevated border border-border rounded-xl p-6">
                  <h3 className="font-display text-lg text-content mb-4">Intelligence Delivered</h3>
                  <div className="space-y-4">
                    <div className="flex justify-between items-center">
                      <span className="text-secondary">Facts discovered</span>
                      <span className="font-mono text-content text-xl">
                        {roiData.intelligence_delivered.facts_discovered}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-secondary">Signals detected</span>
                      <span className="font-mono text-content text-xl">
                        {roiData.intelligence_delivered.signals_detected}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-secondary">Knowledge gaps filled</span>
                      <span className="font-mono text-content text-xl">
                        {roiData.intelligence_delivered.gaps_filled}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-secondary">Briefings generated</span>
                      <span className="font-mono text-content text-xl">
                        {roiData.intelligence_delivered.briefings_generated}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Actions Taken */}
                <div className="bg-elevated border border-border rounded-xl p-6">
                  <h3 className="font-display text-lg text-content mb-4">Actions Taken</h3>
                  <div className="space-y-4">
                    <div className="flex justify-between items-center">
                      <span className="text-secondary">Total actions</span>
                      <span className="font-mono text-content text-xl">{roiData.actions_taken.total}</span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-secondary">Auto-approved</span>
                      <span className="font-mono text-success text-xl">
                        {roiData.actions_taken.auto_approved}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-secondary">You approved</span>
                      <span className="font-mono text-interactive text-xl">
                        {roiData.actions_taken.user_approved}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-secondary">Rejected</span>
                      <span className="font-mono text-critical text-xl">{roiData.actions_taken.rejected}</span>
                    </div>
                  </div>
                </div>

                {/* Pipeline Impact */}
                <div className="bg-elevated border border-border rounded-xl p-6">
                  <h3 className="font-display text-lg text-content mb-4">Pipeline Impact</h3>
                  <div className="space-y-4">
                    <div className="flex justify-between items-center">
                      <span className="text-secondary">Leads discovered</span>
                      <span className="font-mono text-content text-xl">
                        {roiData.pipeline_impact.leads_discovered}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-secondary">Meetings prepared</span>
                      <span className="font-mono text-content text-xl">
                        {roiData.pipeline_impact.meetings_prepped}
                      </span>
                    </div>
                    <div className="flex justify-between items-center">
                      <span className="text-secondary">Follow-ups sent</span>
                      <span className="font-mono text-content text-xl">
                        {roiData.pipeline_impact.follow_ups_sent}
                      </span>
                    </div>
                  </div>
                </div>
              </div>

              {/* Weekly Trend Line Chart */}
              {trendData && trendData.length > 0 && (
                <div className="bg-elevated border border-border rounded-xl p-6">
                  <h3 className="font-display text-lg text-content mb-4">Weekly Time Saved Trend</h3>
                  <ResponsiveContainer width="100%" height={250}>
                    <LineChart data={trendData}>
                      <XAxis
                        dataKey="week_start"
                        tickFormatter={(value) => {
                          const date = new Date(value);
                          return `${date.getMonth() + 1}/${date.getDate()}`;
                        }}
                        stroke="#8B92A5"
                        tick={{ fill: "#8B92A5", fontSize: 11 }}
                      />
                      <YAxis
                        stroke="#8B92A5"
                        tick={{ fill: "#8B92A5", fontSize: 11 }}
                        label={{ value: "Hours saved", angle: -90, position: "insideLeft", fill: "#8B92A5" }}
                      />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: "#161B2E",
                          border: "1px solid #2A2F42",
                          borderRadius: "8px",
                          color: "#E8E6E1",
                        }}
                        labelFormatter={(value) => `Week of ${new Date(value).toLocaleDateString()}`}
                        formatter={(value: number) => [`${value}h`, "Time saved"]}
                      />
                      <Line
                        type="monotone"
                        dataKey="hours_saved"
                        stroke={CHART_COLORS.trend}
                        strokeWidth={2}
                        dot={{ fill: CHART_COLORS.trend, strokeWidth: 2, r: 4 }}
                        activeDot={{ r: 6 }}
                      />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              )}

              {/* Export Button */}
              <div className="flex justify-end">
                <button
                  onClick={() => exportReport.mutate(selectedPeriod)}
                  disabled={exportReport.isPending}
                  className="px-6 py-2.5 bg-interactive text-white rounded-lg font-medium hover:bg-interactive-hover transition-colors duration-150 disabled:opacity-60 disabled:cursor-not-allowed"
                >
                  {exportReport.isPending ? "Exporting..." : "Download Report"}
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
