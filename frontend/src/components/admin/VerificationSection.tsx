/** VerificationSection - Agent output verification statistics.
 *
 * KPI cards: overall pass rate, total verified, worst agent.
 * Stacked BarChart: passed (green) + failed (red) by agent.
 * Table: by task type, sorted by pass rate ascending (worst first).
 */

import { Shield, CheckCircle, XCircle, AlertTriangle } from "lucide-react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { useVerificationStats } from "@/hooks/useAdminDashboard";

function KPI({ icon: Icon, label, value, color }: {
  icon: React.ComponentType<{ className?: string; style?: React.CSSProperties }>;
  label: string;
  value: string | number;
  color?: string;
}) {
  return (
    <div
      className="border rounded-lg p-4"
      style={{ borderColor: "var(--border)", backgroundColor: "var(--bg-elevated)" }}
    >
      <div className="flex items-center gap-2 mb-2">
        <Icon className="w-3.5 h-3.5" style={{ color: color || "var(--accent)" }} />
        <span className="text-xs font-medium uppercase tracking-wider" style={{ color: "var(--text-secondary)" }}>
          {label}
        </span>
      </div>
      <span className="font-mono text-2xl font-bold" style={{ color: color || "var(--text-primary)" }}>
        {value}
      </span>
    </div>
  );
}

export function VerificationSection() {
  const { data: stats, isLoading } = useVerificationStats();

  if (isLoading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-20 rounded-lg" style={{ backgroundColor: "var(--border)" }} />
          ))}
        </div>
        <div className="h-64 rounded-lg" style={{ backgroundColor: "var(--border)" }} />
      </div>
    );
  }

  if (!stats) return null;

  const passColor = stats.overall_pass_rate >= 80 ? "var(--success)" : stats.overall_pass_rate >= 50 ? "var(--warning)" : "var(--critical)";

  return (
    <div className="space-y-6">
      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KPI icon={Shield} label="Pass Rate" value={`${stats.overall_pass_rate}%`} color={passColor} />
        <KPI icon={CheckCircle} label="Passed" value={stats.total_passed} color="var(--success)" />
        <KPI icon={XCircle} label="Failed" value={stats.total_verified - stats.total_passed} color="var(--critical)" />
        <KPI
          icon={AlertTriangle}
          label="Worst Agent"
          value={stats.worst_agent || "N/A"}
          color="var(--warning)"
        />
      </div>

      {/* By-Agent Chart */}
      <div
        className="border rounded-lg p-4"
        style={{ borderColor: "var(--border)", backgroundColor: "var(--bg-elevated)" }}
      >
        <h3 className="text-xs font-medium uppercase tracking-wider mb-4" style={{ color: "var(--text-secondary)" }}>
          Verification by Agent
        </h3>
        {!stats.by_agent.length ? (
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>No verification data.</p>
        ) : (
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={stats.by_agent}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                <XAxis dataKey="agent" tick={{ fill: "var(--text-secondary)", fontSize: 10 }} />
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
                <Legend
                  wrapperStyle={{ fontSize: 11, color: "var(--text-secondary)" }}
                />
                <Bar dataKey="passed" stackId="a" fill="var(--success)" name="Passed" radius={[0, 0, 0, 0]} />
                <Bar dataKey="failed" stackId="a" fill="var(--critical)" name="Failed" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>

      {/* By-Task-Type Table */}
      <div
        className="border rounded-lg p-4"
        style={{ borderColor: "var(--border)", backgroundColor: "var(--bg-elevated)" }}
      >
        <h3 className="text-xs font-medium uppercase tracking-wider mb-4" style={{ color: "var(--text-secondary)" }}>
          By Task Type (worst first)
        </h3>
        <table className="w-full text-xs">
          <thead>
            <tr style={{ color: "var(--text-secondary)" }}>
              <th className="text-left pb-2 font-medium">Task Type</th>
              <th className="text-right pb-2 font-medium">Passed</th>
              <th className="text-right pb-2 font-medium">Failed</th>
              <th className="text-right pb-2 font-medium">Total</th>
              <th className="text-right pb-2 font-medium">Pass Rate</th>
            </tr>
          </thead>
          <tbody>
            {stats.by_task_type.map((row) => (
              <tr key={row.task_type} className="border-t" style={{ borderColor: "var(--border)" }}>
                <td className="py-1.5 font-mono font-medium">{row.task_type}</td>
                <td className="py-1.5 text-right font-mono" style={{ color: "var(--success)" }}>{row.passed}</td>
                <td className="py-1.5 text-right font-mono" style={{ color: "var(--critical)" }}>{row.failed}</td>
                <td className="py-1.5 text-right font-mono">{row.total}</td>
                <td className="py-1.5 text-right font-mono">
                  <span style={{
                    color: row.pass_rate >= 80 ? "var(--success)" : row.pass_rate >= 50 ? "var(--warning)" : "var(--critical)",
                  }}>
                    {row.pass_rate}%
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
