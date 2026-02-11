import { X } from "lucide-react";
import { useState } from "react";
import type { EventType, LeadEvent } from "@/api/leads";

interface AddEventModalProps {
  leadId: string;
  companyName: string;
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (event: Omit<LeadEvent, "id" | "lead_memory_id" | "created_at">) => void;
  isLoading: boolean;
}

// Event type options with labels and colors
const eventTypeOptions: {
  value: EventType;
  label: string;
  color: string;
  activeColor: string;
}[] = [
  {
    value: "email_sent",
    label: "Email Sent",
    color: "text-info",
    activeColor: "bg-info/20 border-info/50 text-info",
  },
  {
    value: "email_received",
    label: "Email Received",
    color: "text-cyan-400",
    activeColor: "bg-cyan-500/20 border-cyan-500/50 text-cyan-400",
  },
  {
    value: "meeting",
    label: "Meeting",
    color: "text-purple-400",
    activeColor: "bg-purple-500/20 border-purple-500/50 text-purple-400",
  },
  {
    value: "call",
    label: "Call",
    color: "text-warning",
    activeColor: "bg-warning/20 border-warning/50 text-warning",
  },
  {
    value: "note",
    label: "Note",
    color: "text-slate-400",
    activeColor: "bg-slate-500/20 border-slate-500/50 text-slate-400",
  },
  {
    value: "signal",
    label: "Signal",
    color: "text-success",
    activeColor: "bg-success/20 border-success/50 text-success",
  },
];

// Event types that show subject field
const typesWithSubject: EventType[] = ["email_sent", "email_received", "meeting"];

// Event types that show participants field
const typesWithParticipants: EventType[] = ["email_sent", "email_received", "meeting", "call"];

export function AddEventModal({
  leadId,
  companyName,
  isOpen,
  onClose,
  onSubmit,
  isLoading,
}: AddEventModalProps) {
  const [eventType, setEventType] = useState<EventType>("note");
  const [subject, setSubject] = useState("");
  const [content, setContent] = useState("");
  const [participants, setParticipants] = useState("");

  // Suppress unused variable warning - leadId may be used for future validation
  void leadId;

  if (!isOpen) return null;

  const showSubject = typesWithSubject.includes(eventType);
  const showParticipants = typesWithParticipants.includes(eventType);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    // Determine direction based on event type
    let direction: "inbound" | "outbound" | null = null;
    if (eventType === "email_sent") {
      direction = "outbound";
    } else if (eventType === "email_received") {
      direction = "inbound";
    }

    // Parse participants from comma-separated string
    const participantsList = participants
      .split(",")
      .map((p) => p.trim())
      .filter((p) => p.length > 0);

    const event: Omit<LeadEvent, "id" | "lead_memory_id" | "created_at"> = {
      event_type: eventType,
      direction,
      subject: showSubject && subject.trim() ? subject.trim() : null,
      content: content.trim() || null,
      participants: showParticipants ? participantsList : [],
      occurred_at: new Date().toISOString(),
      source: "manual",
    };

    onSubmit(event);
  };

  const handleClose = () => {
    // Reset form state
    setEventType("note");
    setSubject("");
    setContent("");
    setParticipants("");
    onClose();
  };

  const canSubmit = content.trim().length > 0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-slate-900/80 backdrop-blur-sm animate-in fade-in duration-200"
        onClick={handleClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-lg bg-slate-800 border border-slate-700 rounded-2xl shadow-2xl animate-in fade-in zoom-in-95 duration-200 max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-slate-700 shrink-0">
          <div>
            <h2 className="text-lg font-semibold text-white">Add Event</h2>
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
        <form onSubmit={handleSubmit} className="p-6 overflow-y-auto">
          {/* Event type toggle buttons */}
          <div className="mb-5">
            <label className="block text-sm font-medium text-slate-300 mb-3">
              Event Type
            </label>
            <div className="grid grid-cols-3 gap-2">
              {eventTypeOptions.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  onClick={() => setEventType(option.value)}
                  className={`px-3 py-2.5 text-sm font-medium rounded-lg border transition-all duration-200 ${
                    eventType === option.value
                      ? option.activeColor
                      : "bg-slate-900/50 border-slate-700 text-slate-400 hover:bg-slate-700/50 hover:border-slate-600"
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          {/* Subject field (conditional) */}
          {showSubject && (
            <div className="mb-5 animate-in fade-in slide-in-from-top-2 duration-200">
              <label htmlFor="event-subject" className="block text-sm font-medium text-slate-300 mb-2">
                Subject
              </label>
              <input
                id="event-subject"
                type="text"
                value={subject}
                onChange={(e) => setSubject(e.target.value)}
                placeholder={
                  eventType === "meeting"
                    ? "Meeting topic"
                    : "Email subject line"
                }
                className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 transition-all"
              />
            </div>
          )}

          {/* Participants field (conditional) */}
          {showParticipants && (
            <div className="mb-5 animate-in fade-in slide-in-from-top-2 duration-200">
              <label htmlFor="event-participants" className="block text-sm font-medium text-slate-300 mb-2">
                Participants
              </label>
              <input
                id="event-participants"
                type="text"
                value={participants}
                onChange={(e) => setParticipants(e.target.value)}
                placeholder="john@example.com, jane@example.com"
                className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 transition-all"
              />
              <p className="text-xs text-slate-500 mt-1.5">
                Separate multiple participants with commas
              </p>
            </div>
          )}

          {/* Content textarea (always shown) */}
          <div className="mb-6">
            <label htmlFor="event-content" className="block text-sm font-medium text-slate-300 mb-2">
              Content <span className="text-critical">*</span>
            </label>
            <textarea
              id="event-content"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder={
                eventType === "note"
                  ? "Add your note here..."
                  : eventType === "signal"
                    ? "Describe the signal or trigger event..."
                    : eventType === "call"
                      ? "Call summary and key points..."
                      : eventType === "meeting"
                        ? "Meeting notes and outcomes..."
                        : "Email content or summary..."
              }
              rows={4}
              className="w-full px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-xl text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500/50 focus:border-primary-500/50 resize-none transition-all"
            />
          </div>

          {/* Action buttons */}
          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={handleClose}
              className="px-4 py-2.5 text-sm font-medium text-slate-400 hover:text-white transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={!canSubmit || isLoading}
              className="px-5 py-2.5 bg-primary-600 hover:bg-primary-500 disabled:bg-primary-600/50 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors shadow-lg shadow-primary-600/25"
            >
              {isLoading ? (
                <span className="flex items-center gap-2">
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
                  Adding...
                </span>
              ) : (
                "Add Event"
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
