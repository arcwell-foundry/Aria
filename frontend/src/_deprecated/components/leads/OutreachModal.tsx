import { Send, Sparkles, X } from "lucide-react";
import { useState } from "react";
import { useInitiateOutreach } from "@/hooks/useLeadGeneration";

interface OutreachModalProps {
  isOpen: boolean;
  onClose: () => void;
  leadId: string;
  companyName: string;
}

export function OutreachModal({ isOpen, onClose, leadId, companyName }: OutreachModalProps) {
  const [subject, setSubject] = useState(`Introduction to ${companyName}`);
  const [message, setMessage] = useState("");
  const [tone, setTone] = useState("Professional");
  const [error, setError] = useState<string | null>(null);

  const outreachMutation = useInitiateOutreach();

  if (!isOpen) return null;

  const isValid = subject.trim().length > 0 && message.trim().length > 0;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!isValid) return;

    outreachMutation.mutate(
      {
        leadId,
        outreach: {
          subject: subject.trim(),
          message: message.trim(),
          tone: tone.toLowerCase(),
        },
      },
      {
        onSuccess: () => {
          setSubject(`Introduction to ${companyName}`);
          setMessage("");
          setTone("Professional");
          setError(null);
          onClose();
        },
        onError: (err: Error) => {
          setError(err.message || "Failed to send outreach. Please try again.");
        },
      }
    );
  };

  const handleClose = () => {
    setSubject(`Introduction to ${companyName}`);
    setMessage("");
    setTone("Professional");
    setError(null);
    onClose();
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-900/80 backdrop-blur-sm animate-in fade-in duration-200"
        onClick={handleClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-lg bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700">
          <div>
            <h2 className="text-lg font-semibold text-white">Initiate Outreach</h2>
            <p className="text-sm text-slate-400 mt-0.5">{companyName}</p>
          </div>
          <button
            onClick={handleClose}
            className="p-2 rounded-lg hover:bg-slate-700 text-slate-400 hover:text-white transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Error */}
          {error && (
            <div className="px-4 py-3 text-sm text-red-300 bg-red-900/30 border border-red-800/50 rounded-lg">
              {error}
            </div>
          )}

          {/* Subject */}
          <div>
            <label htmlFor="outreach-subject" className="block text-sm font-medium text-slate-300 mb-2">
              Subject
            </label>
            <input
              id="outreach-subject"
              type="text"
              value={subject}
              onChange={(e) => setSubject(e.target.value)}
              className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 transition-all"
            />
          </div>

          {/* Message */}
          <div>
            <label htmlFor="outreach-message" className="block text-sm font-medium text-slate-300 mb-2">
              Message
            </label>
            <textarea
              id="outreach-message"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Write your outreach message..."
              rows={6}
              className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 resize-none transition-all"
            />
            <p className="flex items-center gap-1.5 text-xs text-slate-500 mt-1.5">
              <Sparkles className="w-3.5 h-3.5" />
              Scribe agent will refine this draft to match your writing style
            </p>
          </div>

          {/* Tone */}
          <div>
            <label htmlFor="outreach-tone" className="block text-sm font-medium text-slate-300 mb-2">
              Tone
            </label>
            <select
              id="outreach-tone"
              value={tone}
              onChange={(e) => setTone(e.target.value)}
              className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-white focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 transition-all"
            >
              <option value="Professional">Professional</option>
              <option value="Friendly">Friendly</option>
              <option value="Direct">Direct</option>
            </select>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-3 pt-4">
            <button
              type="button"
              onClick={handleClose}
              className="px-4 py-2.5 text-sm font-medium text-slate-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!isValid || outreachMutation.isPending}
              className="flex items-center gap-2 px-5 py-2.5 bg-primary-600 hover:bg-primary-500 disabled:bg-primary-600/50 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors shadow-lg shadow-primary-600/25"
            >
              {outreachMutation.isPending ? (
                <>
                  <svg className="w-4 h-4 animate-spin" viewBox="0 0 24 24">
                    <circle
                      className="opacity-25"
                      cx="12"
                      cy="12"
                      r="10"
                      stroke="currentColor"
                      strokeWidth="4"
                      fill="none"
                    />
                    <path
                      className="opacity-75"
                      fill="currentColor"
                      d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                    />
                  </svg>
                  Sending...
                </>
              ) : (
                <>
                  <Send className="w-4 h-4" />
                  Send to Scribe
                </>
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
