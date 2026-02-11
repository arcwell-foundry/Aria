import { useState, useMemo } from "react";
import {
  Activity,
  CheckCircle2,
  Zap,
  Clock,
  Pencil,
  Trash2,
  Search,
  ChevronDown,
  ChevronUp,
  Sparkles,
  ArrowUpCircle,
} from "lucide-react";
import type { InstalledSkill, AuditEntry, CustomSkill } from "@/api/skills";
import {
  useInstalledSkills,
  useUninstallSkill,
  useSkillAudit,
  useCustomSkills,
  useDeleteCustomSkill,
  useApproveSkillGlobally,
} from "@/hooks/useSkills";
import { TrustLevelBadge } from "./TrustLevelBadge";
import { MiniDonutChart } from "./MiniDonutChart";
import { SkillEditSlideOver } from "./SkillEditSlideOver";

// --- Helpers ---

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatRelative(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return new Date(dateString).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

function formatTimestamp(dateString: string): string {
  return new Date(dateString).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

function successRateColor(rate: number): string {
  if (rate >= 0.8) return "#22c55e"; // success green
  if (rate >= 0.5) return "#f59e0b"; // warning amber
  return "#ef4444"; // critical red
}

// --- Stat Card ---

interface StatCardProps {
  icon: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
}

function StatCard({ icon, label, value, sub }: StatCardProps) {
  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-4">
      <div className="flex items-center gap-2 text-slate-400 mb-2">
        {icon}
        <span className="text-xs font-medium">{label}</span>
      </div>
      <div className="text-2xl font-bold text-white">{value}</div>
      {sub && <div className="text-xs text-slate-500 mt-1">{sub}</div>}
    </div>
  );
}

// --- Performance Skill Row ---

interface PerformanceSkillRowProps {
  skill: InstalledSkill;
  onUninstall: () => void;
  isUninstalling: boolean;
}

function PerformanceSkillRow({
  skill,
  onUninstall,
  isUninstalling,
}: PerformanceSkillRowProps) {
  const [confirmUninstall, setConfirmUninstall] = useState(false);
  const approveGlobally = useApproveSkillGlobally();
  const [confirmUpgrade, setConfirmUpgrade] = useState(false);

  const successRate =
    skill.execution_count > 0
      ? skill.success_count / skill.execution_count
      : 0;
  const successPct = Math.round(successRate * 100);

  return (
    <div className="group bg-slate-800/50 border border-slate-700 rounded-xl p-4 transition-all duration-200 hover:bg-slate-800/80 hover:border-slate-600">
      <div className="flex items-center gap-4">
        {/* Mini donut chart */}
        <div className="flex-shrink-0">
          <MiniDonutChart
            value={successRate}
            color={successRateColor(successRate)}
          />
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-sm font-semibold text-white truncate">
              {skill.skill_path}
            </h3>
            <TrustLevelBadge level={skill.trust_level} size="sm" />
          </div>
          <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-500">
            <span
              className={
                successPct >= 80
                  ? "text-success"
                  : successPct >= 50
                    ? "text-warning"
                    : "text-critical"
              }
            >
              {successPct}% success
            </span>
            <span>{skill.execution_count} executions</span>
            {skill.last_used_at && (
              <span>{formatRelative(skill.last_used_at)}</span>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex-shrink-0 flex items-center gap-1">
          {/* Upgrade trust (only for USER skills) */}
          {skill.trust_level === "user" && (
            <>
              {confirmUpgrade ? (
                <div className="flex items-center gap-1 mr-2">
                  <button
                    onClick={() => {
                      approveGlobally.mutate(skill.skill_id);
                      setConfirmUpgrade(false);
                    }}
                    className="px-2 py-1 text-xs font-medium text-primary-400 bg-primary-500/10 border border-primary-500/30 hover:bg-primary-500/20 rounded-lg transition-colors"
                  >
                    Confirm
                  </button>
                  <button
                    onClick={() => setConfirmUpgrade(false)}
                    className="px-2 py-1 text-xs text-slate-400 hover:text-white rounded-lg transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setConfirmUpgrade(true)}
                  className="p-1.5 text-slate-500 hover:text-primary-400 hover:bg-primary-500/10 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                  title="Approve globally"
                >
                  <ArrowUpCircle className="w-4 h-4" />
                </button>
              )}
            </>
          )}

          {/* Uninstall */}
          {confirmUninstall ? (
            <div className="flex items-center gap-1">
              <button
                onClick={() => {
                  onUninstall();
                  setConfirmUninstall(false);
                }}
                disabled={isUninstalling}
                className="px-2 py-1 text-xs font-medium text-critical bg-critical/10 border border-critical/30 hover:bg-critical/20 rounded-lg transition-colors disabled:opacity-50"
              >
                {isUninstalling ? "Removing..." : "Confirm"}
              </button>
              <button
                onClick={() => setConfirmUninstall(false)}
                className="px-2 py-1 text-xs text-slate-400 hover:text-white rounded-lg transition-colors"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmUninstall(true)}
              className="p-1.5 text-slate-500 hover:text-critical hover:bg-critical/10 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
              title="Uninstall"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// --- Custom Skills Section ---

function CustomSkillsSection() {
  const { data: skills, isLoading } = useCustomSkills();
  const deleteSkill = useDeleteCustomSkill();
  const [editingSkill, setEditingSkill] = useState<CustomSkill | null>(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2].map((i) => (
          <div
            key={i}
            className="bg-slate-800/30 border border-slate-700/50 rounded-lg p-4 animate-pulse"
          >
            <div className="h-4 bg-slate-700 rounded w-40" />
          </div>
        ))}
      </div>
    );
  }

  if (!skills || skills.length === 0) {
    return (
      <div className="text-center py-8">
        <Sparkles className="w-8 h-8 text-slate-600 mx-auto mb-2" />
        <p className="text-sm text-slate-500">
          Create custom skills to extend ARIA&apos;s capabilities.
        </p>
      </div>
    );
  }

  return (
    <>
      <div className="space-y-2">
        {skills.map((skill) => (
          <div
            key={skill.id}
            className="group bg-slate-800/30 border border-slate-700/50 rounded-lg p-4 flex items-center justify-between transition-colors hover:bg-slate-800/50"
          >
            <div className="min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-white">
                  {skill.skill_name}
                </span>
                <span className="px-1.5 py-0.5 text-xs text-slate-400 bg-slate-700/50 rounded">
                  v{skill.version}
                </span>
              </div>
              {skill.description && (
                <p className="text-xs text-slate-500 mt-0.5 truncate max-w-md">
                  {skill.description}
                </p>
              )}
            </div>

            <div className="flex items-center gap-1 flex-shrink-0">
              <button
                onClick={() => setEditingSkill(skill)}
                className="p-1.5 text-slate-500 hover:text-primary-400 hover:bg-primary-500/10 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                title="Edit"
              >
                <Pencil className="w-4 h-4" />
              </button>
              {confirmDeleteId === skill.id ? (
                <div className="flex items-center gap-1">
                  <button
                    onClick={() => {
                      deleteSkill.mutate(skill.id);
                      setConfirmDeleteId(null);
                    }}
                    className="px-2 py-1 text-xs text-critical bg-critical/10 border border-critical/30 rounded-lg"
                  >
                    Delete
                  </button>
                  <button
                    onClick={() => setConfirmDeleteId(null)}
                    className="px-2 py-1 text-xs text-slate-400 rounded-lg"
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  onClick={() => setConfirmDeleteId(skill.id)}
                  className="p-1.5 text-slate-500 hover:text-critical hover:bg-critical/10 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                  title="Delete"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      {editingSkill && (
        <SkillEditSlideOver
          skill={editingSkill}
          open={!!editingSkill}
          onClose={() => setEditingSkill(null)}
        />
      )}
    </>
  );
}

// --- Audit Section ---

type AuditFilter = "all" | "success" | "failed";

function AuditSection() {
  const { data: entries, isLoading } = useSkillAudit();
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<AuditFilter>("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const filtered = useMemo(() => {
    if (!entries) return [];
    return entries.filter((e: AuditEntry) => {
      if (filter === "success" && !e.success) return false;
      if (filter === "failed" && e.success) return false;
      if (search && !e.skill_path.toLowerCase().includes(search.toLowerCase()))
        return false;
      return true;
    });
  }, [entries, filter, search]);

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="bg-slate-800/30 border border-slate-700/50 rounded-lg p-4 animate-pulse"
          >
            <div className="flex gap-3">
              <div className="w-2 h-2 mt-1.5 bg-slate-700 rounded-full" />
              <div className="flex-1 space-y-2">
                <div className="h-4 bg-slate-700 rounded w-40" />
                <div className="h-3 bg-slate-700 rounded w-24" />
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {/* Search + filters */}
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input
            type="text"
            placeholder="Search by skill name..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2 bg-slate-800/50 border border-slate-700 rounded-lg text-sm text-white placeholder-slate-500 focus:outline-none focus:border-primary-500"
          />
        </div>
        <div className="flex gap-1">
          {(["all", "success", "failed"] as AuditFilter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-2 text-xs font-medium rounded-lg transition-colors capitalize ${
                filter === f
                  ? "bg-primary-600/20 text-primary-400"
                  : "text-slate-400 hover:text-white hover:bg-slate-700/50"
              }`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      {/* Entries */}
      {filtered.length === 0 ? (
        <p className="text-sm text-slate-500 text-center py-6">
          No matching audit entries.
        </p>
      ) : (
        <div className="space-y-1.5">
          {filtered.map((entry: AuditEntry) => {
            const isExpanded = expandedId === entry.id;
            return (
              <div
                key={entry.id}
                className="bg-slate-800/30 border border-slate-700/50 rounded-lg transition-colors hover:bg-slate-800/50"
              >
                <button
                  onClick={() =>
                    setExpandedId(isExpanded ? null : entry.id)
                  }
                  className="w-full p-3 flex items-center justify-between text-left"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div
                      className={`flex-shrink-0 w-2 h-2 rounded-full ${
                        entry.success ? "bg-success" : "bg-critical"
                      }`}
                    />
                    <span className="text-sm font-medium text-white truncate">
                      {entry.skill_path}
                    </span>
                    <TrustLevelBadge
                      level={entry.skill_trust_level}
                      size="sm"
                    />
                    <span className="text-xs text-slate-500">
                      {formatTimestamp(entry.created_at)}
                    </span>
                    <span className="text-xs text-slate-500">
                      {formatDuration(entry.execution_time_ms)}
                    </span>
                  </div>
                  {isExpanded ? (
                    <ChevronUp className="w-4 h-4 text-slate-500 flex-shrink-0" />
                  ) : (
                    <ChevronDown className="w-4 h-4 text-slate-500 flex-shrink-0" />
                  )}
                </button>

                {isExpanded && (
                  <div className="px-3 pb-3 border-t border-slate-700/50 pt-2 space-y-2 text-xs">
                    {entry.agent_id && (
                      <div>
                        <span className="text-slate-500">Agent:</span>{" "}
                        <span className="text-slate-300">{entry.agent_id}</span>
                      </div>
                    )}
                    <div>
                      <span className="text-slate-500">Data requested:</span>{" "}
                      <span className="text-slate-300">
                        {entry.data_classes_requested.join(", ") || "none"}
                      </span>
                    </div>
                    <div>
                      <span className="text-slate-500">Data granted:</span>{" "}
                      <span className="text-slate-300">
                        {entry.data_classes_granted.join(", ") || "none"}
                      </span>
                    </div>
                    {entry.security_flags.length > 0 && (
                      <div className="flex flex-wrap gap-1">
                        {entry.security_flags.map((flag) => (
                          <span
                            key={flag}
                            className="px-1.5 py-0.5 text-warning bg-warning/10 border border-warning/20 rounded"
                          >
                            {flag}
                          </span>
                        ))}
                      </div>
                    )}
                    {entry.data_redacted && (
                      <span className="text-slate-500">
                        Data was sanitized during execution
                      </span>
                    )}
                    {entry.error && (
                      <div className="p-2 bg-critical/10 border border-critical/20 rounded text-critical">
                        {entry.error}
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// --- Skill Discovery Placeholder ---

function SkillDiscoveryPlaceholder() {
  return (
    <div className="bg-slate-800/30 border border-dashed border-slate-700 rounded-xl p-6 text-center">
      <Sparkles className="w-6 h-6 text-primary-400 mx-auto mb-2" />
      <p className="text-sm text-slate-400">
        ARIA will recommend skills based on your usage patterns
      </p>
      <p className="text-xs text-slate-600 mt-1">Coming in Wave 6</p>
    </div>
  );
}

// --- Main Component ---

export function SkillPerformancePanel() {
  const { data: skills, isLoading, error } = useInstalledSkills();
  const uninstallSkill = useUninstallSkill();

  // Aggregate stats
  const stats = useMemo(() => {
    if (!skills || skills.length === 0) {
      return {
        total: 0,
        avgSuccess: 0,
        totalExecutions: 0,
        avgTime: "—",
      };
    }

    const totalExec = skills.reduce(
      (sum: number, s: InstalledSkill) => sum + s.execution_count,
      0
    );
    const totalSuccess = skills.reduce(
      (sum: number, s: InstalledSkill) => sum + s.success_count,
      0
    );
    const avgSuccess =
      totalExec > 0 ? Math.round((totalSuccess / totalExec) * 100) : 0;

    return {
      total: skills.length,
      avgSuccess,
      totalExecutions: totalExec,
      avgTime: "—", // Would need per-skill perf data for this; placeholder
    };
  }, [skills]);

  if (error) {
    return (
      <div className="bg-critical/10 border border-critical/30 rounded-xl p-4">
        <p className="text-critical">
          Failed to load skills. Please try again.
        </p>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="bg-slate-800/50 border border-slate-700 rounded-xl p-4 animate-pulse"
            >
              <div className="h-3 bg-slate-700 rounded w-20 mb-3" />
              <div className="h-7 bg-slate-700 rounded w-12" />
            </div>
          ))}
        </div>
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="bg-slate-800/50 border border-slate-700 rounded-xl p-5 animate-pulse"
            >
              <div className="flex items-center gap-4">
                <div className="w-10 h-10 bg-slate-700 rounded-full" />
                <div className="flex-1 space-y-2">
                  <div className="h-4 bg-slate-700 rounded w-48" />
                  <div className="h-3 bg-slate-700 rounded w-32" />
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Stat cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={<Activity className="w-4 h-4" />}
          label="Installed"
          value={String(stats.total)}
          sub={`${stats.total} skill${stats.total !== 1 ? "s" : ""}`}
        />
        <StatCard
          icon={<CheckCircle2 className="w-4 h-4" />}
          label="Success Rate"
          value={`${stats.avgSuccess}%`}
          sub="across all skills"
        />
        <StatCard
          icon={<Zap className="w-4 h-4" />}
          label="Executions"
          value={stats.totalExecutions.toLocaleString()}
          sub="total runs"
        />
        <StatCard
          icon={<Clock className="w-4 h-4" />}
          label="Avg Time"
          value={stats.avgTime}
          sub="per execution"
        />
      </div>

      {/* Skill discovery placeholder */}
      <SkillDiscoveryPlaceholder />

      {/* Installed skills table */}
      {skills && skills.length > 0 ? (
        <div>
          <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
            Installed Skills
          </h2>
          <div className="space-y-2">
            {skills.map((skill: InstalledSkill, index: number) => (
              <div
                key={skill.id}
                className="animate-in fade-in slide-in-from-bottom-4"
                style={{
                  animationDelay: `${index * 50}ms`,
                  animationFillMode: "both",
                }}
              >
                <PerformanceSkillRow
                  skill={skill}
                  onUninstall={() => uninstallSkill.mutate(skill.skill_id)}
                  isUninstalling={
                    uninstallSkill.isPending &&
                    uninstallSkill.variables === skill.skill_id
                  }
                />
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center py-12">
          <div className="w-16 h-16 bg-slate-800 border border-slate-700 rounded-2xl flex items-center justify-center mb-4">
            <Zap className="w-8 h-8 text-slate-500" />
          </div>
          <h3 className="text-lg font-semibold text-white">
            No skills installed
          </h3>
          <p className="mt-1 text-slate-400 text-sm">
            Browse the catalog to install skills.
          </p>
        </div>
      )}

      {/* Custom skills */}
      <div>
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
          Custom Skills
        </h2>
        <CustomSkillsSection />
      </div>

      {/* Audit log */}
      <div>
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-3">
          Recent Activity
        </h2>
        <AuditSection />
      </div>
    </div>
  );
}
