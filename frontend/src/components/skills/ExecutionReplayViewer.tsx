import { useState, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Clock,
  Bot,
  Zap,
  User,
  Calendar,
  Shield,
  ShieldCheck,
  Download,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  XCircle,
  Lock,
  Lightbulb,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  Loader2,
  AlertTriangle,
  RefreshCw,
  FileSearch,
} from "lucide-react";
import { useExecutionReplay } from "@/hooks/useSkills";
import { downloadReplayPdf } from "@/api/skills";
import type { ReplayStep, StepStatus, RiskLevel } from "@/api/skills";
import { TrustLevelBadge } from "./TrustLevelBadge";

// --- Config maps ---

const agentColors: Record<string, string> = {
  hunter: "from-emerald-500 to-emerald-600",
  analyst: "from-blue-500 to-blue-600",
  strategist: "from-violet-500 to-violet-600",
  scribe: "from-amber-500 to-amber-600",
  operator: "from-rose-500 to-rose-600",
  scout: "from-cyan-500 to-cyan-600",
};

const stepStatusConfig: Record<
  StepStatus,
  { label: string; classes: string; icon: typeof Clock }
> = {
  pending: { label: "Pending", classes: "text-slate-500", icon: Clock },
  running: { label: "Running", classes: "text-primary-400", icon: Loader2 },
  completed: { label: "Done", classes: "text-success", icon: CheckCircle2 },
  failed: { label: "Failed", classes: "text-critical", icon: XCircle },
  skipped: { label: "Skipped", classes: "text-slate-500", icon: Minus },
};

const riskColorMap: Record<string, string> = {
  low: "text-success",
  medium: "text-warning",
  high: "text-critical",
  critical: "text-interactive",
};

// --- Utilities ---

function formatTimestamp(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

function formatMs(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const remaining = Math.round(seconds % 60);
  return remaining > 0 ? `${minutes}m ${remaining}s` : `${minutes}m`;
}

function executionTimeColor(ms: number): string {
  if (ms < 500) return "text-success";
  if (ms < 2000) return "text-warning";
  return "text-critical";
}

function triggerIcon(reason: string) {
  const lower = reason.toLowerCase();
  if (lower.includes("schedule") || lower.includes("cron"))
    return Calendar;
  if (lower.includes("user") || lower.includes("manual"))
    return User;
  return Zap;
}

function renderData(data: unknown): string {
  if (data === null || data === undefined) return "null";
  if (typeof data === "string") return data;
  try {
    return JSON.stringify(data, null, 2);
  } catch {
    return String(data);
  }
}

// --- Sub-components ---

function SkeletonBlock({ className }: { className?: string }) {
  return (
    <div
      className={`animate-pulse bg-slate-700/50 rounded-lg ${className ?? ""}`}
    />
  );
}

function LoadingSkeleton() {
  return (
    <div className="space-y-6">
      {/* Header skeleton */}
      <div className="flex items-center gap-4">
        <SkeletonBlock className="w-8 h-8 rounded-full" />
        <SkeletonBlock className="w-48 h-6" />
        <SkeletonBlock className="w-24 h-5 ml-auto" />
      </div>

      {/* Summary strip skeleton */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="bg-slate-800/50 border border-slate-700 rounded-xl p-4"
            style={{ animationDelay: `${i * 100}ms` }}
          >
            <SkeletonBlock className="w-16 h-4 mb-2" />
            <SkeletonBlock className="w-24 h-6" />
          </div>
        ))}
      </div>

      {/* Timeline skeleton */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
        <SkeletonBlock className="w-40 h-5 mb-6" />
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="flex gap-4 mb-6" style={{ animationDelay: `${(i + 4) * 100}ms` }}>
            <SkeletonBlock className="w-8 h-8 rounded-full flex-shrink-0" />
            <div className="flex-1">
              <SkeletonBlock className="w-48 h-4 mb-2" />
              <SkeletonBlock className="w-full h-16" />
            </div>
          </div>
        ))}
      </div>

      {/* Bottom panels skeleton */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
          <SkeletonBlock className="w-32 h-5 mb-4" />
          <SkeletonBlock className="w-full h-12" />
        </div>
        <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
          <SkeletonBlock className="w-32 h-5 mb-4" />
          <SkeletonBlock className="w-full h-12" />
        </div>
      </div>
    </div>
  );
}

