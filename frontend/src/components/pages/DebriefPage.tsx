/**
 * DebriefPage - Post-meeting debrief with AI extraction
 *
 * Route: /dashboard/debriefs/new?meeting_id={id}
 *
 * Features:
 * - Pre-filled meeting info from calendar event
 * - 3 outcome buttons: Positive, Neutral, Concern
 * - Auto-expanding notes textarea
 * - AI-extracted results: summary, action items, commitments, insights
 * - Follow-up email draft
 *
 * Design: Mobile-first, single column, focused layout
 */

import { useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import {
  ChevronLeft,
  Check,
  Circle,
  AlertTriangle,
  Loader2,
  Send,
  Edit3,
  Building2,
  Calendar,
  Users,
} from "lucide-react";
import { cn } from "@/utils/cn";
import { useDebrief, useUpdateDebrief } from "@/hooks/useDebriefs";
import type { DebriefOutcome } from "@/api/debriefs";

// Outcome button configuration
const OUTCOME_OPTIONS: {
  value: DebriefOutcome;
  label: string;
  icon: typeof Check;
  colorClass: string;
  bgClass: string;
}[] = [
  {
    value: "positive",
    label: "Positive",
    icon: Check,
    colorClass: "text-green-600",
    bgClass: "bg-green-50 border-green-200 hover:bg-green-100",
  },
  {
    value: "neutral",
    label: "Neutral",
    icon: Circle,
    colorClass: "text-slate-500",
    bgClass: "bg-slate-50 border-slate-200 hover:bg-slate-100",
  },
  {
    value: "concern",
    label: "Concern",
    icon: AlertTriangle,
    colorClass: "text-amber-600",
    bgClass: "bg-amber-50 border-amber-200 hover:bg-amber-100",
  },
];

export function DebriefPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const meetingId = searchParams.get("meeting_id") || "";

  const [selectedOutcome, setSelectedOutcome] = useState<DebriefOutcome | null>(null);
  const [notes, setNotes] = useState("");
  const [showResults, setShowResults] = useState(false);

  // Queries and mutations
  const { data: debrief, isLoading, error } = useDebrief(meetingId);
  const updateDebrief = useUpdateDebrief();
  const isSubmitting = updateDebrief.isPending;

  // Handle form submission
  const handleSubmit = async () => {
    if (!debrief || !selectedOutcome) return;

    await updateDebrief.mutateAsync({
      debriefId: debrief.id,
      data: {
        outcome: selectedOutcome,
        notes: notes.trim() || undefined,
      },
    });

    setShowResults(true);
  };

  // Loading state
  if (isLoading) {
    return (
      <div
        className="flex-1 flex flex-col h-full"
        style={{ backgroundColor: "var(--bg-primary)" }}
      >
        <div className="flex-1 overflow-y-auto p-6">
          <div className="animate-pulse space-y-6" data-testid="debrief-loading">
            <div className="h-4 w-32 bg-[var(--border)] rounded" />
            <div className="h-8 w-2/3 bg-[var(--border)] rounded" />
            <div className="h-20 w-full bg-[var(--border)] rounded" />
            <div className="flex gap-4">
              <div className="h-24 flex-1 bg-[var(--border)] rounded-lg" />
              <div className="h-24 flex-1 bg-[var(--border)] rounded-lg" />
              <div className="h-24 flex-1 bg-[var(--border)] rounded-lg" />
            </div>
            <div className="h-32 w-full bg-[var(--border)] rounded" />
          </div>
        </div>
      </div>
    );
  }

  // Error state
  if (error || !debrief) {
    return (
      <div
        className="flex-1 flex flex-col h-full"
        style={{ backgroundColor: "var(--bg-primary)" }}
      >
        <div className="flex-1 overflow-y-auto p-6">
          <button
            onClick={() => navigate("/communications")}
            className="flex items-center gap-2 text-sm mb-6 hover:opacity-80 transition-opacity"
            style={{ color: "var(--text-secondary)" }}
          >
            <ChevronLeft className="w-4 h-4" />
            Back
          </button>
          <div
            className="text-center py-8"
            style={{ color: "var(--text-secondary)" }}
          >
            Error loading debrief. Please try again.
          </div>
        </div>
      </div>
    );
  }

  // Show AI-extracted results after submission
  if (showResults && debrief.ai_analysis) {
    return (
      <DebriefResults
        debrief={debrief}
        onClose={() => navigate("/communications")}
      />
    );
  }

  // Format date
  const meetingDate = new Date(debrief.occurred_at);
  const formattedDate = meetingDate.toLocaleDateString("en-US", {
    weekday: "long",
    month: "long",
    day: "numeric",
    year: "numeric",
  });
  const formattedTime = meetingDate.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });

  return (
    <div
      className="flex-1 flex flex-col h-full"
      style={{ backgroundColor: "var(--bg-primary)" }}
    >
      <div className="flex-1 overflow-y-auto">
        {/* Mobile-friendly max-width container */}
        <div className="max-w-2xl mx-auto p-6 space-y-6">
          {/* Back button */}
          <button
            onClick={() => navigate("/communications")}
            className="flex items-center gap-2 text-sm hover:opacity-80 transition-opacity"
            style={{ color: "var(--text-secondary)" }}
          >
            <ChevronLeft className="w-4 h-4" />
            Back
          </button>

          {/* Meeting header */}
          <div className="space-y-3">
            <h1
              className="font-display text-2xl italic"
              style={{ color: "var(--text-primary)" }}
            >
              {debrief.title}
            </h1>

            <div
              className="flex flex-wrap items-center gap-4 text-sm"
              style={{ color: "var(--text-secondary)" }}
            >
              <div className="flex items-center gap-1.5">
                <Calendar className="w-4 h-4" />
                <span>{formattedDate} at {formattedTime}</span>
              </div>

              {debrief.attendees.length > 0 && (
                <div className="flex items-center gap-1.5">
                  <Users className="w-4 h-4" />
                  <span>{debrief.attendees.join(", ")}</span>
                </div>
              )}
            </div>

            {/* Lead badge */}
            {debrief.lead_name && (
              <div
                className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm"
                style={{
                  backgroundColor: "var(--bg-elevated)",
                  color: "var(--text-secondary)",
                }}
              >
                <Building2 className="w-4 h-4" />
                <span>{debrief.lead_name}</span>
                <button
                  className="text-xs hover:opacity-70"
                  style={{ color: "var(--accent)" }}
                >
                  Change
                </button>
              </div>
            )}
          </div>

          {/* Outcome selector */}
          <div className="space-y-3">
            <label
              className="block text-sm font-medium"
              style={{ color: "var(--text-secondary)" }}
            >
              How did it go?
            </label>
            <div className="grid grid-cols-3 gap-3">
              {OUTCOME_OPTIONS.map((option) => {
                const Icon = option.icon;
                const isSelected = selectedOutcome === option.value;

                return (
                  <button
                    key={option.value}
                    onClick={() => setSelectedOutcome(option.value)}
                    className={cn(
                      "flex flex-col items-center gap-2 p-4 rounded-lg border-2 transition-all",
                      "focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-[var(--accent)]",
                      option.bgClass,
                      isSelected && "ring-2 ring-offset-2 ring-[var(--accent)]"
                    )}
                    style={{
                      borderColor: isSelected ? "var(--accent)" : undefined,
                    }}
                  >
                    <Icon
                      className={cn("w-6 h-6", option.colorClass)}
                      strokeWidth={option.value === "neutral" ? 1.5 : 2.5}
                    />
                    <span
                      className="text-sm font-medium"
                      style={{ color: "var(--text-primary)" }}
                    >
                      {option.label}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Notes textarea */}
          <div className="space-y-2">
            <label
              className="block text-sm font-medium"
              style={{ color: "var(--text-secondary)" }}
            >
              Notes
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="What happened? Key decisions, next steps, concerns..."
              rows={5}
              className={cn(
                "w-full px-4 py-3 rounded-lg border text-sm resize-none",
                "border-[var(--border)] bg-[var(--bg-elevated)]",
                "focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/30",
                "placeholder:text-[var(--text-muted)]"
              )}
              style={{
                color: "var(--text-primary)",
                minHeight: "120px",
              }}
            />
          </div>
        </div>
      </div>

      {/* Bottom action bar */}
      <div
        className="flex-shrink-0 border-t p-4"
        style={{ borderColor: "var(--border)", backgroundColor: "var(--bg-elevated)" }}
      >
        <div className="max-w-2xl mx-auto">
          <button
            onClick={handleSubmit}
            disabled={!selectedOutcome || isSubmitting}
            className={cn(
              "w-full flex items-center justify-center gap-2 px-6 py-3 rounded-lg text-sm font-medium",
              "transition-colors",
              (!selectedOutcome || isSubmitting) && "opacity-50 cursor-not-allowed"
            )}
            style={{
              backgroundColor: "var(--accent)",
              color: "white",
            }}
          >
            {isSubmitting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Processing...
              </>
            ) : (
              <>
                <Edit3 className="w-4 h-4" />
                Process Debrief
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

// Results component shown after submission
interface DebriefResultsProps {
  debrief: NonNullable<ReturnType<typeof useDebrief>["data"]>;
  onClose: () => void;
}

function DebriefResults({ debrief, onClose }: DebriefResultsProps) {
  const navigate = useNavigate();
  const analysis = debrief.ai_analysis;

  if (!analysis) {
    return null;
  }

  return (
    <div
      className="flex-1 flex flex-col h-full overflow-y-auto"
      style={{ backgroundColor: "var(--bg-primary)" }}
    >
      <div className="max-w-2xl mx-auto p-6 space-y-6 w-full">
        {/* Back button */}
        <button
          onClick={onClose}
          className="flex items-center gap-2 text-sm hover:opacity-80 transition-opacity"
          style={{ color: "var(--text-secondary)" }}
        >
          <ChevronLeft className="w-4 h-4" />
          Done
        </button>

        {/* Summary card */}
        <div
          className="rounded-lg border p-4"
          style={{
            borderColor: "var(--border)",
            backgroundColor: "var(--bg-elevated)",
          }}
        >
          <h2
            className="text-sm font-medium mb-2"
            style={{ color: "var(--text-secondary)" }}
          >
            Summary
          </h2>
          <p style={{ color: "var(--text-primary)" }}>{analysis.summary}</p>
        </div>

        {/* Action items */}
        {analysis.action_items.length > 0 && (
          <div
            className="rounded-lg border p-4"
            style={{
              borderColor: "var(--border)",
              backgroundColor: "var(--bg-elevated)",
            }}
          >
            <h2
              className="text-sm font-medium mb-3"
              style={{ color: "var(--text-secondary)" }}
            >
              Action Items
            </h2>
            <ul className="space-y-2">
              {analysis.action_items.map((item, index) => (
                <li
                  key={index}
                  className="flex items-start gap-3"
                >
                  <input
                    type="checkbox"
                    checked={item.completed}
                    readOnly
                    className="mt-1 rounded border-[var(--border)]"
                  />
                  <div className="flex-1">
                    <p style={{ color: "var(--text-primary)" }}>{item.task}</p>
                    {(item.owner || item.due_date) && (
                      <p
                        className="text-xs mt-0.5"
                        style={{ color: "var(--text-secondary)" }}
                      >
                        {item.owner && `Assigned: ${item.owner}`}
                        {item.owner && item.due_date && " · "}
                        {item.due_date && `Due: ${new Date(item.due_date).toLocaleDateString()}`}
                      </p>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Commitments */}
        {(analysis.commitments.ours.length > 0 || analysis.commitments.theirs.length > 0) && (
          <div className="grid grid-cols-2 gap-4">
            {/* Our commitments */}
            {analysis.commitments.ours.length > 0 && (
              <div
                className="rounded-lg border p-4"
                style={{
                  borderColor: "var(--border)",
                  backgroundColor: "var(--bg-elevated)",
                }}
              >
                <h2
                  className="text-sm font-medium mb-2"
                  style={{ color: "var(--text-secondary)" }}
                >
                  Our Commitments
                </h2>
                <ul className="space-y-1">
                  {analysis.commitments.ours.map((item, index) => (
                    <li
                      key={index}
                      className="text-sm"
                      style={{ color: "var(--text-primary)" }}
                    >
                      • {item}
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {/* Their commitments */}
            {analysis.commitments.theirs.length > 0 && (
              <div
                className="rounded-lg border p-4"
                style={{
                  borderColor: "var(--border)",
                  backgroundColor: "var(--bg-elevated)",
                }}
              >
                <h2
                  className="text-sm font-medium mb-2"
                  style={{ color: "var(--text-secondary)" }}
                >
                  Their Commitments
                </h2>
                <ul className="space-y-1">
                  {analysis.commitments.theirs.map((item, index) => (
                    <li
                      key={index}
                      className="text-sm"
                      style={{ color: "var(--text-primary)" }}
                    >
                      • {item}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}

        {/* Insights chips */}
        {analysis.insights.length > 0 && (
          <div>
            <h2
              className="text-sm font-medium mb-2"
              style={{ color: "var(--text-secondary)" }}
            >
              Insights
            </h2>
            <div className="flex flex-wrap gap-2">
              {analysis.insights.map((insight, index) => (
                <span
                  key={index}
                  className="px-3 py-1 rounded-full text-xs font-medium"
                  style={{
                    backgroundColor: "var(--bg-subtle)",
                    color: "var(--text-secondary)",
                  }}
                >
                  {insight}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Follow-up email draft */}
        {debrief.follow_up_email && (
          <div
            className="rounded-lg border p-4"
            style={{
              borderColor: "var(--border)",
              backgroundColor: "var(--bg-elevated)",
            }}
          >
            <div className="flex items-start justify-between gap-4 mb-3">
              <h2
                className="text-sm font-medium"
                style={{ color: "var(--text-secondary)" }}
              >
                Follow-up Email Draft
              </h2>
              <button
                onClick={() => navigate(`/communications/drafts/${debrief.follow_up_email?.draft_id}`)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium"
                style={{
                  backgroundColor: "var(--accent)",
                  color: "white",
                }}
              >
                <Send className="w-4 h-4" />
                Edit & Send
              </button>
            </div>
            <p
              className="text-sm mb-2"
              style={{ color: "var(--text-primary)" }}
            >
              {debrief.follow_up_email.subject}
            </p>
            <p
              className="text-sm whitespace-pre-line line-clamp-3"
              style={{ color: "var(--text-secondary)" }}
            >
              {debrief.follow_up_email.body}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
