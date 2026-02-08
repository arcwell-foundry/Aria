import { useState } from "react";
import {
  CheckCircle2,
  XCircle,
  Bookmark,
  Search,
  ChevronDown,
  ChevronUp,
  Building2,
  Users,
} from "lucide-react";
import { useDiscoveredLeads, useReviewLead } from "@/hooks/useLeadGeneration";
import type { DiscoveredLead, ReviewStatus } from "@/api/leadGeneration";
import { ScoreBreakdown } from "./ScoreBreakdown";

type FilterTab = "all" | "pending" | "saved";

function scoreColor(score: number): string {
  if (score >= 70) return "text-success bg-success/10 border-success/20";
  if (score >= 40) return "text-warning bg-warning/10 border-warning/20";
  return "text-critical bg-critical/10 border-critical/20";
}

function statusBadge(status: ReviewStatus) {
  switch (status) {
    case "approved":
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-success/10 text-success border border-success/20">
          <CheckCircle2 className="w-3 h-3" />
          Approved
        </span>
      );
    case "rejected":
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-critical/10 text-critical border border-critical/20">
          <XCircle className="w-3 h-3" />
          Rejected
        </span>
      );
    case "saved":
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-warning/10 text-warning border border-warning/20">
          <Bookmark className="w-3 h-3" />
          Saved
        </span>
      );
    default:
      return null;
  }
}

function SkeletonCard() {
  return (
    <div className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-5 animate-pulse">
      <div className="flex items-start gap-4 mb-4">
        <div className="w-10 h-10 bg-slate-700 rounded-lg" />
        <div className="flex-1">
          <div className="h-5 bg-slate-700 rounded w-3/4 mb-2" />
          <div className="h-4 bg-slate-700 rounded w-1/2" />
        </div>
        <div className="w-10 h-10 bg-slate-700 rounded-full" />
      </div>
      <div className="flex gap-2 mb-3">
        <div className="h-5 bg-slate-700 rounded-full w-16" />
        <div className="h-5 bg-slate-700 rounded-full w-20" />
      </div>
      <div className="h-4 bg-slate-700 rounded w-2/3" />
    </div>
  );
}

function getContactName(contact: Record<string, unknown>): string {
  if (typeof contact.name === "string") return contact.name;
  if (typeof contact.first_name === "string" && typeof contact.last_name === "string") {
    return `${contact.first_name} ${contact.last_name}`;
  }
  if (typeof contact.email === "string") return contact.email;
  return "Unknown contact";
}

interface LeadCardItemProps {
  lead: DiscoveredLead;
  isExpanded: boolean;
  isSelected: boolean;
  onToggleExpand: () => void;
  onToggleSelect: () => void;
  onAction: (leadId: string, action: ReviewStatus) => void;
  isActioning: boolean;
}

function LeadCardItem({
  lead,
  isExpanded,
  isSelected,
  onToggleExpand,
  onToggleSelect,
  onAction,
  isActioning,
}: LeadCardItemProps) {
  return (
    <div
      className={`bg-slate-800/50 border rounded-xl p-5 transition-all duration-200 ${
        isSelected
          ? "border-primary-500/50 ring-1 ring-primary-500/20"
          : "border-slate-700/50 hover:border-slate-600/50"
      }`}
    >
      {/* Header row: checkbox + company + score */}
      <div className="flex items-start gap-3">
        <button
          onClick={(e) => {
            e.stopPropagation();
            onToggleSelect();
          }}
          className={`mt-1 w-5 h-5 flex-shrink-0 rounded border-2 transition-all duration-200 flex items-center justify-center ${
            isSelected
              ? "bg-primary-500 border-primary-500"
              : "border-slate-600 hover:border-slate-500"
          }`}
        >
          {isSelected && (
            <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
            </svg>
          )}
        </button>

        <div className="flex-1 min-w-0 cursor-pointer" onClick={onToggleExpand}>
          <div className="flex items-start justify-between gap-3">
            <div className="flex items-center gap-3 min-w-0">
              <div className="flex-shrink-0 w-10 h-10 bg-gradient-to-br from-slate-700 to-slate-800 rounded-lg flex items-center justify-center border border-slate-600/50">
                <Building2 className="w-5 h-5 text-slate-400" />
              </div>
              <div className="min-w-0">
                <h3 className="text-base font-semibold text-white truncate">
                  {lead.company_name}
                </h3>
                {lead.review_status !== "pending" && (
                  <div className="mt-1">{statusBadge(lead.review_status)}</div>
                )}
              </div>
            </div>

            {/* Fit score circle */}
            <div
              className={`flex-shrink-0 w-11 h-11 rounded-full border flex items-center justify-center ${scoreColor(lead.fit_score)}`}
            >
              <span className="text-sm font-bold">{lead.fit_score}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Signals */}
      {lead.signals.length > 0 && (
        <div className="flex flex-wrap gap-1.5 mt-3 ml-8">
          {lead.signals.slice(0, 4).map((signal) => (
            <span
              key={signal}
              className="px-2 py-0.5 text-xs rounded-full bg-slate-700/50 text-slate-400"
            >
              {signal}
            </span>
          ))}
          {lead.signals.length > 4 && (
            <span className="px-2 py-0.5 text-xs rounded-full bg-slate-700/50 text-slate-500">
              +{lead.signals.length - 4}
            </span>
          )}
        </div>
      )}

      {/* Contacts preview */}
      {lead.contacts.length > 0 && (
        <div className="flex items-center gap-2 mt-3 ml-8 text-sm text-slate-400">
          <Users className="w-4 h-4 text-slate-500 flex-shrink-0" />
          <span className="truncate">
            {lead.contacts.slice(0, 2).map(getContactName).join(", ")}
            {lead.contacts.length > 2 && ` +${lead.contacts.length - 2}`}
          </span>
        </div>
      )}

      {/* Expand toggle */}
      <button
        onClick={onToggleExpand}
        className="flex items-center gap-1 mt-3 ml-8 text-xs text-slate-500 hover:text-slate-300 transition-colors"
      >
        {isExpanded ? (
          <>
            <ChevronUp className="w-3.5 h-3.5" />
            Hide breakdown
          </>
        ) : (
          <>
            <ChevronDown className="w-3.5 h-3.5" />
            Show breakdown
          </>
        )}
      </button>

      {/* Expanded score breakdown */}
      {isExpanded && lead.score_breakdown && (
        <div className="mt-4 ml-8">
          <ScoreBreakdown breakdown={lead.score_breakdown} />
        </div>
      )}

      {/* Action buttons */}
      {lead.review_status === "pending" && (
        <div className="flex items-center gap-2 mt-4 ml-8">
          <button
            onClick={() => onAction(lead.id, "approved")}
            disabled={isActioning}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-success hover:brightness-110 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <CheckCircle2 className="w-4 h-4" />
            Approve
          </button>
          <button
            onClick={() => onAction(lead.id, "rejected")}
            disabled={isActioning}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-critical hover:brightness-110 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <XCircle className="w-4 h-4" />
            Reject
          </button>
          <button
            onClick={() => onAction(lead.id, "saved")}
            disabled={isActioning}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium bg-warning hover:brightness-110 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <Bookmark className="w-4 h-4" />
            Save
          </button>
        </div>
      )}
    </div>
  );
}

