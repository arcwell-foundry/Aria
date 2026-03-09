/**
 * ContactHistoryView - Unified timeline of all communications with a specific contact
 *
 * Shows a merged view of:
 * - Emails received from the contact (from email_scan_log)
 * - Drafts/replies to the contact (from email_drafts)
 * - Sent emails to the contact
 *
 * This is a view mode within the Communications page, triggered when:
 * - User clicks on a contact name in the Drafts or Email Log tabs
 * - User uses search to find a specific contact and clicks "View all communications"
 */

import { useState, useEffect, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Mail,
  MailOpen,
  Send,
  FileText,
  Clock,
  ArrowRight,
  Inbox,
  AlertCircle,
  Building2,
  TrendingUp,
  Heart,
} from "lucide-react";
import { cn } from "@/utils/cn";
import { fetchContactHistory, type ContactHistoryEntry, type ContactHistoryResponse } from "@/api/communications";
import { EmptyState } from "@/components/common/EmptyState";

// Category display config
const CATEGORY_STYLES: Record<string, { label: string; bg: string; text: string }> = {
  NEEDS_REPLY: { label: "Needs Reply", bg: "var(--accent)", text: "white" },
  FYI: { label: "FYI", bg: "var(--bg-subtle)", text: "var(--text-secondary)" },
  SKIP: { label: "Skip", bg: "var(--bg-subtle)", text: "var(--text-secondary)" },
};

// Urgency display config
const URGENCY_STYLES: Record<string, { label: string; bg: string; text: string }> = {
  URGENT: { label: "Urgent", bg: "var(--critical)", text: "white" },
  NORMAL: { label: "Normal", bg: "var(--bg-subtle)", text: "var(--text-secondary)" },
  LOW: { label: "Low", bg: "var(--bg-subtle)", text: "var(--text-secondary)" },
};

// Status display config for drafts
const STATUS_STYLES: Record<string, { label: string; bg: string; text: string }> = {
  draft: { label: "DRAFT", bg: "var(--accent)", text: "white" },
  sent: { label: "SENT", bg: "var(--success)", text: "white" },
  dismissed: { label: "DISMISSED", bg: "var(--text-secondary)", text: "white" },
  pending_review: { label: "PENDING", bg: "#6366f1", text: "white" },
  approved: { label: "APPROVED", bg: "var(--success)", text: "white" },
  saved_to_client: { label: "SAVED", bg: "#0891b2", text: "white" },
};

// Format relative time
function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

// Format full date
function formatFullDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString("en-US", {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: date.getFullYear() !== new Date().getFullYear() ? "numeric" : undefined,
    hour: "numeric",
    minute: "2-digit",
  });
}

// Entry type icon and label
function getEntryTypeInfo(type: ContactHistoryEntry["type"]) {
  switch (type) {
    case "received":
      return { icon: Inbox, label: "Received", color: "var(--text-secondary)" };
    case "draft":
      return { icon: FileText, label: "Draft", color: "var(--accent)" };
    case "sent":
      return { icon: Send, label: "Sent", color: "var(--success)" };
    case "dismissed":
      return { icon: AlertCircle, label: "Dismissed", color: "var(--text-secondary)" };
    default:
      return { icon: Mail, label: "Email", color: "var(--text-secondary)" };
  }
}

