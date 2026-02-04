// frontend/src/components/drafts/DraftComposeModal.tsx
/* eslint-disable react-hooks/set-state-in-effect */
import { useState, useEffect, useCallback } from "react";
import type { EmailDraftTone, EmailDraftPurpose, CreateEmailDraftRequest } from "@/api/drafts";
import { ToneSelector } from "./ToneSelector";
import { PurposeSelector } from "./PurposeSelector";

interface DraftComposeModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (data: CreateEmailDraftRequest) => void;
  isLoading?: boolean;
}

export function DraftComposeModal({
  isOpen,
  onClose,
  onSubmit,
  isLoading = false,
}: DraftComposeModalProps) {
  const [recipientEmail, setRecipientEmail] = useState("");
  const [recipientName, setRecipientName] = useState("");
  const [subjectHint, setSubjectHint] = useState("");
  const [purpose, setPurpose] = useState<EmailDraftPurpose>("intro");
  const [tone, setTone] = useState<EmailDraftTone>("friendly");
  const [context, setContext] = useState("");

  // Reset form when modal opens
  useEffect(() => {
    if (isOpen) {
      setRecipientEmail("");
      setRecipientName("");
      setSubjectHint("");
      setPurpose("intro");
      setTone("friendly");
      setContext("");
    }
  }, [isOpen]);

  // Handle escape key
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape" && !isLoading) {
        onClose();
      }
    },
    [onClose, isLoading]
  );

  useEffect(() => {
    if (isOpen) {
      document.addEventListener("keydown", handleKeyDown);
      return () => document.removeEventListener("keydown", handleKeyDown);
    }
  }, [isOpen, handleKeyDown]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!recipientEmail.trim()) return;

    onSubmit({
      recipient_email: recipientEmail.trim(),
      recipient_name: recipientName.trim() || undefined,
      subject_hint: subjectHint.trim() || undefined,
      purpose,
      tone,
      context: context.trim() || undefined,
    });
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop with blur */}
      <div
        className="absolute inset-0 bg-black/70 backdrop-blur-sm"
        onClick={isLoading ? undefined : onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-xl max-h-[90vh] mx-4 bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl flex flex-col overflow-hidden animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="shrink-0 flex items-center justify-between px-6 py-4 border-b border-slate-700">
          <div>
            <h2 className="text-xl font-semibold text-white">Compose Email</h2>
            <p className="text-sm text-slate-400 mt-0.5">ARIA will draft an email based on your inputs</p>
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

        {/* Form */}
        <form onSubmit={handleSubmit} className="flex-1 overflow-y-auto">
          <div className="px-6 py-5 space-y-5">
            {/* Recipient info */}
            <div className="grid sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">
                  Recipient Email <span className="text-red-400">*</span>
                </label>
                <input
                  type="email"
                  value={recipientEmail}
                  onChange={(e) => setRecipientEmail(e.target.value)}
                  placeholder="john@example.com"
                  className="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all"
                  required
                  disabled={isLoading}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-slate-300 mb-1.5">
                  Recipient Name
                </label>
                <input
                  type="text"
                  value={recipientName}
                  onChange={(e) => setRecipientName(e.target.value)}
                  placeholder="John Smith"
                  className="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all"
                  disabled={isLoading}
                />
              </div>
            </div>

            {/* Subject hint */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">
                Subject Hint
              </label>
              <input
                type="text"
                value={subjectHint}
                onChange={(e) => setSubjectHint(e.target.value)}
                placeholder="What should the email be about?"
                className="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all"
                disabled={isLoading}
              />
            </div>

            {/* Purpose selector */}
            <PurposeSelector value={purpose} onChange={setPurpose} disabled={isLoading} />

            {/* Tone selector */}
            <ToneSelector value={tone} onChange={setTone} disabled={isLoading} />

            {/* Additional context */}
            <div>
              <label className="block text-sm font-medium text-slate-300 mb-1.5">
                Additional Context
              </label>
              <textarea
                value={context}
                onChange={(e) => setContext(e.target.value)}
                placeholder="Any specific points to include, recent interactions, or relevant background..."
                rows={3}
                className="w-full px-4 py-2.5 bg-slate-900 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-transparent transition-all resize-none"
                disabled={isLoading}
              />
            </div>
          </div>

          {/* Footer */}
          <div className="shrink-0 flex items-center justify-end gap-3 px-6 py-4 border-t border-slate-700">
            <button
              type="button"
              onClick={onClose}
              disabled={isLoading}
              className="px-4 py-2.5 text-sm font-medium text-slate-400 hover:text-white hover:bg-slate-700 rounded-xl transition-colors disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading || !recipientEmail.trim()}
              className="inline-flex items-center gap-2 px-5 py-2.5 text-sm font-medium bg-gradient-to-r from-primary-600 to-primary-500 hover:from-primary-500 hover:to-primary-400 text-white rounded-xl transition-all duration-200 shadow-lg shadow-primary-600/25 disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none"
            >
              {isLoading ? (
                <>
                  <svg className="animate-spin w-4 h-4" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Generating...
                </>
              ) : (
                <>
                  <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                  </svg>
                  Generate Draft
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
