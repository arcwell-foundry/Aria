import { useState } from "react";
import {
  Zap,
  Loader2,
  CheckCircle2,
  XCircle,
  ChevronUp,
  Eye,
} from "lucide-react";
import type { StepStatus } from "@/api/skills";
import { useExecutionPlan } from "@/hooks/useSkills";
import { ExecutionPlanCard } from "./ExecutionPlanCard";
import { SkillSatisfactionButtons } from "./SkillSatisfactionButtons";

// --- Simple skill execution indicator (1 skill, auto-approved) ---

interface SimpleExecutionProps {
  skillName: string;
  status: StepStatus;
  resultSummary?: string | null;
  executionTimeMs?: number | null;
  executionId?: string | null;
}

function SimpleExecution({ skillName, status, resultSummary, executionTimeMs, executionId }: SimpleExecutionProps) {
  const [detailVisible, setDetailVisible] = useState(false);

  const isRunning = status === "running";
  const isDone = status === "completed";
  const isFailed = status === "failed";

  return (
    <div className="my-2">
      {/* Inline indicator */}
      <div
        className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium transition-all duration-300 ${
          isRunning
            ? "bg-primary-500/10 text-primary-400 border border-primary-500/20"
            : isDone
              ? "bg-success/10 text-success border border-success/20"
              : isFailed
                ? "bg-critical/10 text-critical border border-critical/20"
                : "bg-slate-800/50 text-slate-400 border border-slate-700"
        }`}
      >
        {isRunning && <Loader2 className="w-3 h-3 animate-spin" />}
        {isDone && <CheckCircle2 className="w-3 h-3" />}
        {isFailed && <XCircle className="w-3 h-3" />}
        {!isRunning && !isDone && !isFailed && <Zap className="w-3 h-3" />}

        <span>
          {isRunning ? `Running ${skillName}...` :
           isDone ? `Used ${skillName}` :
           isFailed ? `${skillName} failed` :
           skillName}
        </span>

        {executionTimeMs !== null && executionTimeMs !== undefined && isDone && (
          <span className="text-slate-500">{Math.round(executionTimeMs)}ms</span>
        )}

        {isDone && executionId && (
          <SkillSatisfactionButtons executionId={executionId} />
        )}
      </div>

      {/* "View what ARIA did" disclosure link */}
      {(isDone || isFailed) && resultSummary && (
        <div className="mt-1">
          <button
            onClick={() => setDetailVisible(!detailVisible)}
            className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 transition-colors"
          >
            {detailVisible ? (
              <ChevronUp className="w-3 h-3" />
            ) : (
              <Eye className="w-3 h-3" />
            )}
            {detailVisible ? "Hide details" : "View what ARIA did"}
          </button>
          {detailVisible && (
            <div className="mt-1.5 text-xs text-slate-400 bg-slate-900/50 rounded-lg p-3 border border-slate-700/50 leading-relaxed">
              {resultSummary}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// --- Multi-step execution with plan card ---

interface PlanExecutionProps {
  planId: string;
  onAction?: () => void;
}

function PlanExecution({ planId, onAction }: PlanExecutionProps) {
  const { data: plan, isLoading } = useExecutionPlan(planId);

  if (isLoading || !plan) {
    return (
      <div className="my-2 flex items-center gap-2 text-xs text-slate-500">
        <Loader2 className="w-3 h-3 animate-spin" />
        Loading execution plan...
      </div>
    );
  }

  return (
    <div className="my-3">
      <ExecutionPlanCard
        plan={plan}
        compact={plan.status !== "pending_approval"}
        onAction={onAction}
        showTrustCheckbox={plan.steps.length === 1}
      />
    </div>
  );
}

// --- Main component ---

export interface SkillExecutionData {
  type: "simple" | "plan";
  /** For simple: the skill being executed */
  skillName?: string;
  status?: StepStatus;
  resultSummary?: string | null;
  executionTimeMs?: number | null;
  executionId?: string | null;
  /** For plan: the plan ID to fetch and render */
  planId?: string;
}

interface SkillExecutionInlineProps {
  execution: SkillExecutionData;
  onAction?: () => void;
}

export function SkillExecutionInline({ execution, onAction }: SkillExecutionInlineProps) {
  if (execution.type === "simple" && execution.skillName) {
    return (
      <SimpleExecution
        skillName={execution.skillName}
        status={execution.status ?? "pending"}
        resultSummary={execution.resultSummary}
        executionTimeMs={execution.executionTimeMs}
        executionId={execution.executionId}
      />
    );
  }

  if (execution.type === "plan" && execution.planId) {
    return <PlanExecution planId={execution.planId} onAction={onAction} />;
  }

  return null;
}
