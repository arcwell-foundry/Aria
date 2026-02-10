import { useNavigate } from "react-router-dom";
import { ChevronRight } from "lucide-react";
import type { AuditEntry } from "@/api/skills";
import { useSkillAudit } from "@/hooks/useSkills";
import { TrustLevelBadge } from "./TrustLevelBadge";

function formatTimestamp(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function AuditEntryRow({ entry }: { entry: AuditEntry }) {
  const navigate = useNavigate();

  return (
    <div
      className="group bg-slate-800/30 border border-slate-700/50 rounded-lg p-4 transition-colors hover:bg-slate-800/50 cursor-pointer"
      onClick={() => navigate(`/dashboard/skills/audit/${entry.id}`)}
    >
      <div className="flex items-start justify-between gap-3">
        {/* Left: status + skill info */}
        <div className="flex items-start gap-3 min-w-0">
          {/* Status indicator */}
          <div
            className={`mt-0.5 flex-shrink-0 w-2 h-2 rounded-full ${
              entry.success ? "bg-success" : "bg-critical"
            }`}
          />

          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-medium text-white truncate">
                {entry.skill_path}
              </span>
              <TrustLevelBadge level={entry.skill_trust_level} size="sm" />
            </div>

            <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-slate-500">
              <span>{formatTimestamp(entry.created_at)}</span>
              <span>{formatDuration(entry.execution_time_ms)}</span>
              {entry.trigger_reason && (
                <span className="text-slate-600">{entry.trigger_reason}</span>
              )}
            </div>

            {/* Error message */}
            {entry.error && (
              <p className="mt-1.5 text-xs text-critical line-clamp-1">
                {entry.error}
              </p>
            )}

            {/* Security flags */}
            {entry.security_flags.length > 0 && (
              <div className="mt-1.5 flex flex-wrap gap-1">
                {entry.security_flags.map((flag) => (
                  <span
                    key={flag}
                    className="px-1.5 py-0.5 text-xs text-warning bg-warning/10 border border-warning/20 rounded"
                  >
                    {flag}
                  </span>
                ))}
              </div>
            )}

            {/* Data redaction indicator */}
            {entry.data_redacted && (
              <span className="mt-1.5 inline-flex items-center gap-1 text-xs text-slate-500">
                <svg
                  className="w-3 h-3"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                  />
                </svg>
                Data sanitized
              </span>
            )}
          </div>
        </div>

        {/* Right: success/fail badge + chevron */}
        <div className="flex items-center gap-2 flex-shrink-0">
          <span
            className={`px-2 py-0.5 text-xs font-medium rounded ${
              entry.success
                ? "text-success bg-success/10"
                : "text-critical bg-critical/10"
            }`}
          >
            {entry.success ? "Success" : "Failed"}
          </span>
          <ChevronRight className="w-4 h-4 text-slate-600 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0" />
        </div>
      </div>
    </div>
  );
}

export function SkillAuditLog() {
  const { data: entries, isLoading, error } = useSkillAudit();

  // Error
  if (error) {
    return (
      <div className="bg-critical/10 border border-critical/30 rounded-xl p-4">
        <p className="text-critical">
          Failed to load audit log. Please try again.
        </p>
      </div>
    );
  }

  // Loading
  if (isLoading) {
    return (
      <div className="space-y-3">
        {[1, 2, 3, 4, 5].map((i) => (
          <div
            key={i}
            className="bg-slate-800/30 border border-slate-700/50 rounded-lg p-4 animate-pulse"
          >
            <div className="flex items-start gap-3">
              <div className="w-2 h-2 mt-1.5 bg-slate-700 rounded-full" />
              <div className="flex-1 space-y-2">
                <div className="flex items-center gap-2">
                  <div className="h-4 bg-slate-700 rounded w-40" />
                  <div className="h-4 bg-slate-700 rounded-full w-16" />
                </div>
                <div className="flex gap-3">
                  <div className="h-3 bg-slate-700 rounded w-24" />
                  <div className="h-3 bg-slate-700 rounded w-12" />
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    );
  }

  // Empty
  if (!entries || entries.length === 0) {
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
                d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
              />
            </svg>
          </div>
        </div>
        <h3 className="mt-6 text-xl font-semibold text-white">
          No activity yet
        </h3>
        <p className="mt-2 text-slate-400 text-center max-w-md">
          Skill execution history will appear here once skills are used.
        </p>
      </div>
    );
  }

  // List
  return (
    <div className="space-y-2">
      {entries.map((entry, index) => (
        <div
          key={entry.id}
          className="animate-in fade-in slide-in-from-bottom-4"
          style={{
            animationDelay: `${index * 30}ms`,
            animationFillMode: "both",
          }}
        >
          <AuditEntryRow entry={entry} />
        </div>
      ))}
    </div>
  );
}
