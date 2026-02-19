/** AgentWaterfallSection - Agent execution timeline visualization.
 *
 * Hours selector (1h / 6h / 24h).
 * Horizontal bar waterfall colored by status.
 * Summary table: agent, count, avg duration, avg cost, pass rate.
 */

import { useState, useMemo } from "react";
import { useAgentWaterfall } from "@/hooks/useAdminDashboard";
import { cn } from "@/utils/cn";

const HOUR_OPTIONS = [1, 6, 24] as const;

const STATUS_COLORS: Record<string, string> = {
  completed: "var(--success)",
  failed: "var(--critical)",
  retry: "var(--warning)",
  pending: "var(--text-secondary)",
};

export function AgentWaterfallSection() {
  const [hours, setHours] = useState<number>(24);
  const { data: executions, isLoading } = useAgentWaterfall(hours);

  const { timeline, summaryTable, timeRange } = useMemo(() => {
    if (!executions?.length) return { timeline: [], summaryTable: [], timeRange: { min: 0, max: 1 } };

    // Time range for positioning
    const timestamps = executions.map((e) => new Date(e.created_at).getTime());
    const min = Math.min(...timestamps);
    const max = Math.max(...timestamps);
    const range = max - min || 1;

    const timeline = executions.slice(0, 100).map((e) => {
      const ts = new Date(e.created_at).getTime();
      const left = ((ts - min) / range) * 100;
      return { ...e, left };
    });

    // Per-agent summary
    const agentMap: Record<string, {
      count: number;
      totalCost: number;
      passed: number;
      failed: number;
    }> = {};
    for (const e of executions) {
      const agent = e.delegatee || "unknown";
      if (!agentMap[agent]) agentMap[agent] = { count: 0, totalCost: 0, passed: 0, failed: 0 };
      agentMap[agent].count += 1;
      agentMap[agent].totalCost += e.cost_usd;
      if (e.verification_passed === true) agentMap[agent].passed += 1;
      if (e.verification_passed === false) agentMap[agent].failed += 1;
    }

    const summaryTable = Object.entries(agentMap)
      .map(([agent, s]) => ({
        agent,
        count: s.count,
        avgCost: s.count ? s.totalCost / s.count : 0,
        passRate: (s.passed + s.failed) > 0 ? (s.passed / (s.passed + s.failed)) * 100 : 0,
      }))
      .sort((a, b) => b.count - a.count);

    return { timeline, summaryTable, timeRange: { min, max } };
  }, [executions]);

  return (
    <div className="space-y-6">
      {/* Hours selector */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium uppercase tracking-wider" style={{ color: "var(--text-secondary)" }}>
          Time Window:
        </span>
        {HOUR_OPTIONS.map((h) => (
          <button
            key={h}
            onClick={() => setHours(h)}
            className={cn(
              "px-3 py-1 text-xs font-medium rounded border transition-colors cursor-pointer",
            )}
            style={{
              borderColor: hours === h ? "var(--accent)" : "var(--border)",
              backgroundColor: hours === h ? "var(--accent-muted)" : "transparent",
              color: hours === h ? "var(--accent)" : "var(--text-secondary)",
            }}
          >
            {h}h
          </button>
        ))}
      </div>

      {/* Waterfall */}
      <div
        className="border rounded-lg p-4"
        style={{ borderColor: "var(--border)", backgroundColor: "var(--bg-elevated)" }}
      >
        <h3 className="text-xs font-medium uppercase tracking-wider mb-4" style={{ color: "var(--text-secondary)" }}>
          Execution Timeline
        </h3>
        {isLoading ? (
          <div className="h-40 animate-pulse rounded" style={{ backgroundColor: "var(--border)" }} />
        ) : !timeline.length ? (
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>No agent executions in this window.</p>
        ) : (
          <div className="relative h-48 overflow-hidden">
            {/* Time axis */}
            <div className="absolute bottom-0 left-0 right-0 flex justify-between text-[10px] font-mono" style={{ color: "var(--text-secondary)" }}>
              <span>{new Date(timeRange.min).toLocaleTimeString()}</span>
              <span>{new Date(timeRange.max).toLocaleTimeString()}</span>
            </div>
            {/* Bars */}
            <div className="absolute inset-0 bottom-4">
              {timeline.map((e, i) => {
                const barColor = STATUS_COLORS[e.status] || "var(--text-secondary)";
                return (
                  <div
                    key={e.trace_id || i}
                    className="absolute h-3 rounded-sm opacity-80 hover:opacity-100 transition-opacity"
                    style={{
                      left: `${e.left}%`,
                      top: `${(i % 12) * 14}px`,
                      width: "clamp(4px, 2%, 24px)",
                      backgroundColor: barColor,
                    }}
                    title={`${e.delegatee} - ${e.status} - $${e.cost_usd.toFixed(4)}`}
                  />
                );
              })}
            </div>
          </div>
        )}
        {/* Legend */}
        <div className="flex gap-4 mt-3">
          {Object.entries(STATUS_COLORS).map(([status, color]) => (
            <div key={status} className="flex items-center gap-1.5 text-[10px]" style={{ color: "var(--text-secondary)" }}>
              <div className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: color }} />
              {status}
            </div>
          ))}
        </div>
      </div>

      {/* Summary Table */}
      <div
        className="border rounded-lg p-4"
        style={{ borderColor: "var(--border)", backgroundColor: "var(--bg-elevated)" }}
      >
        <h3 className="text-xs font-medium uppercase tracking-wider mb-4" style={{ color: "var(--text-secondary)" }}>
          Agent Summary
        </h3>
        <table className="w-full text-xs">
          <thead>
            <tr style={{ color: "var(--text-secondary)" }}>
              <th className="text-left pb-2 font-medium">Agent</th>
              <th className="text-right pb-2 font-medium">Executions</th>
              <th className="text-right pb-2 font-medium">Avg Cost</th>
              <th className="text-right pb-2 font-medium">Pass Rate</th>
            </tr>
          </thead>
          <tbody>
            {summaryTable.map((row) => (
              <tr key={row.agent} className="border-t" style={{ borderColor: "var(--border)" }}>
                <td className="py-1.5 font-mono font-medium">{row.agent}</td>
                <td className="py-1.5 text-right font-mono">{row.count}</td>
                <td className="py-1.5 text-right font-mono">${row.avgCost.toFixed(4)}</td>
                <td className="py-1.5 text-right font-mono">
                  <span style={{ color: row.passRate >= 80 ? "var(--success)" : row.passRate >= 50 ? "var(--warning)" : "var(--critical)" }}>
                    {row.passRate.toFixed(0)}%
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
