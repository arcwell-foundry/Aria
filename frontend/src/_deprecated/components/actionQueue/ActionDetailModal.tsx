import type { Action } from "@/api/actionQueue";
import {
  X,
  Check,
  Clock,
  Shield,
  Brain,
  Crosshair,
  PenLine,
  Settings,
  Compass,
  Mail,
  Database,
  Search,
  Calendar,
  UserPlus,
} from "lucide-react";
import { useState } from "react";

interface ActionDetailModalProps {
  action: Action | null;
  isOpen: boolean;
  onClose: () => void;
  onApprove?: (id: string) => void;
  onReject?: (id: string, reason?: string) => void;
}

const agentMeta: Record<string, { icon: typeof Brain; label: string; color: string }> = {
  scout: { icon: Compass, label: "Scout", color: "text-teal-400" },
  analyst: { icon: Brain, label: "Analyst", color: "text-interactive" },
  hunter: { icon: Crosshair, label: "Hunter", color: "text-orange-400" },
  operator: { icon: Settings, label: "Operator", color: "text-info" },
  scribe: { icon: PenLine, label: "Scribe", color: "text-success" },
  strategist: { icon: Shield, label: "Strategist", color: "text-rose-400" },
};

const typeMeta: Record<string, { icon: typeof Mail; label: string }> = {
  email_draft: { icon: Mail, label: "Email Draft" },
  crm_update: { icon: Database, label: "CRM Update" },
  research: { icon: Search, label: "Research" },
  meeting_prep: { icon: Calendar, label: "Meeting Prep" },
  lead_gen: { icon: UserPlus, label: "Lead Gen" },
};

