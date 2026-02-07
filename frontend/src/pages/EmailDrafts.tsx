// frontend/src/pages/EmailDrafts.tsx
import { useState } from "react";
import type { EmailDraftListItem, EmailDraftStatus, CreateEmailDraftRequest, UpdateEmailDraftRequest, RegenerateDraftRequest } from "@/api/drafts";
import { DashboardLayout } from "@/components/DashboardLayout";
import {
  EmptyDrafts,
  DraftCard,
  DraftComposeModal,
  DraftDetailModal,
  DraftSkeleton,
} from "@/components/drafts";
import {
  useDrafts,
  useDraft,
  useCreateDraft,
  useUpdateDraft,
  useDeleteDraft,
  useRegenerateDraft,
  useSendDraft,
} from "@/hooks/useDrafts";
import { HelpTooltip } from "@/components/HelpTooltip";

type StatusFilter = EmailDraftStatus | "all";

const statusFilters: { value: StatusFilter; label: string }[] = [
  { value: "all", label: "All Drafts" },
  { value: "draft", label: "Pending" },
  { value: "sent", label: "Sent" },
  { value: "failed", label: "Failed" },
];

export function EmailDraftsPage() {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [isComposeOpen, setIsComposeOpen] = useState(false);
  const [selectedDraftId, setSelectedDraftId] = useState<string | null>(null);

  // Queries
  const { data: drafts, isLoading, error } = useDrafts(
    statusFilter === "all" ? undefined : statusFilter
  );

  // Get selected draft details when needed
  const { data: selectedDraft } = useDraft(selectedDraftId || "");

  // Mutations
  const createDraft = useCreateDraft();
  const updateDraft = useUpdateDraft();
  const deleteDraft = useDeleteDraft();
  const regenerateDraft = useRegenerateDraft();
  const sendDraft = useSendDraft();

  const handleCreate = (data: CreateEmailDraftRequest) => {
    createDraft.mutate(data, {
      onSuccess: (newDraft) => {
        setIsComposeOpen(false);
        setSelectedDraftId(newDraft.id);
      },
    });
  };

  const handleView = (draft: EmailDraftListItem) => {
    setSelectedDraftId(draft.id);
  };

  const handleDelete = (draftId: string) => {
    if (confirm("Are you sure you want to delete this draft?")) {
      deleteDraft.mutate(draftId, {
        onSuccess: () => {
          if (selectedDraftId === draftId) {
            setSelectedDraftId(null);
          }
        },
      });
    }
  };

  const handleSave = (draftId: string, data: UpdateEmailDraftRequest) => {
    updateDraft.mutate({ draftId, data });
  };

  const handleRegenerate = (draftId: string, data?: RegenerateDraftRequest) => {
    regenerateDraft.mutate({ draftId, data });
  };

  const handleSend = (draftId: string) => {
    sendDraft.mutate(draftId);
  };

  const handleCloseDetail = () => {
    setSelectedDraftId(null);
  };

  return (
    <DashboardLayout>
      <div className="relative">
        {/* Background pattern */}
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-slate-800 via-slate-900 to-slate-900 pointer-events-none" />

        <div className="relative max-w-6xl mx-auto px-4 py-8 lg:px-8">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-3xl font-bold text-white">Email Drafts</h1>
                <HelpTooltip content="AI-drafted emails from ARIA. Review, edit, and send from here." placement="right" />
              </div>
              <p className="mt-1 text-slate-400">
                AI-powered emails crafted in your style
              </p>
            </div>

            <button
              onClick={() => setIsComposeOpen(true)}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-gradient-to-r from-primary-600 to-primary-500 hover:from-primary-500 hover:to-primary-400 text-white font-medium rounded-xl transition-all duration-200 shadow-lg shadow-primary-600/25 hover:shadow-primary-500/40"
            >
              <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
              </svg>
              Compose
            </button>
          </div>

          {/* Filter tabs */}
          <div className="flex items-center gap-2 mb-8 overflow-x-auto pb-2">
            {statusFilters.map((filter) => (
              <button
                key={filter.value}
                onClick={() => setStatusFilter(filter.value)}
                className={`px-4 py-2 text-sm font-medium rounded-xl whitespace-nowrap transition-all duration-200 ${
                  statusFilter === filter.value
                    ? "bg-primary-600/20 text-primary-400 border border-primary-500/30"
                    : "text-slate-400 hover:text-white hover:bg-slate-800/50"
                }`}
              >
                {filter.label}
              </button>
            ))}
          </div>

          {/* Error state */}
          {error && (
            <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-4 mb-6">
              <p className="text-red-400">Failed to load drafts. Please try again.</p>
            </div>
          )}

          {/* Loading state */}
          {isLoading && (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {[1, 2, 3, 4, 5, 6].map((i) => (
                <DraftSkeleton key={i} />
              ))}
            </div>
          )}

          {/* Empty state */}
          {!isLoading && drafts?.length === 0 && (
            <EmptyDrafts
              onCreateClick={() => setIsComposeOpen(true)}
              hasFilter={statusFilter !== "all"}
            />
          )}

          {/* Drafts grid */}
          {!isLoading && drafts && drafts.length > 0 && (
            <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
              {drafts.map((draft, index) => (
                <div
                  key={draft.id}
                  className="animate-in fade-in slide-in-from-bottom-4"
                  style={{
                    animationDelay: `${index * 50}ms`,
                    animationFillMode: "both",
                  }}
                >
                  <DraftCard
                    draft={draft}
                    onView={() => handleView(draft)}
                    onDelete={() => handleDelete(draft.id)}
                  />
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Compose Modal */}
        <DraftComposeModal
          isOpen={isComposeOpen}
          onClose={() => setIsComposeOpen(false)}
          onSubmit={handleCreate}
          isLoading={createDraft.isPending}
        />

        {/* Detail Modal */}
        <DraftDetailModal
          draft={selectedDraft || null}
          isOpen={selectedDraftId !== null}
          onClose={handleCloseDetail}
          onSave={handleSave}
          onRegenerate={handleRegenerate}
          onSend={handleSend}
          isSaving={updateDraft.isPending}
          isRegenerating={regenerateDraft.isPending}
          isSending={sendDraft.isPending}
        />
      </div>
    </DashboardLayout>
  );
}
