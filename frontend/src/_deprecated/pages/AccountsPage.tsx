/** Accounts page - Territory planning & account strategy (US-941). */

import { useState, useMemo } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import {
  useTerritory,
  useAccountPlan,
  useUpdateAccountPlan,
  useForecast,
  useQuotas,
  useSetQuota,
} from "@/hooks/useAccounts";
import type { AccountListItem, ForecastStage } from "@/api/accounts";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

// ---------------------------------------------------------------------------
// Utility helpers
// ---------------------------------------------------------------------------

function relativeTime(dateStr: string | null): string {
  if (!dateStr) return "\u2014";
  const diff = Date.now() - new Date(dateStr).getTime();
  const days = Math.floor(diff / 86400000);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 30) return `${days}d ago`;
  return `${Math.floor(days / 30)}mo ago`;
}

function formatCurrency(value: number | null | undefined): string {
  if (value == null) return "\u2014";
  return "$" + value.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// ---------------------------------------------------------------------------
// Inline SVG icons (no external icon library)
// ---------------------------------------------------------------------------

function BuildingIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="4" y="2" width="16" height="20" rx="2" ry="2" />
      <path d="M9 22v-4h6v4" />
      <path d="M8 6h.01M16 6h.01M12 6h.01M8 10h.01M16 10h.01M12 10h.01M8 14h.01M16 14h.01M12 14h.01" />
    </svg>
  );
}

function DollarSignIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="1" x2="12" y2="23" />
      <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
    </svg>
  );
}

function HeartIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 0 0 0-7.78z" />
    </svg>
  );
}

function TrendingUpIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 6 13.5 15.5 8.5 10.5 1 18" />
      <polyline points="17 6 23 6 23 12" />
    </svg>
  );
}

function CloseIcon({ className = "w-5 h-5" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

function ChevronDownIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  );
}

function ChevronUpIcon({ className = "w-4 h-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="18 15 12 9 6 15" />
    </svg>
  );
}

// ---------------------------------------------------------------------------
// Stage filter types
// ---------------------------------------------------------------------------

type StageFilter = "all" | "lead" | "opportunity" | "account";

const STAGE_FILTERS: { value: StageFilter; label: string }[] = [
  { value: "all", label: "All" },
  { value: "lead", label: "Lead" },
  { value: "opportunity", label: "Opportunity" },
  { value: "account", label: "Account" },
];

// ---------------------------------------------------------------------------
// Sort helpers
// ---------------------------------------------------------------------------

type SortKey = "company_name" | "lifecycle_stage" | "health_score" | "expected_value" | "last_activity_at" | "next_action";
type SortDir = "asc" | "desc";

function sortAccounts(accounts: AccountListItem[], key: SortKey, dir: SortDir): AccountListItem[] {
  return [...accounts].sort((a, b) => {
    const aVal = a[key];
    const bVal = b[key];
    if (aVal == null && bVal == null) return 0;
    if (aVal == null) return 1;
    if (bVal == null) return -1;
    const cmp = typeof aVal === "string" ? aVal.localeCompare(bVal as string) : (aVal as number) - (bVal as number);
    return dir === "asc" ? cmp : -cmp;
  });
}

// ---------------------------------------------------------------------------
// Health color helpers
// ---------------------------------------------------------------------------

function healthColor(score: number): string {
  if (score >= 70) return "text-success";
  if (score >= 40) return "text-yellow-400";
  return "text-critical";
}

function healthBarColor(score: number): string {
  if (score >= 70) return "bg-success";
  if (score >= 40) return "bg-yellow-500";
  return "bg-critical";
}

function stageBadgeColor(stage: string): string {
  switch (stage.toLowerCase()) {
    case "lead":
      return "bg-info/20 text-info border-info/30";
    case "opportunity":
      return "bg-warning/20 text-warning border-warning/30";
    case "account":
      return "bg-success/20 text-success border-success/30";
    default:
      return "bg-slate-500/20 text-slate-400 border-slate-500/30";
  }
}

function priorityBadgeColor(priority: "high" | "medium" | "low"): string {
  switch (priority) {
    case "high":
      return "bg-critical/20 text-critical border-critical/30";
    case "medium":
      return "bg-yellow-500/20 text-yellow-400 border-yellow-500/30";
    case "low":
      return "bg-success/20 text-success border-success/30";
  }
}

function quotaBarColor(pct: number): string {
  if (pct >= 75) return "bg-success";
  if (pct >= 50) return "bg-yellow-500";
  return "bg-critical";
}

// ---------------------------------------------------------------------------
// Detail panel tabs
// ---------------------------------------------------------------------------