const riskColors: Record<string, string> = {
  low: "text-green-400 bg-green-500/10",
  medium: "text-warning bg-warning/10",
  high: "text-orange-400 bg-orange-500/10",
  critical: "text-critical bg-critical/10",
};

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function ActionDetailModal({
  action,
  isOpen,
  onClose,
  onApprove,
  onReject,
}: ActionDetailModalProps) {
  const [rejectReason, setRejectReason] = useState("");
  const [showRejectInput, setShowRejectInput] = useState(false);

  if (!isOpen || !action) return null;

  const agent = agentMeta[action.agent] ?? agentMeta.scout;
  const actionType = typeMeta[action.action_type] ?? typeMeta.research;
  const AgentIcon = agent.icon;
  const TypeIcon = actionType.icon;
  const isPending = action.status === "pending";
  const riskClass = riskColors[action.risk_level] ?? riskColors.low;

  const handleReject = () => {
    onReject?.(action.id, rejectReason || undefined);
    setRejectReason("");
    setShowRejectInput(false);
  };

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/60 z-40" onClick={onClose} />

      {/* Panel */}
      <div className="fixed inset-y-0 right-0 w-full max-w-lg z-50 flex">
        <div className="w-full bg-slate-900 border-l border-slate-700 shadow-2xl overflow-y-auto">
          {/* Header */}
          <div className="sticky top-0 bg-slate-900/95 backdrop-blur border-b border-slate-700 px-6 py-4 flex items-center justify-between z-10">
            <h2 className="text-lg font-semibold text-white">Action Detail</h2>
            <button
              onClick={onClose}
              className="p-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          <div className="p-6 space-y-6">
            {/* Title + meta */}
            <div>
              <h3 className="text-xl font-semibold text-white mb-3">{action.title}</h3>
              <div className="flex flex-wrap gap-2">
                <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full ${agent.color} bg-slate-800`}>
                  <AgentIcon className="w-3.5 h-3.5" />
                  {agent.label}
                </span>
                <span className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-full text-slate-300 bg-slate-800">
                  <TypeIcon className="w-3.5 h-3.5" />
                  {actionType.label}
                </span>
                <span className={`inline-flex px-2.5 py-1 text-xs font-medium rounded-full ${riskClass}`}>
                  {action.risk_level.charAt(0).toUpperCase() + action.risk_level.slice(1)} Risk
                </span>
              </div>
            </div>

            {/* Description */}
            {action.description && (
              <div>
                <h4 className="text-sm font-medium text-slate-300 mb-2">Description</h4>
                <p className="text-sm text-slate-400 leading-relaxed">{action.description}</p>
              </div>
            )}

            {/* ARIA's Reasoning */}
            {action.reasoning && (
              <div className="bg-slate-800/50 border border-slate-700 rounded-lg p-4">
                <h4 className="text-sm font-medium text-slate-300 mb-2 flex items-center gap-2">
                  <Brain className="w-4 h-4 text-primary-400" />
                  ARIA&apos;s Reasoning
                </h4>
                <p className="text-sm text-slate-400 leading-relaxed">{action.reasoning}</p>
              </div>
            )}

            {/* Payload preview */}
            {action.payload && Object.keys(action.payload).length > 0 && (
              <div>
                <h4 className="text-sm font-medium text-slate-300 mb-2">Action Payload</h4>
                <pre className="bg-slate-800/50 border border-slate-700 rounded-lg p-4 text-xs text-slate-400 overflow-x-auto">
                  {JSON.stringify(action.payload, null, 2)}
                </pre>
              </div>
            )}

            {/* Result (for completed actions) */}
            {action.result && Object.keys(action.result).length > 0 && action.status === "completed" && (
              <div>
                <h4 className="text-sm font-medium text-slate-300 mb-2">Result</h4>
                <pre className="bg-slate-800/50 border border-slate-700 rounded-lg p-4 text-xs text-slate-400 overflow-x-auto">
                  {JSON.stringify(action.result, null, 2)}
                </pre>
              </div>
            )}

            {/* Timestamps */}
            <div className="space-y-2">
              <h4 className="text-sm font-medium text-slate-300">Timeline</h4>
              <div className="space-y-1.5">
                <div className="flex items-center gap-2 text-xs text-slate-400">
                  <Clock className="w-3.5 h-3.5 text-slate-500" />
                  Created: {formatDate(action.created_at)}
                </div>
                {action.approved_at && (
                  <div className="flex items-center gap-2 text-xs text-slate-400">
                    <Check className="w-3.5 h-3.5 text-green-400" />
                    Approved: {formatDate(action.approved_at)}
                  </div>
                )}
                {action.completed_at && (
                  <div className="flex items-center gap-2 text-xs text-slate-400">
                    <Check className="w-3.5 h-3.5 text-info" />
                    Completed: {formatDate(action.completed_at)}
                  </div>
                )}
              </div>
            </div>

            {/* Reject reason input */}
            {showRejectInput && (
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-2">
                  Rejection reason (optional)
                </label>
                <textarea
                  value={rejectReason}
                  onChange={(e) => setRejectReason(e.target.value)}
                  placeholder="Why are you rejecting this action?"
                  className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500"
                  rows={3}
                />
                <div className="flex gap-2 mt-3">
                  <button
                    onClick={handleReject}
                    className="px-4 py-2 bg-critical hover:brightness-110 text-white text-sm font-medium rounded-lg transition-colors"
                  >
                    Confirm Reject
                  </button>
                  <button
                    onClick={() => {
                      setShowRejectInput(false);
                      setRejectReason("");
                    }}
                    className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-300 text-sm font-medium rounded-lg transition-colors"
                  >
                    Cancel
                  </button>
                </div>
              </div>
            )}

            {/* Action buttons for pending */}
            {isPending && !showRejectInput && (
              <div className="flex gap-3 pt-2">
                {onApprove && (
                  <button
                    onClick={() => onApprove(action.id)}
                    className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-green-600 hover:bg-green-500 text-white font-medium rounded-lg transition-colors shadow-lg shadow-green-600/25"
                  >
                    <Check className="w-4 h-4" />
                    Approve
                  </button>
                )}
                {onReject && (
                  <button
                    onClick={() => setShowRejectInput(true)}
                    className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-slate-700 hover:bg-slate-600 text-slate-300 font-medium rounded-lg transition-colors"
                  >
                    <X className="w-4 h-4" />
                    Reject
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
