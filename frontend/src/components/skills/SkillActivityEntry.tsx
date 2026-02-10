import { useState } from "react";
import {
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  ChevronDown,
  ChevronUp,
  Bot,
  Zap,
} from "lucide-react";
import type { ActivityItem } from "@/api/activity";

// Agent color mapping (same as ExecutionPlanCard)
const agentColors: Record<string, string> = {
  hunter: "from-emerald-500 to-emerald-600",
  analyst: "from-blue-500 to-blue-600",
  strategist: "from-violet-500 to-violet-600",
  scribe: "from-amber-500 to-amber-600",
  operator: "from-rose-500 to-rose-600",
  scout: "from-cyan-500 to-cyan-600",
};

function AgentIcon({ agent }: { agent: string | null }) {
  const gradient = agent ? agentColors[agent] ?? "from-slate-500 to-slate-600" : "from-primary-500 to-primary-600";
  return (
    <div className={`w-8 h-8 rounded-full bg-gradient-to-br ${gradient} flex items-center justify-center flex-shrink-0`}>
      {agent ? (
        <Bot className="w-4 h-4 text-white" />
      ) : (
        <Zap className="w-4 h-4 text-white" />
      )}
    </div>
  );
}

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60_000);
  const diffHours = Math.floor(diffMins / 60);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

interface SkillActivityEntryProps {
  activity: ActivityItem;
  onClick?: () => void;
}

export function SkillActivityEntry({ activity, onClick }: SkillActivityEntryProps) {
  const [expanded, setExpanded] = useState(false);

  const isSkillExecution = activity.activity_type === "skill_execution" ||
    activity.activity_type === "skill_step_completed" ||
    activity.activity_type === "skill_step_failed";

  const metadata = activity.metadata as Record<string, unknown>;
  const skillName = (metadata.skill_name as string) ?? null;
  const stepNumber = (metadata.step_number as number) ?? null;
  const executionTimeMs = (metadata.execution_time_ms as number) ?? null;
  const planId = (metadata.plan_id as string) ?? null;

  const isRunning = activity.activity_type === "skill_execution" && !metadata.completed;
  const isFailed = activity.activity_type === "skill_step_failed";

  return (
    <div
      className={`group bg-slate-800/50 border border-slate-700 rounded-xl p-4 transition-all duration-200 hover:bg-slate-800/80 hover:border-slate-600 ${
        onClick ? "cursor-pointer" : ""
      }`}
      onClick={onClick}
    >
      <div className="flex items-start gap-3">
        <AgentIcon agent={activity.agent} />

        <div className="flex-1 min-w-0">
          {/* Title row */}
          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-sm font-medium text-white truncate">
              {activity.title}
            </span>
            {isSkillExecution && skillName && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-semibold tracking-wider text-primary-400 bg-primary-500/10 rounded border border-primary-500/20">
                <Zap className="w-2.5 h-2.5" />
                {skillName}
              </span>
            )}
            {isRunning && (
              <Loader2 className="w-3.5 h-3.5 text-primary-400 animate-spin flex-shrink-0" />
            )}
            {isFailed && (
              <XCircle className="w-3.5 h-3.5 text-critical flex-shrink-0" />
            )}
          </div>

          {/* Description */}
          {activity.description && (
            <p className={`mt-1 text-xs text-slate-400 ${expanded ? "" : "line-clamp-2"}`}>
              {activity.description}
            </p>
          )}

          {/* Meta row */}
          <div className="mt-2 flex items-center gap-3 text-xs text-slate-500">
            <span className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {formatRelativeTime(activity.created_at)}
            </span>
            {stepNumber !== null && (
              <span>Step {stepNumber}</span>
            )}
            {executionTimeMs !== null && (
              <span>{Math.round(executionTimeMs)}ms</span>
            )}
            {activity.confidence > 0 && (
              <span className="flex items-center gap-1">
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    activity.confidence >= 0.8 ? "bg-success" :
                    activity.confidence >= 0.5 ? "bg-warning" :
                    "bg-critical"
                  }`}
                />
                {Math.round(activity.confidence * 100)}%
              </span>
            )}
          </div>

          {/* Expandable detail */}
          {(activity.reasoning || planId) && (
            <div className="mt-2">
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setExpanded(!expanded);
                }}
                className="flex items-center gap-1 text-xs text-slate-500 hover:text-slate-300 transition-colors"
              >
                {expanded ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                {expanded ? "Less" : "Details"}
              </button>
              {expanded && (
                <div className="mt-2 space-y-2">
                  {activity.reasoning && (
                    <p className="text-xs text-slate-400 bg-slate-900/50 rounded-lg p-2.5 border border-slate-700/50 leading-relaxed">
                      {activity.reasoning}
                    </p>
                  )}
                  {planId && (
                    <p className="text-xs text-slate-500">
                      Plan: <span className="font-mono text-slate-400">{planId.slice(0, 8)}</span>
                    </p>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Status icon (right side) */}
        <div className="flex-shrink-0 mt-0.5">
          {activity.activity_type === "skill_step_completed" && (
            <CheckCircle2 className="w-4 h-4 text-success" />
          )}
        </div>
      </div>
    </div>
  );
}
