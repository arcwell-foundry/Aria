/** TrustEvolutionSection - Trust score evolution over time.
 *
 * User selector dropdown from trust summaries.
 * Multi-line AreaChart: one line per action_category, 0-1 scale.
 * Event dots: red for failures, orange for overrides.
 * Stuck users alert list.
 */

import { useState, useMemo } from "react";
import { AlertTriangle } from "lucide-react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  ZAxis,
} from "recharts";
import { useTrustSummaries, useTrustEvolution } from "@/hooks/useAdminDashboard";

const CATEGORY_COLORS: Record<string, string> = {
  lead_discovery: "#3B82F6",
  research: "#22C55E",
  strategy: "#F59E0B",
  email_draft: "#8B5CF6",
  crm_action: "#EF4444",
  market_monitoring: "#06B6D4",
  verification: "#F97316",
  browser_automation: "#EC4899",
  general: "#6B7280",
};

export function TrustEvolutionSection() {
  const { data: summaries } = useTrustSummaries();
  const [selectedUser, setSelectedUser] = useState<string | undefined>();
  const { data: evolution } = useTrustEvolution(selectedUser, 30);

  const stuckUsers = useMemo(() => {
    return (summaries ?? []).filter((u) => u.is_stuck);
  }, [summaries]);

  const chartData = useMemo(() => {
    if (!evolution?.length) return [];

    // Group by recorded_at, create one row per timestamp with each category as a column
    const byTime: Record<string, Record<string, number>> = {};
    for (const pt of evolution) {
      const ts = pt.recorded_at.slice(0, 16); // group by minute
      if (!byTime[ts]) byTime[ts] = {};
      byTime[ts][pt.action_category] = pt.trust_score;
    }

    return Object.entries(byTime)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([ts, cats]) => ({
        time: ts.slice(5, 16),
        ...cats,
      }));
  }, [evolution]);

  const categories = useMemo(() => {
    if (!evolution?.length) return [];
    return [...new Set(evolution.map((p) => p.action_category))];
  }, [evolution]);

  const eventDots = useMemo(() => {
    if (!evolution?.length) return [];
    return evolution
      .filter((p) => p.change_type === "failure" || p.change_type === "override")
      .map((p) => ({
        time: p.recorded_at.slice(5, 16),
        trust_score: p.trust_score,
        type: p.change_type,
      }));
  }, [evolution]);

  return (
    <div className="space-y-6">
      {/* User selector */}
      <div className="flex items-center gap-3">
        <span className="text-xs font-medium uppercase tracking-wider" style={{ color: "var(--text-secondary)" }}>
          User:
        </span>
        <select
          value={selectedUser ?? ""}
          onChange={(e) => setSelectedUser(e.target.value || undefined)}
          className="px-3 py-1.5 text-xs font-mono rounded border cursor-pointer"
          style={{
            borderColor: "var(--border)",
            backgroundColor: "var(--bg-subtle)",
            color: "var(--text-primary)",
          }}
        >
          <option value="">All Users</option>
          {(summaries ?? []).map((u) => (
            <option key={u.user_id} value={u.user_id}>
              {u.user_id.slice(0, 8)}... (avg: {u.avg_trust.toFixed(2)})
            </option>
          ))}
        </select>
      </div>

      {/* Trust Evolution Chart */}
      <div
        className="border rounded-lg p-4"
        style={{ borderColor: "var(--border)", backgroundColor: "var(--bg-elevated)" }}
      >
        <h3 className="text-xs font-medium uppercase tracking-wider mb-4" style={{ color: "var(--text-secondary)" }}>
          Trust Score Over Time
        </h3>
        {!chartData.length ? (
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>No trust evolution data available.</p>
        ) : (
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="time" tick={{ fill: "var(--text-secondary)", fontSize: 10 }} />
                <YAxis domain={[0, 1]} tick={{ fill: "var(--text-secondary)", fontSize: 10 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "var(--bg-subtle)",
                    border: "1px solid var(--border)",
                    borderRadius: 6,
                    color: "var(--text-primary)",
                    fontSize: 12,
                  }}
                />
                {categories.map((cat) => (
                  <Area
                    key={cat}
                    type="monotone"
                    dataKey={cat}
                    stroke={CATEGORY_COLORS[cat] || "#6B7280"}
                    fill={CATEGORY_COLORS[cat] || "#6B7280"}
                    fillOpacity={0.1}
                    strokeWidth={1.5}
                    name={cat}
                  />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
        {/* Category legend */}
        <div className="flex flex-wrap gap-3 mt-3">
          {categories.map((cat) => (
            <div key={cat} className="flex items-center gap-1.5 text-[10px]" style={{ color: "var(--text-secondary)" }}>
              <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: CATEGORY_COLORS[cat] || "#6B7280" }} />
              {cat}
            </div>
          ))}
        </div>
      </div>

      {/* Event Dots Summary */}
      {eventDots.length > 0 && (
        <div
          className="border rounded-lg p-4"
          style={{ borderColor: "var(--border)", backgroundColor: "var(--bg-elevated)" }}
        >
          <h3 className="text-xs font-medium uppercase tracking-wider mb-3" style={{ color: "var(--text-secondary)" }}>
            Trust Change Events
          </h3>
          <div className="flex flex-wrap gap-2">
            {eventDots.slice(0, 20).map((d, i) => (
              <span
                key={i}
                className="px-2 py-1 rounded text-[10px] font-mono"
                style={{
                  backgroundColor: d.type === "failure" ? "rgba(164, 107, 107, 0.2)" : "rgba(184, 149, 106, 0.2)",
                  color: d.type === "failure" ? "var(--critical)" : "var(--warning)",
                }}
              >
                {d.type} @ {d.trust_score.toFixed(2)}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Stuck Users */}
      {stuckUsers.length > 0 && (
        <div
          className="border rounded-lg p-4"
          style={{ borderColor: "var(--warning)", backgroundColor: "var(--bg-elevated)" }}
        >
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle className="w-4 h-4" style={{ color: "var(--warning)" }} />
            <h3 className="text-xs font-medium uppercase tracking-wider" style={{ color: "var(--warning)" }}>
              Stuck Users (low trust despite activity)
            </h3>
          </div>
          <div className="space-y-2">
            {stuckUsers.map((u) => (
              <div
                key={u.user_id}
                className="flex items-center justify-between text-xs border rounded px-3 py-2"
                style={{ borderColor: "var(--border)" }}
              >
                <span className="font-mono" style={{ color: "var(--text-primary)" }}>
                  {u.user_id.slice(0, 8)}...
                </span>
                <span style={{ color: "var(--critical)" }}>
                  avg trust: {u.avg_trust.toFixed(3)} / {u.total_actions} actions
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
