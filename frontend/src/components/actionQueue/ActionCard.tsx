import type { Action, ActionAgent, RiskLevel } from "@/api/actionQueue";
import {
  Search,
  Mail,
  Database,
  Calendar,
  UserPlus,
  Bot,
  Shield,
  Crosshair,
  PenLine,
  Settings,
  Compass,
  Brain,
  Check,
  X,
  ChevronRight,
  Clock,
} from "lucide-react";

interface ActionCardProps {
  action: Action;
  isSelected?: boolean;
  onSelect?: (id: string) => void;
  onApprove?: (id: string) => void;
  onReject?: (id: string) => void;
  onViewDetail?: (id: string) => void;
}

const agentConfig: Record<ActionAgent, { icon: typeof Bot; label: string; color: string }> = {
  scout: { icon: Compass, label: "Scout", color: "text-teal-400" },
  analyst: { icon: Brain, label: "Analyst", color: "text-interactive" },
  hunter: { icon: Crosshair, label: "Hunter", color: "text-orange-400" },
  operator: { icon: Settings, label: "Operator", color: "text-info" },
  scribe: { icon: PenLine, label: "Scribe", color: "text-success" },
  strategist: { icon: Shield, label: "Strategist", color: "text-rose-400" },
};

const actionTypeConfig: Record<string, { icon: typeof Mail; label: string }> = {
  email_draft: { icon: Mail, label: "Email Draft" },
  crm_update: { icon: Database, label: "CRM Update" },
  research: { icon: Search, label: "Research" },
  meeting_prep: { icon: Calendar, label: "Meeting Prep" },
  lead_gen: { icon: UserPlus, label: "Lead Gen" },
};

const riskConfig: Record<RiskLevel, { bg: string; text: string; label: string }> = {
  low: { bg: "bg-green-500/10", text: "text-green-400", label: "Low" },
  medium: { bg: "bg-warning/10", text: "text-warning", label: "Medium" },
  high: { bg: "bg-orange-500/10", text: "text-orange-400", label: "High" },
  critical: { bg: "bg-critical/10", text: "text-critical", label: "Critical" },
};

const statusConfig: Record<string, { bg: string; text: string; label: string }> = {
  pending: { bg: "bg-warning/10", text: "text-warning", label: "Pending" },
  approved: { bg: "bg-info/10", text: "text-info", label: "Approved" },
  auto_approved: { bg: "bg-teal-500/10", text: "text-teal-400", label: "Auto-Approved" },
  executing: { bg: "bg-interactive/10", text: "text-interactive", label: "Executing" },
  completed: { bg: "bg-green-500/10", text: "text-green-400", label: "Completed" },
  rejected: { bg: "bg-critical/10", text: "text-critical", label: "Rejected" },
  failed: { bg: "bg-critical/10", text: "text-critical", label: "Failed" },
};

function formatRelativeTime(dateString: string): string {
  const now = new Date();
  const date = new Date(dateString);
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMs / 3600000);
  const diffDays = Math.floor(diffMs / 86400000);

  if (diffMins < 1) return "Just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  return `${diffDays}d ago`;
}

export function ActionCard({
  action,
  isSelected = false,
  onSelect,
  onApprove,
  onReject,
  onViewDetail,
}: ActionCardProps) {
  const agent = agentConfig[action.agent] ?? agentConfig.scout;
  const actionType = actionTypeConfig[action.action_type] ?? actionTypeConfig.research;
  const risk = riskConfig[action.risk_level];
  const status = statusConfig[action.status] ?? statusConfig.pending;
  const isPending = action.status === "pending";
  const AgentIcon = agent.icon;
  const TypeIcon = actionType.icon;

  return (
    <div
      className={`group relative bg-slate-800/50 border rounded-xl p-4 transition-all duration-200 hover:bg-slate-800/80 hover:shadow-lg hover:shadow-slate-900/50 ${
        isSelected
          ? "border-primary-500/50 bg-primary-500/5"
          : "border-slate-700 hover:border-slate-600"
      }`}
    >
      <div className="flex items-start gap-3">
        {/* Selection checkbox for pending actions */}
        {isPending && onSelect && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onSelect(action.id);
            }}
            className={`mt-0.5 flex-shrink-0 w-5 h-5 rounded border-2 flex items-center justify-center transition-colors ${
              isSelected
                ? "bg-primary-600 border-primary-600"
                : "border-slate-600 hover:border-slate-400"
            }`}
          >
            {isSelected && <Check className="w-3 h-3 text-white" />}
          </button>
        )}

        {/* Agent icon */}
        <div className={`flex-shrink-0 mt-0.5 ${agent.color}`}>
          <AgentIcon className="w-5 h-5" />
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <span className={`text-xs font-medium ${agent.color}`}>{agent.label}</span>
                <span className="text-slate-600">&middot;</span>
                <span className="text-xs text-slate-500 flex items-center gap-1">
                  <TypeIcon className="w-3 h-3" />
                  {actionType.label}
                </span>
              </div>
              <h3 className="text-sm font-semibold text-white group-hover:text-primary-400 transition-colors truncate">
                {action.title}
              </h3>
              {action.description && (
                <p className="mt-1 text-xs text-slate-400 line-clamp-2">{action.description}</p>
              )}
            </div>

            {/* Badges column */}
            <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
              <span className={`inline-flex px-2 py-0.5 text-xs font-medium rounded-full ${risk.bg} ${risk.text}`}>
                {risk.label}
              </span>
              <span className={`inline-flex px-2 py-0.5 text-xs font-medium rounded-full ${status.bg} ${status.text}`}>
                {status.label}
              </span>
            </div>
          </div>

          {/* Footer: timestamp + actions */}
          <div className="mt-3 flex items-center justify-between">
            <span className="text-xs text-slate-500 flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {formatRelativeTime(action.created_at)}
            </span>

            <div className="flex items-center gap-1">
              {/* Why link (show reasoning) */}
              {action.reasoning && onViewDetail && (
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onViewDetail(action.id);
                  }}
                  className="text-xs text-slate-500 hover:text-primary-400 transition-colors flex items-center gap-0.5"
                >
                  Why?
                  <ChevronRight className="w-3 h-3" />
                </button>
              )}

              {/* Approve / Reject buttons for pending */}
              {isPending && (
                <div className="flex items-center gap-1 ml-2">
                  {onApprove && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onApprove(action.id);
                      }}
                      className="p-1.5 text-slate-400 hover:text-green-400 hover:bg-green-500/10 rounded-lg transition-colors"
                      title="Approve action"
                    >
                      <Check className="w-4 h-4" />
                    </button>
                  )}
                  {onReject && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onReject(action.id);
                      }}
                      className="p-1.5 text-slate-400 hover:text-critical hover:bg-critical/10 rounded-lg transition-colors"
                      title="Reject action"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