type DetailTab = "plan" | "stakeholders" | "actions";

// ---------------------------------------------------------------------------
// AccountDetailPanel
// ---------------------------------------------------------------------------

function AccountDetailPanel({
  account,
  onClose,
}: {
  account: AccountListItem;
  onClose: () => void;
}) {
  const [activeTab, setActiveTab] = useState<DetailTab>("plan");
  const { data: plan, isLoading: planLoading } = useAccountPlan(account.id);
  const updatePlan = useUpdateAccountPlan();
  const [strategy, setStrategy] = useState<string | null>(null);

  // Sync strategy text when plan loads
  const displayStrategy = strategy ?? plan?.strategy ?? "";

  const tabs: { value: DetailTab; label: string }[] = [
    { value: "plan", label: "Plan" },
    { value: "stakeholders", label: "Stakeholders" },
    { value: "actions", label: "Actions" },
  ];

  function handleSave() {
    if (displayStrategy.trim()) {
      updatePlan.mutate({ leadId: account.id, strategy: displayStrategy });
    }
  }

  return (
    <div className="fixed inset-y-0 right-0 w-full max-w-[480px] bg-slate-900 border-l border-slate-700 shadow-2xl z-50 flex flex-col">
      {/* Header */}
      <div className="flex items-center justify-between p-6 border-b border-slate-700">
        <div>
          <h2 className="text-xl font-semibold text-white">{account.company_name}</h2>
          <span className={`inline-block mt-1 text-xs px-2 py-0.5 rounded border ${stageBadgeColor(account.lifecycle_stage)}`}>
            {capitalize(account.lifecycle_stage)}
          </span>
        </div>
        <button
          onClick={onClose}
          className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          aria-label="Close panel"
        >
          <CloseIcon />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex border-b border-slate-700">
        {tabs.map((tab) => (
          <button
            key={tab.value}
            onClick={() => setActiveTab(tab.value)}
            className={`flex-1 py-3 text-sm font-medium text-center transition-colors ${
              activeTab === tab.value
                ? "text-interactive border-b-2 border-interactive"
                : "text-slate-400 hover:text-white"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {/* Plan Tab */}
        {activeTab === "plan" && (
          <div className="space-y-4">
            {planLoading ? (
              <div className="space-y-3">
                <div className="h-4 bg-slate-700 rounded animate-pulse w-2/3" />
                <div className="h-32 bg-slate-700 rounded animate-pulse" />
                <p className="text-sm text-slate-500">Generating plan...</p>
              </div>
            ) : (
              <>
                <label className="block text-sm font-medium text-slate-300">
                  Account Strategy
                </label>
                <textarea
                  value={displayStrategy}
                  onChange={(e) => setStrategy(e.target.value)}
                  rows={8}
                  className="w-full bg-slate-800 border border-slate-600 rounded-lg p-3 text-white text-sm resize-y focus:outline-none focus:ring-2 focus:ring-interactive focus:border-transparent"
                  placeholder="Describe your account strategy..."
                />
                <button
                  onClick={handleSave}
                  disabled={updatePlan.isPending}
                  className="px-4 py-2 bg-interactive text-white text-sm rounded-lg font-medium hover:bg-interactive-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {updatePlan.isPending ? "Saving..." : "Save Strategy"}
                </button>
                {updatePlan.isSuccess && (
                  <p className="text-sm text-success">Strategy saved.</p>
                )}
              </>
            )}
          </div>
        )}

        {/* Stakeholders Tab */}
        {activeTab === "stakeholders" && (
          <div className="space-y-4">
            {planLoading ? (
              <div className="space-y-3">
                <div className="h-4 bg-slate-700 rounded animate-pulse w-1/2" />
                <div className="h-4 bg-slate-700 rounded animate-pulse w-2/3" />
                <div className="h-4 bg-slate-700 rounded animate-pulse w-1/3" />
              </div>
            ) : plan?.stakeholder_summary ? (
              <div className="space-y-4">
                <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4">
                  <p className="text-xs text-slate-500 uppercase tracking-wide mb-1">Champion</p>
                  <p className="text-white text-sm">{plan.stakeholder_summary.champion || "Not identified"}</p>
                </div>
                <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4">
                  <p className="text-xs text-slate-500 uppercase tracking-wide mb-1">Decision Maker</p>
                  <p className="text-white text-sm">{plan.stakeholder_summary.decision_maker || "Not identified"}</p>
                </div>
                <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4">
                  <p className="text-xs text-slate-500 uppercase tracking-wide mb-1">Key Risk</p>
                  <p className="text-white text-sm">{plan.stakeholder_summary.key_risk || "None identified"}</p>
                </div>
              </div>
            ) : (
              <p className="text-slate-500 text-sm">No stakeholder data available. Generate an account plan first.</p>
            )}
          </div>
        )}

        {/* Actions Tab */}
        {activeTab === "actions" && (
          <div className="space-y-3">
            {planLoading ? (
              <div className="space-y-3">
                <div className="h-12 bg-slate-700 rounded animate-pulse" />
                <div className="h-12 bg-slate-700 rounded animate-pulse" />
              </div>
            ) : plan?.next_actions && plan.next_actions.length > 0 ? (
              plan.next_actions.map((item, idx) => (
                <div
                  key={idx}
                  className="bg-slate-800/50 border border-slate-700 rounded-lg p-4 flex items-start gap-3"
                >
                  <span className={`inline-block text-xs px-2 py-0.5 rounded border font-medium ${priorityBadgeColor(item.priority)}`}>
                    {capitalize(item.priority)}
                  </span>
                  <div className="flex-1">
                    <p className="text-white text-sm">{item.action}</p>
                    {item.due_in_days != null && (
                      <p className="text-xs text-slate-500 mt-1">
                        Due in {item.due_in_days} day{item.due_in_days !== 1 ? "s" : ""}
                      </p>
                    )}
                  </div>
                </div>
              ))
            ) : (
              <p className="text-slate-500 text-sm">No actions defined yet. Generate an account plan to see recommended actions.</p>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Main page
// ---------------------------------------------------------------------------

export function AccountsPage() {
  const [stageFilter, setStageFilter] = useState<StageFilter>("all");
  const [sortKey, setSortKey] = useState<SortKey>("company_name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [selectedAccount, setSelectedAccount] = useState<AccountListItem | null>(null);

  // Quota form state
  const [quotaPeriod, setQuotaPeriod] = useState("");
  const [quotaTarget, setQuotaTarget] = useState("");

  // Data hooks
  const apiStage = stageFilter === "all" ? undefined : stageFilter;
  const { data: territory, isLoading: territoryLoading } = useTerritory(apiStage);
  const { data: forecast, isLoading: forecastLoading } = useForecast();
  const { data: quotas, isLoading: quotasLoading } = useQuotas();
  const setQuota = useSetQuota();

  // Sorted accounts
  const territoryAccounts = territory?.accounts;
  const accounts = useMemo(() => {
    if (!territoryAccounts) return [];
    return sortAccounts(territoryAccounts, sortKey, sortDir);
  }, [territoryAccounts, sortKey, sortDir]);

  // Chart data
  const forecastStages = forecast?.stages;
  const chartData = useMemo(() => {
    if (!forecastStages) return [];
    return forecastStages.map((s: ForecastStage) => ({
      stage: capitalize(s.stage),
      totalValue: s.total_value,
      weightedValue: s.weighted_value,
    }));
  }, [forecastStages]);

  // Column header click handler
  function handleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  function SortIndicator({ col }: { col: SortKey }) {
    if (sortKey !== col) return <ChevronDownIcon className="w-3 h-3 opacity-30" />;
    return sortDir === "asc" ? <ChevronUpIcon className="w-3 h-3" /> : <ChevronDownIcon className="w-3 h-3" />;
  }

  function handleQuotaSubmit(e: React.FormEvent) {
    e.preventDefault();
    const target = parseFloat(quotaTarget);
    if (quotaPeriod.trim() && !isNaN(target) && target > 0) {
      setQuota.mutate(
        { period: quotaPeriod.trim(), targetValue: target },
        {
          onSuccess: () => {
            setQuotaPeriod("");
            setQuotaTarget("");
          },
        },
      );
    }
  }

  return (
    <DashboardLayout>
      <div className="p-4 lg:p-8 min-h-screen bg-slate-900">
        <div className="max-w-7xl mx-auto space-y-8">
          {/* ---- Header ---- */}
          <div>
            <h1 className="text-3xl font-display text-white">Accounts</h1>
            <p className="mt-1 text-slate-400">Territory planning &amp; account strategy</p>
          </div>

          {/* ---- Stat Cards ---- */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {/* Total Accounts */}
            <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4 flex items-center gap-3">
              <div className="text-slate-400">
                <BuildingIcon />
              </div>
              <div>
                <p className="text-2xl font-semibold text-white">
                  {territoryLoading ? "\u2014" : (territory?.stats.total_accounts ?? 0)}
                </p>
                <p className="text-sm text-slate-400">Total Accounts</p>
              </div>
            </div>

            {/* Total Pipeline */}
            <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4 flex items-center gap-3">
              <div className="text-slate-400">
                <DollarSignIcon />
              </div>
              <div>
                <p className="text-2xl font-semibold text-white">
                  {territoryLoading ? "\u2014" : formatCurrency(territory?.stats.total_value)}
                </p>
                <p className="text-sm text-slate-400">Total Pipeline</p>
              </div>
            </div>

            {/* Avg Health */}
            <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4 flex items-center gap-3">
              <div className={territory ? healthColor(territory.stats.avg_health) : "text-slate-400"}>
                <HeartIcon />
              </div>
              <div>
                <p className={`text-2xl font-semibold ${territory ? healthColor(territory.stats.avg_health) : "text-white"}`}>
                  {territoryLoading ? "\u2014" : (territory?.stats.avg_health ?? 0)}
                </p>
                <p className="text-sm text-slate-400">Avg Health</p>
              </div>
            </div>

            {/* Weighted Forecast */}
            <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4 flex items-center gap-3">
              <div className="text-interactive">
                <TrendingUpIcon />
              </div>
              <div>
                <p className="text-2xl font-semibold text-white">
                  {forecastLoading ? "\u2014" : formatCurrency(forecast?.weighted_pipeline)}
                </p>
                <p className="text-sm text-slate-400">Weighted Forecast</p>
              </div>
            </div>
          </div>

          {/* ---- Stage Filter Tabs ---- */}
          <div className="flex gap-2">
            {STAGE_FILTERS.map((f) => (
              <button
                key={f.value}
                onClick={() => setStageFilter(f.value)}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                  stageFilter === f.value
                    ? "bg-interactive text-white"
                    : "text-slate-400 hover:text-white"
                }`}
              >
                {f.label}
              </button>
            ))}
          </div>

          {/* ---- Territory Table ---- */}
          <div className="bg-slate-800/50 border border-slate-700 rounded-xl overflow-hidden">
            {territoryLoading ? (
              <div className="p-8 space-y-3">
                {[1, 2, 3, 4].map((i) => (
                  <div key={i} className="h-10 bg-slate-700 rounded animate-pulse" />
                ))}
              </div>
            ) : accounts.length === 0 ? (
              <div className="p-12 text-center">
                <BuildingIcon className="w-10 h-10 text-slate-600 mx-auto mb-3" />
                <p className="text-slate-400 text-sm">No accounts yet. Start tracking leads to build your territory.</p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-slate-700 text-slate-400 text-left">
                      {([
                        ["company_name", "Company"],
                        ["lifecycle_stage", "Stage"],
                        ["health_score", "Health"],
                        ["expected_value", "Value"],
                        ["last_activity_at", "Last Activity"],
                        ["next_action", "Next Action"],
                      ] as [SortKey, string][]).map(([key, label]) => (
                        <th
                          key={key}
                          className="px-4 py-3 font-medium cursor-pointer select-none hover:text-white transition-colors"
                          onClick={() => handleSort(key)}
                        >
                          <span className="flex items-center gap-1">
                            {label}
                            <SortIndicator col={key} />
                          </span>
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {accounts.map((acct) => (
                      <tr
                        key={acct.id}
                        className="border-b border-slate-700/50 hover:bg-slate-700/30 cursor-pointer transition-colors"
                        onClick={() => setSelectedAccount(acct)}
                      >
                        <td className="px-4 py-3 text-white font-medium">{acct.company_name}</td>
                        <td className="px-4 py-3">
                          <span className={`inline-block text-xs px-2 py-0.5 rounded border ${stageBadgeColor(acct.lifecycle_stage)}`}>
                            {capitalize(acct.lifecycle_stage)}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-2">
                            <div className="w-16 h-2 bg-slate-700 rounded-full overflow-hidden">
                              <div
                                className={`h-full rounded-full ${healthBarColor(acct.health_score)}`}
                                style={{ width: `${Math.min(acct.health_score, 100)}%` }}
                              />
                            </div>
                            <span className={`text-xs font-mono ${healthColor(acct.health_score)}`}>
                              {acct.health_score}
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-3 text-slate-300 font-mono text-xs">
                          {formatCurrency(acct.expected_value)}
                        </td>
                        <td className="px-4 py-3 text-slate-400 text-xs">
                          {relativeTime(acct.last_activity_at)}
                        </td>
                        <td className="px-4 py-3 text-slate-300 text-xs max-w-[200px] truncate">
                          {acct.next_action || "\u2014"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* ---- Pipeline Forecast ---- */}
          <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
            <h2 className="text-lg font-display text-white mb-4">Pipeline Forecast</h2>
            {forecastLoading ? (
              <div className="h-64 bg-slate-700 rounded animate-pulse" />
            ) : chartData.length === 0 ? (
              <p className="text-slate-500 text-sm py-12 text-center">No forecast data available.</p>
            ) : (
              <>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={chartData} barGap={4}>
                    <XAxis
                      dataKey="stage"
                      stroke="#64748b"
                      tick={{ fill: "#94a3b8", fontSize: 12 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      stroke="#64748b"
                      tick={{ fill: "#94a3b8", fontSize: 11 }}
                      axisLine={false}
                      tickLine={false}
                      tickFormatter={(v: number) => formatCurrency(v)}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#1e293b",
                        border: "1px solid #334155",
                        borderRadius: "8px",
                        color: "#e2e8f0",
                      }}
                      formatter={(value: number, name: string) => [
                        formatCurrency(value),
                        name === "totalValue" ? "Total Value" : "Weighted Value",
                      ]}
                    />
                    <Bar dataKey="totalValue" fill="#475569" radius={[4, 4, 0, 0]} name="totalValue" />
                    <Bar dataKey="weightedValue" fill="var(--interactive)" radius={[4, 4, 0, 0]} name="weightedValue" />
                  </BarChart>
                </ResponsiveContainer>
                <p className="mt-4 text-sm text-slate-400 text-center">
                  Total Pipeline: {formatCurrency(forecast?.total_pipeline)} | Weighted: {formatCurrency(forecast?.weighted_pipeline)}
                </p>
              </>
            )}
          </div>

          {/* ---- Quota Tracking ---- */}
          <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
            <h2 className="text-lg font-display text-white mb-4">Quota Tracking</h2>

            {quotasLoading ? (
              <div className="space-y-3">
                {[1, 2].map((i) => (
                  <div key={i} className="h-16 bg-slate-700 rounded animate-pulse" />
                ))}
              </div>
            ) : quotas && quotas.length > 0 ? (
              <div className="space-y-4 mb-6">
                {quotas.map((q) => {
                  const pct = q.target_value > 0 ? Math.round((q.actual_value / q.target_value) * 100) : 0;
                  return (
                    <div key={q.id} className="bg-slate-800 border border-slate-700 rounded-lg p-4">
                      <div className="flex items-center justify-between mb-2">
                        <span className="text-white text-sm font-medium">{q.period}</span>
                        <span className={`text-sm font-mono ${pct >= 75 ? "text-success" : pct >= 50 ? "text-yellow-400" : "text-critical"}`}>
                          {pct}%
                        </span>
                      </div>
                      <div className="w-full h-2 bg-slate-700 rounded-full overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all ${quotaBarColor(pct)}`}
                          style={{ width: `${Math.min(pct, 100)}%` }}
                        />
                      </div>
                      <div className="flex justify-between mt-1 text-xs text-slate-500">
                        <span>{formatCurrency(q.actual_value)} actual</span>
                        <span>{formatCurrency(q.target_value)} target</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            ) : (
              <p className="text-slate-500 text-sm mb-6">No quotas set. Add one below to track your progress.</p>
            )}

            {/* Set Quota Form */}
            <form onSubmit={handleQuotaSubmit} className="flex flex-col sm:flex-row gap-3">
              <input
                type="text"
                value={quotaPeriod}
                onChange={(e) => setQuotaPeriod(e.target.value)}
                placeholder="Period (e.g. Q1 2026)"
                className="flex-1 bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-interactive focus:border-transparent"
              />
              <input
                type="number"
                value={quotaTarget}
                onChange={(e) => setQuotaTarget(e.target.value)}
                placeholder="Target value ($)"
                min="0"
                step="1000"
                className="flex-1 bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-white text-sm placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-interactive focus:border-transparent"
              />
              <button
                type="submit"
                disabled={setQuota.isPending}
                className="px-5 py-2 bg-interactive text-white text-sm rounded-lg font-medium hover:bg-interactive-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
              >
                {setQuota.isPending ? "Setting..." : "Set Quota"}
              </button>
            </form>
          </div>
        </div>
      </div>

      {/* ---- Account Detail Slide-Over ---- */}
      {selectedAccount && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black/40 z-40"
            onClick={() => setSelectedAccount(null)}
          />
          <AccountDetailPanel
            account={selectedAccount}
            onClose={() => setSelectedAccount(null)}
          />
        </>
      )}
    </DashboardLayout>
  );
}
