import type { ReactNode } from "react";
import type { EmailDraftListItem } from "@/api/drafts";
import { StyleMatchIndicator } from "./StyleMatchIndicator";

interface DraftCardProps {
  draft: EmailDraftListItem;
  onView: () => void;
  onDelete: () => void;
}

const purposeLabels: Record<string, string> = {
  intro: "Introduction",
  follow_up: "Follow Up",
  proposal: "Proposal",
  thank_you: "Thank You",
  check_in: "Check In",
  other: "Other",
};

const toneLabels: Record<string, { label: string; color: string }> = {
  formal: { label: "Formal", color: "bg-blue-500/20 text-blue-400 border-blue-500/30" },
  friendly: { label: "Friendly", color: "bg-emerald-500/20 text-emerald-400 border-emerald-500/30" },
  urgent: { label: "Urgent", color: "bg-amber-500/20 text-amber-400 border-amber-500/30" },
};

const statusConfig: Record<string, { label: string; color: string; icon: ReactNode }> = {
  draft: {
    label: "Draft",
    color: "bg-slate-500/20 text-slate-400",
    icon: (
      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
      </svg>
    ),
  },
  sent: {
    label: "Sent",
    color: "bg-emerald-500/20 text-emerald-400",
    icon: (
      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
      </svg>
    ),
  },
  failed: {
    label: "Failed",
    color: "bg-red-500/20 text-red-400",
    icon: (
      <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
      </svg>
    ),
  },
};

export function DraftCard({ draft, onView, onDelete }: DraftCardProps) {
  const status = statusConfig[draft.status];
  const tone = toneLabels[draft.tone];
  const formattedDate = new Date(draft.created_at).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });

  return (
    <div
      onClick={onView}
      className="group relative bg-slate-800/50 hover:bg-slate-800/80 border border-slate-700/50 hover:border-slate-600/50 rounded-2xl p-5 cursor-pointer transition-all duration-300 hover:shadow-xl hover:shadow-black/20 hover:-translate-y-0.5"
    >
      {/* Subtle gradient overlay on hover */}
      <div className="absolute inset-0 bg-gradient-to-br from-primary-500/5 to-transparent opacity-0 group-hover:opacity-100 rounded-2xl transition-opacity duration-300 pointer-events-none" />

      <div className="relative">
        {/* Header row */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="flex-1 min-w-0">
            <h3 className="font-semibold text-white truncate group-hover:text-primary-300 transition-colors">
              {draft.subject || "No subject"}
            </h3>
            <p className="text-sm text-slate-400 truncate mt-0.5">
              To: {draft.recipient_name || draft.recipient_email}
            </p>
          </div>

          {/* Status badge */}
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium rounded-lg ${status.color}`}>
            {status.icon}
            {status.label}
          </span>
        </div>

        {/* Tags row */}
        <div className="flex items-center gap-2 mb-4">
          <span className="px-2.5 py-1 text-xs font-medium bg-slate-700/50 text-slate-300 rounded-lg">
            {purposeLabels[draft.purpose]}
          </span>
          <span className={`px-2.5 py-1 text-xs font-medium rounded-lg border ${tone.color}`}>
            {tone.label}
          </span>
        </div>

        {/* Footer row */}
        <div className="flex items-center justify-between">
          {/* Style match score */}
          {draft.style_match_score !== undefined && (
            <StyleMatchIndicator score={draft.style_match_score} size="sm" />
          )}
          {draft.style_match_score === undefined && <div />}

          <div className="flex items-center gap-3">
            <span className="text-xs text-slate-500">{formattedDate}</span>

            {/* Delete button - appears on hover */}
            <button
              onClick={(e) => {
                e.stopPropagation();
                onDelete();
              }}
              className="opacity-0 group-hover:opacity-100 p-1.5 text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-all duration-200"
              title="Delete draft"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