// Skeleton for loading state
function HistorySkeleton() {
  return (
    <div className="space-y-3 animate-pulse">
      {Array.from({ length: 5 }).map((_, i) => (
        <div
          key={i}
          className="border rounded-lg p-4"
          style={{ borderColor: "var(--border)", backgroundColor: "var(--bg-elevated)" }}
        >
          <div className="flex items-start justify-between gap-4">
            <div className="flex items-start gap-3 flex-1">
              <div className="w-8 h-8 rounded-full bg-[var(--border)]" />
              <div className="flex-1 space-y-2">
                <div className="h-4 w-40 bg-[var(--border)] rounded" />
                <div className="h-3 w-full bg-[var(--border)] rounded" />
              </div>
            </div>
            <div className="flex gap-2">
              <div className="h-5 w-16 bg-[var(--border)] rounded-full" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

// Single timeline entry
function TimelineEntry({
  entry,
  onDraftClick,
}: {
  entry: ContactHistoryEntry;
  onDraftClick: (draftId: string) => void;
}) {
  const typeInfo = getEntryTypeInfo(entry.type);
  const TypeIcon = typeInfo.icon;
  const categoryStyle = entry.category ? CATEGORY_STYLES[entry.category] : null;
  const urgencyStyle = entry.urgency ? URGENCY_STYLES[entry.urgency] : null;
  const statusStyle = entry.status ? STATUS_STYLES[entry.status] : null;

  const isClickable = entry.draft_id && (entry.type === "draft" || entry.type === "sent");

  return (
    <button
      onClick={() => isClickable && entry.draft_id && onDraftClick(entry.draft_id)}
      disabled={!isClickable}
      className={cn(
        "w-full text-left border rounded-lg p-4 transition-all duration-200",
        isClickable
          ? "hover:border-[var(--accent)]/50 hover:shadow-sm cursor-pointer"
          : "cursor-default"
      )}
      style={{
        borderColor: "var(--border)",
        backgroundColor: "var(--bg-elevated)",
      }}
    >
      <div className="flex items-start justify-between gap-4">
        {/* Left: icon + content */}
        <div className="flex items-start gap-3 min-w-0 flex-1">
          {/* Direction icon */}
          <div
            className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5"
            style={{ backgroundColor: "var(--bg-subtle)" }}
          >
            <TypeIcon className="w-4 h-4" style={{ color: typeInfo.color }} />
          </div>

          {/* Content */}
          <div className="min-w-0 flex-1">
            {/* Type label + timestamp */}
            <div className="flex items-center gap-2 mb-1">
              <span
                className="text-xs font-medium uppercase tracking-wide"
                style={{ color: typeInfo.color }}
              >
                {typeInfo.label}
              </span>
              <span className="flex items-center gap-1">
                <Clock className="w-3 h-3" style={{ color: "var(--text-secondary)" }} />
                <span
                  className="font-mono text-xs"
                  style={{ color: "var(--text-secondary)" }}
                  title={formatFullDate(entry.timestamp)}
                >
                  {formatRelativeTime(entry.timestamp)}
                </span>
              </span>
            </div>

            {/* Subject */}
            <p
              className="text-sm font-medium truncate mb-1"
              style={{ color: "var(--text-primary)" }}
            >
              {entry.subject || "(no subject)"}
            </p>

            {/* Snippet */}
            {entry.snippet && (
              <p
                className="text-xs leading-relaxed line-clamp-2"
                style={{ color: "var(--text-secondary)" }}
              >
                {entry.snippet}
              </p>
            )}
          </div>
        </div>

        {/* Right: badges */}
        <div className="flex flex-col items-end gap-1.5 flex-shrink-0">
          {/* Category badge (for received emails) */}
          {categoryStyle && (
            <span
              className="px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-wide"
              style={{ backgroundColor: categoryStyle.bg, color: categoryStyle.text }}
            >
              {categoryStyle.label}
            </span>
          )}

          {/* Status badge (for drafts/sent) */}
          {statusStyle && (
            <span
              className="px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-wide"
              style={{ backgroundColor: statusStyle.bg, color: statusStyle.text }}
            >
              {statusStyle.label}
            </span>
          )}

          {/* Urgency badge (for received emails) */}
          {urgencyStyle && entry.urgency !== "NORMAL" && (
            <span
              className="px-2 py-0.5 rounded-full text-[10px] font-medium uppercase tracking-wide"
              style={{ backgroundColor: urgencyStyle.bg, color: urgencyStyle.text }}
            >
              {urgencyStyle.label}
            </span>
          )}

          {/* Arrow for clickable entries */}
          {isClickable && (
            <ArrowRight
              className="w-4 h-4 mt-1"
              style={{ color: "var(--text-secondary)" }}
            />
          )}
        </div>
      </div>
    </button>
  );
}

// Props for the component
export interface ContactHistoryViewProps {
  contactEmail: string;
  onBack: () => void;
}

export function ContactHistoryView({ contactEmail, onBack }: ContactHistoryViewProps) {
  const navigate = useNavigate();
  const [data, setData] = useState<ContactHistoryResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Fetch contact history
  useEffect(() => {
    let mounted = true;

    async function loadHistory() {
      setIsLoading(true);
      setError(null);

      try {
        const result = await fetchContactHistory(contactEmail, 100);
        if (mounted) {
          setData(result);
        }
      } catch (err) {
        if (mounted) {
          setError(err instanceof Error ? err.message : "Failed to load contact history");
        }
      } finally {
        if (mounted) {
          setIsLoading(false);
        }
      }
    }

    loadHistory();

    return () => {
      mounted = false;
    };
  }, [contactEmail]);

  // Handle draft click
  const handleDraftClick = useCallback(
    (draftId: string) => {
      navigate(`/communications/drafts/${draftId}`);
    },
    [navigate]
  );

  const hasEntries = data && data.entries.length > 0;

  return (
    <div className="flex-1 overflow-y-auto p-8">
      {/* Header with back button */}
      <div className="mb-6">
        <button
          onClick={onBack}
          className={cn(
            "flex items-center gap-2 text-sm font-medium transition-colors mb-3",
            "hover:opacity-80"
          )}
          style={{ color: "var(--text-secondary)" }}
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Communications
        </button>

        <div className="flex items-center gap-3 mb-1">
          {/* Avatar */}
          <div
            className="w-10 h-10 rounded-full flex items-center justify-center"
            style={{ backgroundColor: "var(--bg-subtle)" }}
          >
            <Mail className="w-5 h-5" style={{ color: "var(--text-secondary)" }} />
          </div>

          <div>
            <h1
              className="font-display text-2xl italic"
              style={{ color: "var(--text-primary)" }}
            >
              {data?.contact_name || contactEmail}
            </h1>
            {data?.contact_name && (
              <p
                className="text-sm"
                style={{ color: "var(--text-secondary)" }}
              >
                {contactEmail}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Pipeline context */}
      {data?.pipeline_context && data.pipeline_context.company_name && (
        <div
          className="flex flex-wrap items-center gap-3 mb-4 p-3 rounded-lg border"
          style={{ borderColor: 'var(--accent)', backgroundColor: 'color-mix(in srgb, var(--accent) 5%, var(--bg-elevated))' }}
        >
          <div className="flex items-center gap-2">
            <Building2 className="w-4 h-4" style={{ color: 'var(--accent)' }} />
            <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
              {data.pipeline_context.company_name}
            </span>
          </div>
          {data.pipeline_context.relationship_type && (
            <>
              <div className="w-px h-4 bg-[var(--border)]" />
              <span
                className="text-xs px-2 py-0.5 rounded-full font-medium"
                style={{ backgroundColor: 'var(--bg-subtle)', color: 'var(--text-secondary)' }}
              >
                {data.pipeline_context.relationship_type.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase())}
              </span>
            </>
          )}
          {data.pipeline_context.lifecycle_stage && (
            <>
              <div className="w-px h-4 bg-[var(--border)]" />
              <div className="flex items-center gap-1">
                <TrendingUp className="w-3.5 h-3.5" style={{ color: 'var(--text-secondary)' }} />
                <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                  {data.pipeline_context.lifecycle_stage.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase())}
                </span>
              </div>
            </>
          )}
          {data.pipeline_context.health_score != null && (
            <>
              <div className="w-px h-4 bg-[var(--border)]" />
              <div className="flex items-center gap-1">
                <Heart className="w-3.5 h-3.5" style={{ color: data.pipeline_context.health_score >= 70 ? 'var(--success)' : data.pipeline_context.health_score >= 40 ? '#d97706' : 'var(--critical)' }} />
                <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                  Health: {data.pipeline_context.health_score}
                </span>
              </div>
            </>
          )}
        </div>
      )}

      {/* Stats bar */}
      {data && (
        <div
          className="flex items-center gap-4 mb-6 p-3 rounded-lg border"
          style={{ borderColor: "var(--border)", backgroundColor: "var(--bg-subtle)" }}
        >
          <div className="flex items-center gap-2">
            <Inbox className="w-4 h-4" style={{ color: "var(--text-secondary)" }} />
            <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
              <strong style={{ color: "var(--text-primary)" }}>{data.received_count}</strong> received
            </span>
          </div>
          <div className="w-px h-4 bg-[var(--border)]" />
          <div className="flex items-center gap-2">
            <Send className="w-4 h-4" style={{ color: "var(--text-secondary)" }} />
            <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
              <strong style={{ color: "var(--text-primary)" }}>{data.sent_count}</strong> sent
            </span>
          </div>
          <div className="w-px h-4 bg-[var(--border)]" />
          <div className="flex items-center gap-2">
            <FileText className="w-4 h-4" style={{ color: "var(--text-secondary)" }} />
            <span className="text-sm" style={{ color: "var(--text-secondary)" }}>
              <strong style={{ color: "var(--text-primary)" }}>{data.draft_count}</strong> pending
            </span>
          </div>
        </div>
      )}

      {/* Content */}
      {isLoading ? (
        <HistorySkeleton />
      ) : error ? (
        <div
          className="text-center py-8"
          style={{ color: "var(--text-secondary)" }}
        >
          <AlertCircle className="w-8 h-8 mx-auto mb-2" style={{ color: "var(--critical)" }} />
          <p className="font-medium" style={{ color: "var(--text-primary)" }}>
            Failed to load contact history
          </p>
          <p className="text-sm mt-1">{error}</p>
          <button
            onClick={onBack}
            className="mt-4 px-4 py-2 rounded-lg text-sm font-medium transition-colors"
            style={{
              backgroundColor: "var(--bg-subtle)",
              color: "var(--text-primary)",
            }}
          >
            Go Back
          </button>
        </div>
      ) : !hasEntries ? (
        <EmptyState
          title="No communications yet."
          description={`No emails or drafts found for ${contactEmail}. Communications will appear here once you exchange emails with this contact.`}
          icon={<MailOpen className="w-8 h-8" />}
        />
      ) : (
        <div className="space-y-3">
          {data?.entries.map((entry, index) => (
            <TimelineEntry
              key={`${entry.type}-${entry.timestamp}-${index}`}
              entry={entry}
              onDraftClick={handleDraftClick}
            />
          ))}
        </div>
      )}
    </div>
  );
}
