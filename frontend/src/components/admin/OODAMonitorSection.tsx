/** OODAMonitorSection - Real-time OODA cycle monitoring.
 *
 * KPI cards: active cycle count, avg phase duration.
 * Auto-refreshing table of active cycles (5s polling via hook).
 * BarChart: avg duration per phase.
 */

import { useMemo } from "react";
import { Activity, Clock, Layers } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useDashboardOverview, useActiveOODACycles } from "@/hooks/useAdminDashboard";

function KPI({ icon: Icon, label, value }: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string | number;
}) {
  return (
    <div
      className="border rounded-lg p-4"
      style={{ borderColor: "var(--border)", backgroundColor: "var(--bg-elevated)" }}
    >
      <div className="flex items-center gap-2 mb-2">
        <Icon className="w-3.5 h-3.5" style={{ color: "var(--accent)" }} />
        <span className="text-xs font-medium uppercase tracking-wider" style={{ color: "var(--text-secondary)" }}>
          {label}
        </span>
      </div>
      <span className="font-mono text-2xl font-bold" style={{ color: "var(--text-primary)" }}>
        {value}
      </span>
    </div>
  );
}

export function OODAMonitorSection() {
  const { data: overview } = useDashboardOverview();
  const { data: cycles, isLoading } = useActiveOODACycles();

  const phaseDurations = useMemo(() => {
    if (!cycles?.length) return [];
    const phaseTotals: Record<string, { total: number; count: number }> = {};
    for (const c of cycles) {
      const phase = c.current_phase || "unknown";
      if (!phaseTotals[phase]) phaseTotals[phase] = { total: 0, count: 0 };
      phaseTotals[phase].total += c.total_duration_ms;
      phaseTotals[phase].count += 1;
    }
    return ["observe", "orient", "decide", "act"].map((p) => ({
      phase: p,
      avg_ms: phaseTotals[p] ? Math.round(phaseTotals[p].total / phaseTotals[p].count) : 0,
    }));
  }, [cycles]);

  const avgDuration = useMemo(() => {
    if (!cycles?.length) return 0;
    return Math.round(cycles.reduce((s, c) => s + c.total_duration_ms, 0) / cycles.length);
  }, [cycles]);

  return (
    <div className="space-y-6">
      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
        <KPI icon={Activity} label="Active Cycles" value={overview?.active_ooda ?? 0} />
        <KPI icon={Clock} label="Avg Duration" value={`${avgDuration}ms`} />
        <KPI icon={Layers} label="Total Phases" value={cycles?.reduce((s, c) => s + c.phases_completed, 0) ?? 0} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Phase Duration Chart */}
        <div
          className="border rounded-lg p-4"
          style={{ borderColor: "var(--border)", backgroundColor: "var(--bg-elevated)" }}
        >
          <h3 className="text-xs font-medium uppercase tracking-wider mb-4" style={{ color: "var(--text-secondary)" }}>
            Avg Duration per Phase
          </h3>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={phaseDurations}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="phase" tick={{ fill: "var(--text-secondary)", fontSize: 11 }} />
                <YAxis tick={{ fill: "var(--text-secondary)", fontSize: 11 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "var(--bg-subtle)",
                    border: "1px solid var(--border)",
                    borderRadius: 6,
                    color: "var(--text-primary)",
                    fontSize: 12,
                  }}
                />
                <Bar dataKey="avg_ms" fill="var(--accent)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Active Cycles Table */}
        <div
          className="border rounded-lg p-4 overflow-auto"
          style={{ borderColor: "var(--border)", backgroundColor: "var(--bg-elevated)" }}
        >
          <h3 className="text-xs font-medium uppercase tracking-wider mb-4" style={{ color: "var(--text-secondary)" }}>
            Active Cycles
          </h3>
          {isLoading ? (
            <div className="animate-pulse space-y-2">
              {Array.from({ length: 5 }).map((_, i) => (
                <div key={i} className="h-6 rounded" style={{ backgroundColor: "var(--border)" }} />
              ))}
            </div>
          ) : !cycles?.length ? (
            <p className="text-sm" style={{ color: "var(--text-secondary)" }}>No active OODA cycles.</p>
          ) : (
            <table className="w-full text-xs">
              <thead>
                <tr style={{ color: "var(--text-secondary)" }}>
                  <th className="text-left pb-2 font-medium">Goal</th>
                  <th className="text-left pb-2 font-medium">Phase</th>
                  <th className="text-right pb-2 font-medium">Iter</th>
                  <th className="text-right pb-2 font-medium">Duration</th>
                  <th className="text-right pb-2 font-medium">Tokens</th>
                </tr>
              </thead>
              <tbody>
                {cycles.slice(0, 20).map((c) => (
                  <tr key={c.cycle_id} className="border-t" style={{ borderColor: "var(--border)" }}>
                    <td className="py-1.5 font-mono truncate max-w-[120px]" title={c.goal_id}>
                      {c.goal_id.slice(0, 8)}...
                    </td>
                    <td className="py-1.5">
                      <span
                        className="px-1.5 py-0.5 rounded text-[10px] font-medium uppercase"
                        style={{
                          backgroundColor: "var(--accent-muted)",
                          color: "var(--accent)",
                        }}
                      >
                        {c.current_phase}
                      </span>
                    </td>
                    <td className="py-1.5 text-right font-mono">{c.iteration}</td>
                    <td className="py-1.5 text-right font-mono">{c.total_duration_ms}ms</td>
                    <td className="py-1.5 text-right font-mono">{c.total_tokens.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}
