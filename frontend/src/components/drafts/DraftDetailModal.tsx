// frontend/src/components/drafts/DraftDetailModal.tsx
/* eslint-disable react-hooks/set-state-in-effect */
import { useState, useEffect, useCallback, useMemo } from "react";
import type { EmailDraft, UpdateEmailDraftRequest, EmailDraftTone, RegenerateDraftRequest } from "@/api/drafts";
import { RichTextEditor } from "./RichTextEditor";
import { ToneSelector } from "./ToneSelector";
import { StyleMatchIndicator } from "./StyleMatchIndicator";

interface DraftDetailModalProps {
  draft: EmailDraft | null;
  isOpen: boolean;
  onClose: () => void;
  onSave: (draftId: string, data: UpdateEmailDraftRequest) => void;
  onRegenerate: (draftId: string, data?: RegenerateDraftRequest) => void;
  onSend: (draftId: string) => void;
  isSaving?: boolean;
  isRegenerating?: boolean;
  isSending?: boolean;
}

export function DraftDetailModal({
  draft,
  isOpen,
  onClose,
  onSave,
  onRegenerate,
  onSend,
  isSaving = false,
  isRegenerating = false,
  isSending = false,
}: DraftDetailModalProps) {
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  const [tone, setTone] = useState<EmailDraftTone>("friendly");
  const [showSendConfirm, setShowSendConfirm] = useState(false);

  const isLoading = isSaving || isRegenerating || isSending;
  const canEdit = draft?.status === "draft";

  // Initialize form when draft changes
  useEffect(() => {
    if (draft) {
      setSubject(draft.subject);
      setBody(draft.body);
      setTone(draft.tone);
    }
  }, [draft]);

  // Compute hasChanges via useMemo instead of storing in state
  const hasChanges = useMemo(() => {
    if (!draft) return false;
    return subject !== draft.subject || body !== draft.body || tone !== draft.tone;
  }, [draft, subject, body, tone]);

  // Handle escape key
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isLoading) {
        if (showSendConfirm) {
          setShowSendConfirm(false);
        } else {
          onClose();
        }
      }
    },
    [onClose, isLoading, showSendConfirm]
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
      return () => document.removeEventListener("keydown", handleKeyDown);
    }
  }, [isOpen, handleKeyDown]);

  const handleSave = () => {
    if (!draft || !hasChanges) return;
    onSave(draft.id, {
      subject: subject.trim(),
      body: body.trim(),
      tone,
    });
  };

  const handleRegenerate = () => {
    if (!draft) return;
    onRegenerate(draft.id, { tone });
  };

  const handleSendClick = () => {
    setShowSendConfirm(true);
  };

  const handleConfirmSend = () => {
    if (!draft) return;
    setShowSendConfirm(false);
    onSend(draft.id);
  };

  if (!isOpen || !draft) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={isLoading ? undefined : onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-3xl max-h-[90vh] mx-4 bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="shrink-0 flex items-center justify-between px-6 py-4 border-b border-slate-700">
          <div className="flex items-center gap-4">
            <div>
              <h2 className="text-xl font-semibold text-white">
                {canEdit ? "Edit Draft" : "View Email"}
              </h2>
              <p className="text-sm text-slate-400 mt-0.5">
                To: {draft.recipient_name || draft.recipient_email}
              </p>
            </div>
            {draft.style_match_score !== undefined && (
              <StyleMatchIndicator score={draft.style_match_score} size="md" />
            )}
          </div>
          <button
            onClick={onClose}
            disabled={isLoading}
            className="p-2 text-slate-400 hover:text-white hover:bg-slate-700 rounded-xl transition-colors disabled:opacity-50"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto">
          <div className="px-6 py-5 space-y-5">
            {/* Status badge for sent/failed */}
            {draft.status !== "draft" && (
              <div className={`p-4 rounded-xl ${
                draft.status === "sent"
                  ? "bg-emerald-500/10 border border-emerald-500/30"
                  : "bg-red-500/10 border border-red-500/30"
              }`}>
                <div className="flex items-center gap-2">
                  {draft.status === "sent" ? (
                    <>
                      <svg className="w-5 h-5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                      </svg>
                      <span className="font-medium text-emerald-400">Email sent successfully</span>
                    </>
                  ) : (
                    <>
                      <svg className="w-5 h-5 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                      </svg>
                      <span className="font-medium text-red-400">Failed to send</span>
                    </>
                  )}
                </div>
                {draft.sent_at && (
                  <p className="text-sm text-slate-400 mt-1">
                    {new Date(draft.sent_at).toLocaleString()}
                  </p>
                )}
                {draft.error_message && (
                  <p className="text-sm text-red-300 mt-1">{draft.error_message}</p>
                )}
              </div>
            )}

            {/* Subject */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">Subject</label>
              <input
                type="text"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                disabled={!canEdit || isLoading}
                className="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all disabled:opacity-60"
              />
            </div>

            {/* Tone selector - only show for editable drafts */}
            {canEdit && (
              <ToneSelector value={tone} onChange={setTone} disabled={isLoading} />
            )}

            {/* Body */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">Body</label>
              <RichTextEditor
                content={body}
                onChange={setBody}
                placeholder="Email body..."
                disabled={!canEdit || isLoading}
              />
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="shrink-0 flex items-center justify-between px-6 py-4 border-t border-slate-700">
          <div className="flex items-center gap-2">
            {canEdit && (
              <button
                type="button"
                onClick={handleRegenerate}
                disabled={isLoading}
                className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-slate-300 hover:text-white bg-slate-700/50 hover:bg-slate-700 rounded-xl transition-colors disabled:opacity-50"
              >
                {isRegenerating ? (
                  <>
                    <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Regenerating...
                  </>
                ) : (
                  <>
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                    Regenerate
                  </>
                )}
              </button>
            )}
          </div>

          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={onClose}
              disabled={isLoading}
              className="px-4 py-2.5 text-sm font-medium text-slate-400 hover:text-white hover:bg-slate-700 rounded-xl transition-colors disabled:opacity-50"
            >
              {canEdit ? "Cancel" : "Close"}
            </button>

            {canEdit && (
              <>
                <button
                  type="button"
                  onClick={handleSave}
                  disabled={isLoading || !hasChanges}
                  className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-medium text-primary-400 bg-primary-600/10 hover:bg-primary-600/20 border border-primary-500/30 rounded-xl transition-colors disabled:opacity-50"
                >
                  {isSaving ? (
                    <>
                      <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                      Saving...
                    </>
                  ) : (
                    "Save Changes"
                  )}
                </button>

                <button
                  type="button"
                  onClick={handleSendClick}
                  disabled={isLoading}
                  className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium bg-gradient-to-r from-emerald-600 to-emerald-500 hover:from-emerald-500 hover:to-emerald-400 text-white rounded-xl transition-all duration-200 shadow-lg shadow-emerald-600/25 disabled:opacity-50"
                >
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                  </svg>
                  Send Email
                </button>
              </>
            )}
          </div>
        </div>
      </div>

      {/* Send Confirmation Modal */}
      {showSendConfirm && (
        <div className="absolute inset-0 z-60 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/50" onClick={() => setShowSendConfirm(false)} />
          <div className="relative bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl p-6 max-w-md mx-4 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-start gap-4">
              <div className="shrink-0 w-12 h-12 rounded-full bg-emerald-500/20 flex items-center justify-center">
                <svg className="w-6 h-6 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                </svg>
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-white mb-2">Send this email?</h3>
                <p className="text-sm text-slate-400 mb-1">
                  This email will be sent to:
                </p>
                <p className="text-sm font-medium text-white mb-4">
                  {draft.recipient_name ? `${draft.recipient_name} <${draft.recipient_email}>` : draft.recipient_email}
                </p>
                <div className="flex items-center gap-3">
                  <button
                    onClick={() => setShowSendConfirm(false)}
                    className="flex-1 px-4 py-2.5 text-sm font-medium text-slate-400 hover:text-white bg-slate-700/50 hover:bg-slate-700 rounded-xl transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleConfirmSend}
                    disabled={isSending}
                    className="flex-1 inline-flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium bg-emerald-600 hover:bg-emerald-500 text-white rounded-xl transition-colors disabled:opacity-50"
                  >
                    {isSending ? (
                      <>
                        <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        Sending...
                      </>
                    ) : (
                      "Send Now"
                    )}
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
