import { useState } from "react";
import {
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  ChevronDown,
  ChevronUp,
  Shield,
  AlertTriangle,
  Zap,
  Bot,
  SkipForward,
} from "lucide-react";
import type {
  ExecutionPlan,
  ExecutionStep,
  RiskLevel,
  StepStatus,
  DataAccessLevel,
} from "@/api/skills";
import {
  useApproveExecutionPlan,
  useRejectExecutionPlan,
  useApproveSkillGlobally,
} from "@/hooks/useSkills";

// --- Config maps ---

const riskConfig: Record<RiskLevel, { label: string; classes: string; icon: typeof Shield }> = {
  low: { label: "Low Risk", classes: "bg-success/15 text-success border-success/25", icon: Shield },
  medium: { label: "Medium Risk", classes: "bg-warning/15 text-warning border-warning/25", icon: Shield },
  high: { label: "High Risk", classes: "bg-critical/15 text-critical border-critical/25", icon: AlertTriangle },
  critical: { label: "Critical Risk", classes: "bg-critical/20 text-critical border-critical/40", icon: AlertTriangle },
};

const stepStatusConfig: Record<StepStatus, { label: string; classes: string; icon: typeof Clock }> = {
  pending: { label: "Pending", classes: "text-slate-500", icon: Clock },
  running: { label: "Running", classes: "text-primary-400", icon: Loader2 },
  completed: { label: "Done", classes: "text-success", icon: CheckCircle2 },
  failed: { label: "Failed", classes: "text-critical", icon: XCircle },
  skipped: { label: "Skipped", classes: "text-slate-500", icon: SkipForward },
};

const dataAccessConfig: Record<DataAccessLevel, { label: string; classes: string }> = {
  public: { label: "PUBLIC", classes: "bg-success/10 text-success border-success/20" },
  internal: { label: "INTERNAL", classes: "bg-info/10 text-info border-info/20" },
  confidential: { label: "CONFIDENTIAL", classes: "bg-warning/10 text-warning border-warning/20" },
  restricted: { label: "RESTRICTED", classes: "bg-critical/10 text-critical border-critical/20" },
  regulated: { label: "REGULATED", classes: "bg-critical/15 text-critical border-critical/30" },
};

const agentConfig: Record<string, { label: string; color: string }> = {
  hunter: { label: "Hunter", color: "bg-emerald-500/15 text-emerald-400 border-emerald-500/25" },
  analyst: { label: "Analyst", color: "bg-blue-500/15 text-blue-400 border-blue-500/25" },
  strategist: { label: "Strategist", color: "bg-violet-500/15 text-violet-400 border-violet-500/25" },
  scribe: { label: "Scribe", color: "bg-amber-500/15 text-amber-400 border-amber-500/25" },
  operator: { label: "Operator", color: "bg-rose-500/15 text-rose-400 border-rose-500/25" },
  scout: { label: "Scout", color: "bg-cyan-500/15 text-cyan-400 border-cyan-500/25" },
};

// --- Sub-components ---

function DataAccessBadge({ level }: { level: DataAccessLevel }) {
  const config = dataAccessConfig[level];
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 text-[10px] font-semibold tracking-wider rounded border ${config.classes}`}>
      {config.label}
    </span>
  );
}

function AgentBadge({ agentId }: { agentId: string }) {
  const config = agentConfig[agentId] ?? { label: agentId, color: "bg-slate-500/15 text-slate-400 border-slate-500/25" };
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium rounded-full border ${config.color}`}>
      <Bot className="w-3 h-3" />
      {config.label}
    </span>
  );
}

