import { useState } from "react";
import type { InstalledSkill } from "@/api/skills";
import { useInstalledSkills, useUninstallSkill } from "@/hooks/useSkills";
import { TrustLevelBadge } from "./TrustLevelBadge";

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
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
  return formatDate(dateString);
}

interface InstalledSkillRowProps {
  skill: InstalledSkill;
  onUninstall: () => void;
  isUninstalling: boolean;
}

function InstalledSkillRow({
  skill,
  onUninstall,
  isUninstalling,
}: InstalledSkillRowProps) {
  const [confirmUninstall, setConfirmUninstall] = useState(false);
  const successRate =
    skill.execution_count > 0
      ? Math.round((skill.success_count / skill.execution_count) * 100)
      : null;

  return (
    <div className="group bg-slate-800/50 border border-slate-700 rounded-xl p-5 transition-all duration-200 hover:bg-slate-800/80 hover:border-slate-600">
      <div className="flex items-start justify-between gap-4">
        {/* Left: info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="text-base font-semibold text-white truncate">
              {skill.skill_path}
            </h3>
            <TrustLevelBadge level={skill.trust_level} size="sm" />
          </div>

          {/* Stats row */}
          <div className="mt-2 flex flex-wrap items-center gap-4 text-xs text-slate-500">
            <span className="inline-flex items-center gap-1">
              <svg
                className="w-3.5 h-3.5"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M13 10V3L4 14h7v7l9-11h-7z"
                />
              </svg>
              {skill.execution_count} execution
              {skill.execution_count !== 1 ? "s" : ""}
            </span>
            {successRate !== null && (
              <span
                className={`inline-flex items-center gap-1 ${
                  successRate >= 80
                    ? "text-emerald-500"
                    : successRate >= 50
                      ? "text-amber-500"
                      : "text-red-500"
                }`}
              >
                <svg
                  className="w-3.5 h-3.5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"
                  />
                </svg>
                {successRate}% success
              </span>
            )}
            {skill.last_used_at && (
              <span className="inline-flex items-center gap-1">
                <svg
                  className="w-3.5 h-3.5"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
                  />
                </svg>
                Last used {formatRelative(skill.last_used_at)}
              </span>
            )}
            <span>Installed {formatDate(skill.installed_at)}</span>
          </div>
        </div>

        {/* Right: uninstall */}
        <div className="flex-shrink-0">
          {confirmUninstall ? (
            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  onUninstall();
                  setConfirmUninstall(false);
                }}
                disabled={isUninstalling}
                className="px-3 py-1.5 text-xs font-medium text-red-400 bg-red-500/10 border border-red-500/30 hover:bg-red-500/20 rounded-lg transition-colors disabled:opacity-50"
              >
                {isUninstalling ? "Removing..." : "Confirm"}
              </button>
              <button
                onClick={() => setConfirmUninstall(false)}
                className="px-3 py-1.5 text-xs font-medium text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setConfirmUninstall(true)}
              className="p-2 text-slate-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
              title="Uninstall skill"
            >
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function InstalledSkills() {
  const { data: skills, isLoading, error } = useInstalledSkills();
  const uninstallSkill = useUninstallSkill();

  // Error
  if (error) {
    return (
      <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4">
        <p className="text-red-400">
          Failed to load installed skills. Please try again.
        </p>
      </div>
    );
  }

  // Loading
  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="bg-slate-800/50 border border-slate-700 rounded-xl p-5 animate-pulse"
          >
            <div className="flex items-start justify-between">
              <div className="flex-1 space-y-2">
                <div className="flex items-center gap-2">
                  <div className="h-5 bg-slate-700 rounded w-48" />
                  <div className="h-5 bg-slate-700 rounded-full w-20" />
                </div>
                <div className="flex gap-4">
                  <div className="h-4 bg-slate-700 rounded w-24" />
                  <div className="h-4 bg-slate-700 rounded w-20" />
                  <div className="h-4 bg-slate-700 rounded w-28" />
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  // Empty
  if (!skills || skills.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-4">
        <div className="relative">
          <div className="absolute inset-0 bg-primary-500/20 blur-3xl rounded-full" />
          <div className="relative w-24 h-24 bg-slate-800 border border-slate-700 rounded-2xl flex items-center justify-center">
            <svg
              className="w-12 h-12 text-slate-500"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={1.5}
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
              />
            </svg>
          </div>
        </div>
        <h3 className="mt-6 text-xl font-semibold text-white">
          No skills installed
        </h3>
        <p className="mt-2 text-slate-400 text-center max-w-md">
          Browse the skill catalog and install skills to extend ARIA&apos;s capabilities.
        </p>
      </div>
    );
  }

  // List
  return (
    <div className="space-y-3">
      {skills.map((skill, index) => (
        <div
          key={skill.id}
          className="animate-in fade-in slide-in-from-bottom-4"
          style={{
            animationDelay: `${index * 50}ms`,
            animationFillMode: "both",
          }}
        >
          <InstalledSkillRow
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
  );
}
