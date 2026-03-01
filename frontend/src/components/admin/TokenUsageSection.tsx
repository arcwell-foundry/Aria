/** TokenUsageSection - Team token usage and cost tracking.
 *
 * Period selector (7d / 30d / 90d).
 * KPI cards: total cost, total tokens, avg cost/user, alert count.
 * Stacked AreaChart: standard tokens + thinking tokens.
 * Per-user table with red alert badges for >$30/day.
 */

import { useState, useMemo } from "react";
import { DollarSign, Zap, AlertTriangle, Users } from "lucide-react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { useTeamUsage } from "@/hooks/useAdminDashboard";
import { cn } from "@/utils/cn";

const PERIOD_OPTIONS = [7, 30, 90] as const;

function KPI({ icon: Icon, label, value, alert }: {
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties }>;
  label: string;
  value: string | number;
  alert?: boolean;
}) {
  return (
    <div
      className="border rounded-lg p-4"
      style={{
        borderColor: alert ? "var(--critical)" : "var(--border)",
        backgroundColor: "var(--bg-elevated)",
      }}
    >
      <div className="flex items-center gap-2 mb-2">
        <Icon className="w-3.5 h-3.5" style={{ color: alert ? "var(--critical)" : "var(--accent)" }} />
        <span className="text-xs font-medium uppercase tracking-wider" style={{ color: "var(--text-secondary)" }}>
          {label}
        </span>
      </div>
      <span
        className="font-mono text-2xl font-bold"
        style={{ color: alert ? "var(--critical)" : "var(--text-primary)" }}
      >
        {value}
      </span>
    </div>
  );
}

export function TokenUsageSection() {
  const [days, setDays] = useState<number>(30);
  const { data: usage, isLoading } = useTeamUsage(days);

  const chartData = useMemo(() => {
    if (!usage?.daily_totals?.length) return [];
    return [...usage.daily_totals]
      .sort((a, b) => a.date.localeCompare(b.date))
      .map((d) => ({
        date: d.date.slice(5),
        tokens: d.tokens,
        thinking: d.thinking_tokens,
        cost: d.cost,
      }));
  }, [usage]);

  const totals = useMemo(() => {
    if (!usage) return { cost: 0, tokens: 0, avgCostPerUser: 0, alertCount: 0 };
    const totalCost = usage.users.reduce((s, u) => s + u.total_cost, 0);
    const totalTokens = usage.users.reduce((s, u) => s + u.total_tokens, 0);
    const avgCost = usage.users.length ? totalCost / usage.users.length : 0;
    return {
      cost: totalCost,
      tokens: totalTokens,
      avgCostPerUser: avgCost,
      alertCount: usage.alerts.length,
    };
  }, [usage]);

  return (
    <div className="space-y-6">
      {/* Period selector */}
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium uppercase tracking-wider" style={{ color: "var(--text-secondary)" }}>
          Period:
        </span>
        {PERIOD_OPTIONS.map((d) => (
          <button
            key={d}
            onClick={() => setDays(d)}
            className={cn("px-3 py-1 text-xs font-medium rounded border transition-colors cursor-pointer")}
            style={{
              borderColor: days === d ? "var(--accent)" : "var(--border)",
              backgroundColor: days === d ? "var(--accent-muted)" : "transparent",
              color: days === d ? "var(--accent)" : "var(--text-secondary)",
            }}
          >
            {d}d
          </button>
        ))}
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPI icon={DollarSign} label="Total Cost" value={`$${totals.cost.toFixed(2)}`} />
        <KPI icon={Zap} label="Total Tokens" value={totals.tokens.toLocaleString()} />
        <KPI icon={Users} label="Avg Cost/User" value={`$${totals.avgCostPerUser.toFixed(2)}`} />
        <KPI icon={AlertTriangle} label="Alerts" value={totals.alertCount} alert={totals.alertCount > 0} />
      </div>

      {/* Chart */}
      <div
        className="border rounded-lg p-4"
        style={{ borderColor: "var(--border)", backgroundColor: "var(--bg-elevated)" }}
      >
        <h3 className="text-xs font-medium uppercase tracking-wider mb-4" style={{ color: "var(--text-secondary)" }}>
          Token Usage Over Time
        </h3>
        {isLoading ? (
          <div className="h-64 animate-pulse rounded" style={{ backgroundColor: "var(--border)" }} />
        ) : (
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="date" tick={{ fill: "var(--text-secondary)", fontSize: 10 }} />
                <YAxis tick={{ fill: "var(--text-secondary)", fontSize: 10 }} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: "var(--bg-subtle)",
                    border: "1px solid var(--border)",
                    borderRadius: 6,
                    color: "var(--text-primary)",
                    fontSize: 12,
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="tokens"
                  stackId="1"
                  stroke="var(--accent)"
                  fill="var(--accent-muted)"
                  name="Standard Tokens"
                />
                <Area
                  type="monotone"
                  dataKey="thinking"
                  stackId="1"
                  stroke="#8B5CF6"
                  fill="rgba(139, 92, 246, 0.15)"
                  name="Thinking Tokens"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* Per-User Table */}
      <div
        className="border rounded-lg p-4"
        style={{ borderColor: "var(--border)", backgroundColor: "var(--bg-elevated)" }}
      >
        <h3 className="text-xs font-medium uppercase tracking-wider mb-4" style={{ color: "var(--text-secondary)" }}>
          Per-User Usage
        </h3>
        <table className="w-full text-xs">
          <thead>
            <tr style={{ color: "var(--text-secondary)" }}>
              <th className="text-left pb-2 font-medium">User</th>
              <th className="text-right pb-2 font-medium">Cost</th>
              <th className="text-right pb-2 font-medium">Tokens</th>
              <th className="text-right pb-2 font-medium">Thinking</th>
              <th className="text-right pb-2 font-medium">Calls</th>
              <th className="text-right pb-2 font-medium">Days</th>
            </tr>
          </thead>
          <tbody>
            {(usage?.users ?? []).map((u) => {
              const hasAlert = usage?.alerts.some((a) => a.user_id === u.user_id);
              return (
                <tr key={u.user_id} className="border-t" style={{ borderColor: "var(--border)" }}>
                  <td className="py-1.5 font-mono truncate max-w-[120px]" title={u.user_id}>
                    {u.user_id.slice(0, 8)}...
                    {hasAlert && (
                      <span
                        className="ml-2 px-1.5 py-0.5 rounded text-[10px] font-bold uppercase"
                        style={{ backgroundColor: "rgba(164, 107, 107, 0.2)", color: "var(--critical)" }}
                      >
                        Alert
                      </span>
                    )}
                  </td>
                  <td className="py-1.5 text-right font-mono">${u.total_cost.toFixed(2)}</td>
                  <td className="py-1.5 text-right font-mono">{u.total_tokens.toLocaleString()}</td>
                  <td className="py-1.5 text-right font-mono">{u.total_thinking_tokens.toLocaleString()}</td>
                  <td className="py-1.5 text-right font-mono">{u.total_calls}</td>
                  <td className="py-1.5 text-right font-mono">{u.days_active}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