export function LeadReviewQueue() {
  const [statusFilter, setStatusFilter] = useState<FilterTab>("all");
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const queryFilter: ReviewStatus | undefined =
    statusFilter === "all" ? undefined : statusFilter;

  const { data: leads, isLoading, error } = useDiscoveredLeads(queryFilter);
  const reviewMutation = useReviewLead();

  const handleAction = (leadId: string, action: ReviewStatus) => {
    reviewMutation.mutate({ leadId, action });
  };

  const handleBatchApprove = () => {
    for (const leadId of selectedIds) {
      reviewMutation.mutate({ leadId, action: "approved" });
    }
    setSelectedIds(new Set());
  };

  const toggleSelect = (leadId: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(leadId)) {
        next.delete(leadId);
      } else {
        next.add(leadId);
      }
      return next;
    });
  };

  const filterTabs: { key: FilterTab; label: string }[] = [
    { key: "all", label: "All" },
    { key: "pending", label: "Pending" },
    { key: "saved", label: "Saved" },
  ];

  if (error) {
    return (
      <div className="text-center py-12">
        <p className="text-critical">Failed to load leads. Please try again.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Filter tabs */}
      <div className="flex items-center gap-2">
        {filterTabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => {
              setStatusFilter(tab.key);
              setSelectedIds(new Set());
            }}
            className={`px-3 py-1.5 rounded-full text-sm font-medium transition-colors ${
              statusFilter === tab.key
                ? "bg-slate-700 text-white"
                : "bg-slate-800/50 text-slate-400 hover:text-slate-300 hover:bg-slate-700/50"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Loading state */}
      {isLoading && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <SkeletonCard key={i} />
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isLoading && leads && leads.length === 0 && (
        <div className="flex flex-col items-center justify-center py-16 text-center">
          <div className="w-14 h-14 bg-slate-800/50 border border-slate-700/50 rounded-xl flex items-center justify-center mb-4">
            <Search className="w-7 h-7 text-slate-500" />
          </div>
          <h3 className="text-lg font-semibold text-white mb-2">No leads to review</h3>
          <p className="text-sm text-slate-400 max-w-sm">
            Define your ICP and discover leads to review them here.
          </p>
        </div>
      )}

      {/* Lead cards grid */}
      {!isLoading && leads && leads.length > 0 && (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {leads.map((lead) => (
            <LeadCardItem
              key={lead.id}
              lead={lead}
              isExpanded={expandedId === lead.id}
              isSelected={selectedIds.has(lead.id)}
              onToggleExpand={() =>
                setExpandedId(expandedId === lead.id ? null : lead.id)
              }
              onToggleSelect={() => toggleSelect(lead.id)}
              onAction={handleAction}
              isActioning={reviewMutation.isPending}
            />
          ))}
        </div>
      )}

      {/* Batch approve floating bar */}
      {selectedIds.size > 0 && (
        <div className="fixed bottom-6 left-1/2 -translate-x-1/2 z-50">
          <div className="flex items-center gap-4 px-5 py-3 bg-slate-800 border border-slate-700 rounded-xl shadow-2xl shadow-black/40">
            <span className="text-sm text-slate-300">
              {selectedIds.size} lead{selectedIds.size > 1 ? "s" : ""} selected
            </span>
            <button
              onClick={handleBatchApprove}
              disabled={reviewMutation.isPending}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium bg-success hover:brightness-110 text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <CheckCircle2 className="w-4 h-4" />
              Approve Selected
            </button>
            <button
              onClick={() => setSelectedIds(new Set())}
              className="text-sm text-slate-400 hover:text-slate-300 transition-colors"
            >
              Clear
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