function RiskBadge({ level }: { level: RiskLevel }) {
  const config = riskConfig[level];
  const Icon = config.icon;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full border ${config.classes}`}>
      <Icon className="w-3.5 h-3.5" />
      {config.label}
    </span>
  );
}

function StepStatusIcon({ status }: { status: StepStatus }) {
  const config = stepStatusConfig[status];
  const Icon = config.icon;
  return (
    <Icon
      className={`w-4 h-4 ${config.classes} ${status === "running" ? "animate-spin" : ""}`}
    />
  );
}

function formatDuration(ms: number): string {
  const seconds = Math.round(ms / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remaining = seconds % 60;
  return remaining > 0 ? `${minutes}m ${remaining}s` : `${minutes}m`;
}

interface StepRowProps {
  step: ExecutionStep;
  isLast: boolean;
}

function StepRow({ step, isLast }: StepRowProps) {
  return (
    <div className="relative flex gap-3">
      {/* Timeline connector */}
      <div className="flex flex-col items-center">
        <div className="flex items-center justify-center w-8 h-8 rounded-full bg-slate-800 border border-slate-700 z-10">
          <StepStatusIcon status={step.status} />
        </div>
        {!isLast && (
          <div className={`w-px flex-1 min-h-[24px] ${
            step.status === "completed" ? "bg-success/40" :
            step.status === "running" ? "bg-primary-400/40" :
            "bg-slate-700"
          }`} />
        )}
      </div>

      {/* Step content */}
      <div className="flex-1 pb-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-white">{step.skill_name || step.skill_path}</span>
          {step.agent_id && <AgentBadge agentId={step.agent_id} />}
        </div>

        <div className="mt-1.5 flex items-center gap-2 flex-wrap">
          {step.data_classes.map((dc) => (
            <DataAccessBadge key={dc} level={dc} />
          ))}
          <span className="text-xs text-slate-500 flex items-center gap-1">
            <Clock className="w-3 h-3" />
            ~{formatDuration(step.estimated_seconds * 1000)}
          </span>
        </div>

        {/* Output or error */}
        {step.status === "completed" && step.output_summary && (
          <p className="mt-1.5 text-xs text-slate-400 line-clamp-2">
            {step.output_summary}
          </p>
        )}
        {step.status === "failed" && step.error && (
          <p className="mt-1.5 text-xs text-critical line-clamp-2">
            {step.error}
          </p>
        )}
      </div>
    </div>
  );
}

// --- Main component ---

interface ExecutionPlanCardProps {
  plan: ExecutionPlan;
  /** Compact mode for inline chat display */
  compact?: boolean;
  /** Called after approve/reject mutation completes */
  onAction?: () => void;
  /** Show the "trust this skill always" checkbox (only for single-skill plans) */
  showTrustCheckbox?: boolean;
}

export function ExecutionPlanCard({
  plan,
  compact = false,
  onAction,
  showTrustCheckbox = false,
}: ExecutionPlanCardProps) {
  const [reasoningExpanded, setReasoningExpanded] = useState(false);
  const [trustAlways, setTrustAlways] = useState(false);

  const approveMutation = useApproveExecutionPlan();
  const rejectMutation = useRejectExecutionPlan();
  const trustMutation = useApproveSkillGlobally();

  const isPending = plan.status === "pending_approval";
  const isExecuting = plan.status === "executing";
  const isComplete = plan.status === "completed";
  const isFailed = plan.status === "failed";

  const completedSteps = plan.steps.filter((s) => s.status === "completed").length;
  const progress = plan.steps.length > 0 ? (completedSteps / plan.steps.length) * 100 : 0;

  function handleApprove() {
    approveMutation.mutate(plan.id, {
      onSuccess: () => {
        if (trustAlways && plan.steps.length === 1) {
          trustMutation.mutate(plan.steps[0].skill_id);
        }
        onAction?.();
      },
    });
  }

  function handleReject() {
    rejectMutation.mutate(plan.id, {
      onSuccess: () => onAction?.(),
    });
  }

  // Auto-approved flash: plan was approved by system (not user click) — has approved_at but user didn't click approve
  const autoApproved = (plan.status === "approved" || isExecuting) && !!plan.approved_at && !approveMutation.isSuccess;

  return (
    <div
      className={`relative bg-slate-800/50 border rounded-xl transition-all duration-300 ${
        autoApproved ? "animate-skill-auto-approve border-success/50 shadow-success/10 shadow-lg" :
        isPending ? "border-primary-500/30 shadow-primary-500/5 shadow-md" :
        isComplete ? "border-success/20" :
        isFailed ? "border-critical/30" :
        "border-slate-700"
      } ${compact ? "p-4" : "p-5"}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <Zap className="w-4 h-4 text-primary-400 flex-shrink-0" />
            <h3
              className={`font-semibold text-white truncate ${compact ? "text-sm" : "text-base"}`}
              style={{ fontFamily: "var(--font-display)" }}
            >
              {plan.task_description}
            </h3>
          </div>
          <div className="mt-1.5 flex items-center gap-2 flex-wrap">
            <RiskBadge level={plan.risk_level} />
            <span className="text-xs text-slate-500">
              {plan.steps.length} step{plan.steps.length !== 1 ? "s" : ""} · ~{formatDuration(plan.estimated_duration_ms)}
            </span>
          </div>
        </div>

        {/* Status indicator */}
        {isExecuting && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-primary-400 bg-primary-500/10 rounded-full border border-primary-500/20">
            <Loader2 className="w-3 h-3 animate-spin" />
            {completedSteps}/{plan.steps.length}
          </div>
        )}
        {isComplete && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-success bg-success/10 rounded-full border border-success/20">
            <CheckCircle2 className="w-3 h-3" />
            Done
          </div>
        )}
        {isFailed && (
          <div className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-critical bg-critical/10 rounded-full border border-critical/20">
            <XCircle className="w-3 h-3" />
            Failed
          </div>
        )}
      </div>

      {/* Progress bar (when executing) */}
      {isExecuting && (
        <div className="mt-3 h-1 bg-slate-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-primary-500 to-primary-400 rounded-full transition-all duration-500"
            style={{ width: `${progress}%` }}
          />
        </div>
      )}

      {/* Reasoning (expandable) */}
      {plan.reasoning && (
        <div className="mt-3">
          <button
            onClick={() => setReasoningExpanded(!reasoningExpanded)}
            className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 transition-colors"
          >
            {reasoningExpanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
            {reasoningExpanded ? "Hide reasoning" : "View reasoning"}
          </button>
          {reasoningExpanded && (
            <p className="mt-2 text-xs text-slate-400 leading-relaxed bg-slate-900/50 rounded-lg p-3 border border-slate-700/50">
              {plan.reasoning}
            </p>
          )}
        </div>
      )}

      {/* Steps timeline */}
      {!compact && (
        <div className="mt-4">
          {plan.steps.map((step, index) => (
            <StepRow
              key={step.step_number}
              step={step}
              isLast={index === plan.steps.length - 1}
            />
          ))}
        </div>
      )}

      {/* Compact: collapsed step summary */}
      {compact && plan.steps.length > 0 && (
        <div className="mt-3 flex items-center gap-1.5">
          {plan.steps.map((step) => (
            <div
              key={step.step_number}
              className={`w-2 h-2 rounded-full ${
                step.status === "completed" ? "bg-success" :
                step.status === "running" ? "bg-primary-400 animate-pulse" :
                step.status === "failed" ? "bg-critical" :
                "bg-slate-600"
              }`}
              title={`${step.skill_name}: ${stepStatusConfig[step.status].label}`}
            />
          ))}
        </div>
      )}

      {/* Action buttons (pending approval only) */}
      {isPending && (
        <div className="mt-4 pt-4 border-t border-slate-700/50">
          {showTrustCheckbox && plan.steps.length === 1 && (
            <label className="flex items-center gap-2 mb-3 cursor-pointer group">
              <input
                type="checkbox"
                checked={trustAlways}
                onChange={(e) => setTrustAlways(e.target.checked)}
                className="w-4 h-4 rounded border-slate-600 bg-slate-800 text-primary-500 focus:ring-primary-500/30 focus:ring-2 focus:ring-offset-0"
              />
              <span className="text-xs text-slate-400 group-hover:text-slate-300 transition-colors">
                Trust this skill always
              </span>
            </label>
          )}

          <div className="flex items-center gap-2">
            <button
              onClick={handleApprove}
              disabled={approveMutation.isPending}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-white bg-success/20 border border-success/30 rounded-lg hover:bg-success/30 transition-colors disabled:opacity-50"
            >
              {approveMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <CheckCircle2 className="w-4 h-4" />
              )}
              Approve
            </button>
            <button
              onClick={handleReject}
              disabled={rejectMutation.isPending}
              className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-slate-300 bg-critical/10 border border-critical/20 rounded-lg hover:bg-critical/20 hover:text-white transition-colors disabled:opacity-50"
            >
              {rejectMutation.isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <XCircle className="w-4 h-4" />
              )}
              Reject
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