interface TimelineStepProps {
  step: ReplayStep;
  isLast: boolean;
  userClearance: string;
}

function TimelineStep({ step, isLast, userClearance }: TimelineStepProps) {
  const [expanded, setExpanded] = useState(false);

  const statusConfig = stepStatusConfig[step.status];
  const StatusIcon = statusConfig.icon;
  const hasRedactedInput =
    step.input_data === null && step.input_summary !== null;
  const hasRedactedOutput =
    step.output_data === null && step.output_summary !== null;
  const canSeeRaw = userClearance === "admin";

  return (
    <div className="relative flex gap-4">
      {/* Timeline connector */}
      <div className="flex flex-col items-center">
        <div className="flex items-center justify-center w-9 h-9 rounded-full bg-slate-800 border border-slate-700 z-10 flex-shrink-0">
          <div className="flex items-center justify-center w-6 h-6 rounded-full bg-slate-700 text-xs font-bold text-white">
            {step.step_number}
          </div>
        </div>
        {!isLast && (
          <div
            className={`w-px flex-1 min-h-[24px] ${
              step.status === "completed"
                ? "bg-success/40"
                : step.status === "failed"
                  ? "bg-critical/40"
                  : "bg-slate-700"
            }`}
          />
        )}
      </div>

      {/* Step content */}
      <div className="flex-1 pb-6">
        <button
          onClick={() => setExpanded(!expanded)}
          className="w-full text-left bg-slate-800/50 border border-slate-700 rounded-xl p-4 hover:bg-slate-800/80 hover:border-slate-600 transition-all duration-200"
        >
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3 min-w-0">
              <StatusIcon
                className={`w-4 h-4 flex-shrink-0 ${statusConfig.classes} ${
                  step.status === "running" ? "animate-spin" : ""
                }`}
              />
              <span className="text-sm font-medium text-white truncate">
                {step.skill_name ?? `Step ${step.step_number}`}
              </span>
              {step.agent_id && (
                <span className="flex items-center gap-1.5">
                  <div
                    className={`w-2.5 h-2.5 rounded-full bg-gradient-to-br ${
                      agentColors[step.agent_id] ??
                      "from-slate-500 to-slate-600"
                    }`}
                  />
                  <span className="text-xs text-slate-400 capitalize">
                    {step.agent_id}
                  </span>
                </span>
              )}
            </div>
            <div className="flex items-center gap-3 flex-shrink-0">
              {step.execution_time_ms !== null && (
                <span className="text-xs text-slate-500">
                  {formatMs(step.execution_time_ms)}
                </span>
              )}
              {expanded ? (
                <ChevronUp className="w-4 h-4 text-slate-500" />
              ) : (
                <ChevronDown className="w-4 h-4 text-slate-500" />
              )}
            </div>
          </div>
        </button>

        {/* Expanded detail */}
        {expanded && (
          <div className="mt-2 space-y-3 pl-1">
            {/* Input */}
            <div className="bg-slate-900/50 border border-slate-700/50 rounded-lg p-3">
              <h5 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                Input
              </h5>
              {!canSeeRaw && hasRedactedInput ? (
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <Lock className="w-3.5 h-3.5" />
                  <span>Redacted -- insufficient clearance</span>
                </div>
              ) : step.input_data !== null ? (
                <pre className="text-xs text-slate-300 font-mono whitespace-pre-wrap break-words overflow-x-auto max-h-64 overflow-y-auto">
                  {renderData(step.input_data)}
                </pre>
              ) : step.input_summary ? (
                <p className="text-xs text-slate-300">{step.input_summary}</p>
              ) : (
                <p className="text-xs text-slate-500 italic">No input data</p>
              )}
            </div>

            {/* Prompt */}
            {step.prompt_used && (
              <div className="bg-slate-900/50 border border-slate-700/50 rounded-lg p-3">
                <h5 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                  Prompt
                </h5>
                <pre className="text-xs text-slate-300 font-mono whitespace-pre-wrap break-words overflow-x-auto max-h-48 overflow-y-auto bg-slate-950/50 rounded p-2 border border-slate-800">
                  {step.prompt_used}
                </pre>
              </div>
            )}

            {/* API Calls */}
            {step.api_calls && step.api_calls.length > 0 && (
              <div className="bg-slate-900/50 border border-slate-700/50 rounded-lg p-3">
                <h5 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                  API Calls
                </h5>
                <div className="flex flex-wrap gap-1.5">
                  {step.api_calls.map((call, idx) => (
                    <span
                      key={idx}
                      className="inline-flex items-center px-2 py-0.5 text-[10px] font-medium text-info bg-info/10 rounded-full border border-info/20"
                    >
                      {call}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {/* Output */}
            <div className="bg-slate-900/50 border border-slate-700/50 rounded-lg p-3">
              <h5 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                Output
              </h5>
              {!canSeeRaw && hasRedactedOutput ? (
                <div className="flex items-center gap-2 text-xs text-slate-500">
                  <Lock className="w-3.5 h-3.5" />
                  <span>Redacted -- insufficient clearance</span>
                </div>
              ) : step.output_data !== null ? (
                <pre className="text-xs text-slate-300 font-mono whitespace-pre-wrap break-words overflow-x-auto max-h-64 overflow-y-auto">
                  {renderData(step.output_data)}
                </pre>
              ) : step.output_summary ? (
                <p className="text-xs text-slate-300">{step.output_summary}</p>
              ) : (
                <p className="text-xs text-slate-500 italic">
                  No output data
                </p>
              )}
            </div>

            {/* Extracted Facts */}
            {step.extracted_facts.length > 0 && (
              <div className="bg-slate-900/50 border border-slate-700/50 rounded-lg p-3">
                <h5 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
                  Extracted Facts
                </h5>
                <ul className="space-y-1.5">
                  {step.extracted_facts.map((fact, idx) => (
                    <li
                      key={idx}
                      className="flex items-start gap-2 text-xs text-slate-300"
                    >
                      <Lightbulb className="w-3.5 h-3.5 text-warning mt-0.5 flex-shrink-0" />
                      <span>{renderData(fact)}</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// --- Main component ---

interface ExecutionReplayViewerProps {
  executionId: string | null;
}

export function ExecutionReplayViewer({
  executionId,
}: ExecutionReplayViewerProps) {
  const navigate = useNavigate();
  const { data: replay, isLoading, isError, error, refetch } = useExecutionReplay(executionId);
  const [hashExpanded, setHashExpanded] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);

  const handleDownload = useCallback(async () => {
    if (!executionId) return;
    setIsDownloading(true);
    try {
      const blob = await downloadReplayPdf(executionId);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `audit-replay-${executionId.slice(0, 8)}.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch {
      // Download failed — could add toast notification here
    } finally {
      setIsDownloading(false);
    }
  }, [executionId]);

  // --- State: no execution ID ---
  if (!executionId) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] text-center">
        <FileSearch className="w-12 h-12 text-slate-600 mb-4" />
        <h2 className="text-lg font-semibold text-white mb-2">
          Execution not found
        </h2>
        <p className="text-sm text-slate-400 mb-6">
          No execution ID was provided. Please navigate from the audit log.
        </p>
        <button
          onClick={() => navigate("/dashboard/skills")}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-slate-800 border border-slate-700 rounded-lg hover:bg-slate-700 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Skills
        </button>
      </div>
    );
  }

  // --- State: loading ---
  if (isLoading) {
    return (
      <div className="px-1">
        <LoadingSkeleton />
      </div>
    );
  }

  // --- State: error ---
  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] text-center">
        <AlertTriangle className="w-12 h-12 text-critical mb-4" />
        <h2 className="text-lg font-semibold text-white mb-2">
          Failed to load execution replay
        </h2>
        <p className="text-sm text-slate-400 mb-6 max-w-md">
          {error instanceof Error ? error.message : "An unexpected error occurred while loading the execution data."}
        </p>
        <button
          onClick={() => refetch()}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-slate-800 border border-slate-700 rounded-lg hover:bg-slate-700 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Retry
        </button>
      </div>
    );
  }

  // --- State: no data ---
  if (!replay) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] text-center">
        <FileSearch className="w-12 h-12 text-slate-600 mb-4" />
        <h2 className="text-lg font-semibold text-white mb-2">
          Execution not found
        </h2>
        <p className="text-sm text-slate-400 mb-6">
          The execution record for ID{" "}
          <code className="font-mono text-slate-300">
            {executionId.slice(0, 8)}
          </code>{" "}
          could not be found.
        </p>
        <button
          onClick={() => navigate("/dashboard/skills")}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-white bg-slate-800 border border-slate-700 rounded-lg hover:bg-slate-700 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Skills
        </button>
      </div>
    );
  }

  const { audit_entry, plan, steps, trust_impact, data_access_audit, user_clearance, hash_chain } = replay;
  const skillName = audit_entry.skill_path.split("/").pop() ?? audit_entry.skill_path;
  const TriggerIcon = triggerIcon(audit_entry.trigger_reason);
  const riskLevel: RiskLevel | null = plan?.risk_level ?? null;

  // For single-step executions without a plan, synthesize a step from audit_entry
  const timelineSteps: ReplayStep[] =
    steps.length > 0
      ? steps
      : [
          {
            step_number: 1,
            skill_id: audit_entry.skill_id,
            skill_name: skillName,
            status: audit_entry.success ? "completed" : "failed",
            input_data: null,
            input_summary: null,
            output_data: null,
            output_summary: audit_entry.error,
            prompt_used: null,
            api_calls: null,
            artifacts: [],
            extracted_facts: [],
            execution_time_ms: audit_entry.execution_time_ms,
            agent_id: audit_entry.agent_id,
          },
        ];

  return (
    <div className="space-y-6">
      {/* ========== 1. Header Bar ========== */}
      <div className="flex flex-col sm:flex-row sm:items-center gap-4">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <button
            onClick={() => navigate(-1)}
            className="flex items-center justify-center w-9 h-9 rounded-lg bg-slate-800 border border-slate-700 hover:bg-slate-700 transition-colors flex-shrink-0"
            aria-label="Go back"
          >
            <ArrowLeft className="w-4 h-4 text-slate-300" />
          </button>
          <div className="min-w-0">
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="text-xl font-bold text-white truncate">
                {skillName}
              </h1>
              <code className="text-xs font-mono text-slate-500 bg-slate-800 px-2 py-0.5 rounded border border-slate-700">
                {executionId.slice(0, 8)}
              </code>
              {audit_entry.success ? (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-success bg-success/10 rounded-full border border-success/20">
                  <CheckCircle2 className="w-3 h-3" />
                  Success
                </span>
              ) : (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-critical bg-critical/10 rounded-full border border-critical/20">
                  <XCircle className="w-3 h-3" />
                  Failed
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500 mt-1">
              {formatTimestamp(audit_entry.created_at)}
            </p>
          </div>
        </div>
        <button
          onClick={handleDownload}
          disabled={isDownloading}
          className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium text-slate-300 bg-slate-800 border border-slate-700 rounded-lg hover:bg-slate-700 hover:text-white transition-colors disabled:opacity-50 flex-shrink-0"
        >
          {isDownloading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <Download className="w-4 h-4" />
          )}
          Download Audit Report
        </button>
      </div>

      {/* ========== 2. Summary Strip ========== */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Execution Time */}
        <div
          className="bg-slate-800/50 border border-slate-700 rounded-xl p-4"
          style={{ animationDelay: "0ms" }}
        >
          <div className="flex items-center gap-2 mb-1">
            <Clock className="w-4 h-4 text-slate-500" />
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Execution Time
            </span>
          </div>
          <p
            className={`text-lg font-bold ${executionTimeColor(audit_entry.execution_time_ms)}`}
          >
            {formatMs(audit_entry.execution_time_ms)}
          </p>
        </div>

        {/* Agent */}
        <div
          className="bg-slate-800/50 border border-slate-700 rounded-xl p-4"
          style={{ animationDelay: "100ms" }}
        >
          <div className="flex items-center gap-2 mb-1">
            <Bot className="w-4 h-4 text-slate-500" />
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Agent
            </span>
          </div>
          {audit_entry.agent_id ? (
            <div className="flex items-center gap-2">
              <div
                className={`w-3 h-3 rounded-full bg-gradient-to-br ${
                  agentColors[audit_entry.agent_id] ??
                  "from-slate-500 to-slate-600"
                }`}
              />
              <p className="text-lg font-bold text-white capitalize">
                {audit_entry.agent_id}
              </p>
            </div>
          ) : (
            <p className="text-lg font-bold text-slate-500">N/A</p>
          )}
        </div>

        {/* Trigger */}
        <div
          className="bg-slate-800/50 border border-slate-700 rounded-xl p-4"
          style={{ animationDelay: "200ms" }}
        >
          <div className="flex items-center gap-2 mb-1">
            <TriggerIcon className="w-4 h-4 text-slate-500" />
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Trigger
            </span>
          </div>
          <p className="text-lg font-bold text-white truncate">
            {audit_entry.trigger_reason}
          </p>
        </div>

        {/* Risk Level */}
        <div
          className="bg-slate-800/50 border border-slate-700 rounded-xl p-4"
          style={{ animationDelay: "300ms" }}
        >
          <div className="flex items-center gap-2 mb-1">
            <Shield className="w-4 h-4 text-slate-500" />
            <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Risk Level
            </span>
          </div>
          {riskLevel ? (
            <p
              className={`text-lg font-bold capitalize ${riskColorMap[riskLevel] ?? "text-slate-400"}`}
            >
              {riskLevel}
            </p>
          ) : (
            <p className="text-lg font-bold text-slate-500">N/A</p>
          )}
        </div>
      </div>

      {/* ========== 3. Execution Timeline ========== */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
        <h2 className="text-base font-semibold text-white mb-6 flex items-center gap-2">
          <Zap className="w-4 h-4 text-primary-400" />
          Execution Timeline
          <span className="text-xs text-slate-500 font-normal">
            {timelineSteps.length} step{timelineSteps.length !== 1 ? "s" : ""}
          </span>
        </h2>

        <div>
          {timelineSteps.map((step, index) => (
            <TimelineStep
              key={step.step_number}
              step={step}
              isLast={index === timelineSteps.length - 1}
              userClearance={user_clearance}
            />
          ))}
        </div>
      </div>

      {/* ========== 4. Trust Impact Panel ========== */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
        <h2 className="text-base font-semibold text-white mb-4 flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-primary-400" />
          Trust Impact
        </h2>
        <div className="flex items-center justify-center gap-6">
          <div className="text-center">
            <p className="text-xs text-slate-500 mb-2">Before</p>
            <TrustLevelBadge
              level={trust_impact.before as "core" | "verified" | "community" | "user"}
              size="md"
            />
          </div>
          <div className="flex items-center justify-center w-10 h-10">
            {trust_impact.delta === "increased" ? (
              <ArrowUpRight className="w-6 h-6 text-success" />
            ) : trust_impact.delta === "decreased" ? (
              <ArrowDownRight className="w-6 h-6 text-critical" />
            ) : (
              <Minus className="w-6 h-6 text-slate-500" />
            )}
          </div>
          <div className="text-center">
            <p className="text-xs text-slate-500 mb-2">After</p>
            <TrustLevelBadge
              level={trust_impact.after as "core" | "verified" | "community" | "user"}
              size="md"
            />
          </div>
        </div>
      </div>

      {/* ========== 5. Data Access Audit Panel ========== */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-6">
        <h2 className="text-base font-semibold text-white mb-4 flex items-center gap-2">
          <Lock className="w-4 h-4 text-primary-400" />
          Data Access Audit
        </h2>

        <div className="space-y-4">
          {/* Requested */}
          <div>
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
              Requested
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {data_access_audit.requested.length > 0 ? (
                data_access_audit.requested.map((cls) => (
                  <span
                    key={cls}
                    className="inline-flex items-center px-2 py-0.5 text-[10px] font-semibold tracking-wider text-slate-300 bg-slate-700/50 rounded border border-slate-600"
                  >
                    {cls}
                  </span>
                ))
              ) : (
                <span className="text-xs text-slate-500 italic">
                  No data classes requested
                </span>
              )}
            </div>
          </div>

          {/* Granted vs Denied */}
          <div>
            <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-2">
              Granted vs Denied
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {data_access_audit.granted.map((cls) => (
                <span
                  key={`g-${cls}`}
                  className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-semibold tracking-wider text-success bg-success/10 rounded border border-success/20"
                >
                  <CheckCircle2 className="w-2.5 h-2.5" />
                  {cls}
                </span>
              ))}
              {data_access_audit.denied.map((cls) => (
                <span
                  key={`d-${cls}`}
                  className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-semibold tracking-wider text-critical bg-critical/10 rounded border border-critical/20"
                >
                  <Lock className="w-2.5 h-2.5" />
                  {cls}
                </span>
              ))}
              {data_access_audit.granted.length === 0 &&
                data_access_audit.denied.length === 0 && (
                  <span className="text-xs text-slate-500 italic">
                    No data access decisions recorded
                  </span>
                )}
            </div>
          </div>

          {/* Redaction notice */}
          {audit_entry.data_redacted && (
            <div className="flex items-center gap-2 text-xs text-slate-500 bg-slate-900/30 rounded-lg px-3 py-2 border border-slate-800">
              <Lock className="w-3.5 h-3.5 flex-shrink-0" />
              Some data was redacted during this execution
            </div>
          )}
        </div>
      </div>

      {/* ========== 6. Hash Chain Verification ========== */}
      <div className="bg-slate-800/50 border border-slate-700 rounded-xl">
        <button
          onClick={() => setHashExpanded(!hashExpanded)}
          className="w-full flex items-center justify-between p-4 text-left hover:bg-slate-800/80 transition-colors rounded-xl"
        >
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-success" />
            <span className="text-sm font-medium text-slate-300">
              Cryptographic audit trail verified
            </span>
          </div>
          {hashExpanded ? (
            <ChevronUp className="w-4 h-4 text-slate-500" />
          ) : (
            <ChevronDown className="w-4 h-4 text-slate-500" />
          )}
        </button>

        {hashExpanded && (
          <div className="px-4 pb-4 pt-0 border-t border-slate-700/50 mt-0">
            <div className="mt-4 space-y-3 bg-slate-900/50 rounded-lg p-4 border border-slate-800">
              <div>
                <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">
                  Previous Hash
                </p>
                <code className="text-xs font-mono text-slate-400 break-all">
                  {hash_chain.previous_hash}
                </code>
              </div>
              <div>
                <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-wider mb-1">
                  Entry Hash
                </p>
                <code className="text-xs font-mono text-slate-400 break-all">
                  {hash_chain.entry_hash}
                </code>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
