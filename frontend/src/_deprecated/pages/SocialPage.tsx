import { useMemo, useState } from "react";
import type { SocialDraft, PostVariation } from "@/api/social";
import { DashboardLayout } from "@/components/DashboardLayout";
import { HelpTooltip } from "@/components/HelpTooltip";
import {
  useSocialDrafts,
  useSocialPublished,
  useSocialStats,
  useApproveDraft,
  useRejectDraft,
  usePublishDraft,
  useScheduleDraft,
} from "@/hooks/useSocial";
import {
  Share2,
  Clock,
  Send,
  ThumbsUp,
  MessageSquare,
  Repeat2,
  Eye,
  X,
  Check,
  Calendar,
  Hash,
  Sparkles,
  BookOpen,
  HelpCircle,
  Target,
  Handshake,
  ChevronDown,
  Loader2,
} from "lucide-react";

// ---------- Types ----------

type SectionTab = "drafts" | "scheduled" | "published";

interface RejectModalState {
  isOpen: boolean;
  draftId: string | null;
}

// ---------- Helpers ----------

const VARIATION_LABELS: Record<PostVariation["variation_type"], { label: string; icon: typeof Sparkles }> = {
  insight: { label: "Hot Take", icon: Sparkles },
  educational: { label: "Educational", icon: BookOpen },
  engagement: { label: "Question", icon: HelpCircle },
};

const TRIGGER_BADGES: Record<string, { label: string; className: string }> = {
  signal: { label: "Signal", className: "bg-blue-500/20 text-blue-400 border-blue-500/30" },
  meeting: { label: "Meeting", className: "bg-purple-500/20 text-purple-400 border-purple-500/30" },
  curation: { label: "Curation", className: "bg-amber-500/20 text-amber-400 border-amber-500/30" },
  milestone: { label: "Milestone", className: "bg-green-500/20 text-green-400 border-green-500/30" },
  cadence: { label: "Cadence", className: "bg-slate-500/20 text-slate-400 border-slate-500/30" },
};

const PRESET_REJECT_REASONS = [
  "Not the right tone",
  "Topic not relevant right now",
  "Too promotional",
  "Bad timing",
  "I want to write this myself",
];

function getNextOptimalTime(): string {
  const now = new Date();
  const day = now.getUTCDay();
  let daysUntilNext: number;

  // Tuesday = 2, Wednesday = 3
  if (day < 2) {
    daysUntilNext = 2 - day;
  } else if (day < 3) {
    daysUntilNext = 3 - day;
  } else {
    // Next Tuesday
    daysUntilNext = (2 + 7 - day) % 7;
    if (daysUntilNext === 0) daysUntilNext = 7;
  }

  const target = new Date(now);
  target.setUTCDate(target.getUTCDate() + daysUntilNext);
  target.setUTCHours(14, 0, 0, 0); // 14:00 UTC = 9am EST
  return target.toISOString();
}

function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = date.getTime() - now.getTime();

  if (diffMs < 0) return "Overdue";

  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffHours / 24);

  if (diffDays > 0) return `in ${diffDays}d ${diffHours % 24}h`;
  if (diffHours > 0) return `in ${diffHours}h`;
  const diffMin = Math.floor(diffMs / (1000 * 60));
  return `in ${diffMin}m`;
}

function formatDateTime(dateStr: string): string {
  return new Date(dateStr).toLocaleString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

// ---------- Stat Pill ----------

function StatPill({ icon, value, label }: { icon: React.ReactNode; value: number; label: string }) {
  return (
    <div className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-slate-700/50 rounded-full text-sm">
      {icon}
      <span className="text-white font-medium">{value.toLocaleString()}</span>
      <span className="text-slate-400">{label}</span>
    </div>
  );
}

// ---------- Draft Card ----------

interface DraftCardProps {
  draft: SocialDraft;
  onApproveSchedule: (draftId: string, variationIndex: number, text: string, hashtags: string[], scheduledTime: string) => void;
  onPublishNow: (draftId: string, variationIndex: number, text: string, hashtags: string[]) => void;
  onReject: (draftId: string) => void;
}

function DraftCard({ draft, onApproveSchedule, onPublishNow, onReject }: DraftCardProps) {
  const [selectedVariation, setSelectedVariation] = useState(
    draft.metadata.selected_variation_index ?? 0
  );
  const [editedText, setEditedText] = useState<string | null>(null);
  const [editedHashtags, setEditedHashtags] = useState<string[] | null>(null);
  const [showSchedulePicker, setShowSchedulePicker] = useState(false);
  const [scheduleTime, setScheduleTime] = useState(
    draft.metadata.suggested_time || getNextOptimalTime()
  );

  const variation = draft.metadata.variations[selectedVariation];
  if (!variation) return null;

  const currentText = editedText ?? variation.text;
  const currentHashtags = editedHashtags ?? variation.hashtags;
  const triggerBadge = TRIGGER_BADGES[draft.metadata.trigger_type] || TRIGGER_BADGES.cadence;

  const handleRemoveHashtag = (index: number) => {
    const next = [...currentHashtags];
    next.splice(index, 1);
    setEditedHashtags(next);
  };

  const handleVariationChange = (index: number) => {
    setSelectedVariation(index);
    setEditedText(null);
    setEditedHashtags(null);
  };

  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-5">
      {/* Header row */}
      <div className="flex items-start justify-between gap-3 mb-4">
        <div className="flex items-center gap-2 flex-wrap">
          <span className={`inline-flex items-center px-2.5 py-1 text-xs font-medium rounded-full border ${triggerBadge.className}`}>
            {triggerBadge.label}
          </span>
          <span className="text-xs text-slate-500">
            {draft.metadata.trigger_source}
          </span>
        </div>
        <div className="flex items-center gap-1.5 text-xs text-slate-500">
          <Clock className="w-3.5 h-3.5" />
          {formatDateTime(draft.created_at)}
        </div>
      </div>

      {/* Variation toggle */}
      <div className="flex gap-2 mb-4">
        {draft.metadata.variations.map((v, i) => {
          const config = VARIATION_LABELS[v.variation_type];
          const Icon = config.icon;
          return (
            <button
              key={v.variation_type}
              onClick={() => handleVariationChange(i)}
              className={`inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${
                selectedVariation === i
                  ? "bg-primary-600/20 text-primary-400 border border-primary-500/30"
                  : "text-slate-400 hover:text-white hover:bg-slate-700 border border-transparent"
              }`}
            >
              <Icon className="w-3.5 h-3.5" />
              {config.label}
            </button>
          );
        })}
      </div>

      {/* Editable post text */}
      <textarea
        value={currentText}
        onChange={(e) => setEditedText(e.target.value)}
        rows={5}
        className="w-full bg-slate-900/50 border border-slate-600 rounded-lg px-4 py-3 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500/40 focus:border-primary-500/50 resize-y mb-3"
      />

      {/* Voice match confidence */}
      <div className="flex items-center gap-2 mb-3 text-xs text-slate-500">
        <Sparkles className="w-3.5 h-3.5" />
        <span>Voice match: {Math.round(variation.voice_match_confidence * 100)}%</span>
      </div>

      {/* Hashtag chips */}
      {currentHashtags.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-4">
          {currentHashtags.map((tag, i) => (
            <span
              key={`${tag}-${i}`}
              className="inline-flex items-center gap-1 px-2.5 py-1 bg-slate-700/60 text-slate-300 text-xs rounded-full"
            >
              <Hash className="w-3 h-3 text-slate-500" />
              {tag.replace(/^#/, "")}
              <button
                onClick={() => handleRemoveHashtag(i)}
                className="ml-0.5 text-slate-500 hover:text-slate-300 transition-colors"
              >
                <X className="w-3 h-3" />
              </button>
            </span>
          ))}
        </div>
      )}

      {/* Suggested time */}
      {draft.metadata.suggested_time && (
        <div className="flex items-start gap-2 mb-4 p-3 bg-slate-900/40 rounded-lg border border-slate-700/50">
          <Calendar className="w-4 h-4 text-slate-400 mt-0.5 shrink-0" />
          <div>
            <p className="text-sm text-slate-300">
              Suggested: {formatDateTime(draft.metadata.suggested_time)}
            </p>
            <p className="text-xs text-slate-500 mt-0.5">
              {draft.metadata.suggested_time_reasoning}
            </p>
          </div>
        </div>
      )}

      {/* Schedule picker */}
      {showSchedulePicker && (
        <div className="mb-4 p-3 bg-slate-900/40 rounded-lg border border-slate-700/50">
          <label className="block text-xs text-slate-400 mb-2">Schedule for:</label>
          <input
            type="datetime-local"
            value={scheduleTime.slice(0, 16)}
            onChange={(e) => setScheduleTime(new Date(e.target.value).toISOString())}
            className="w-full bg-slate-800 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-primary-500/40"
          />
        </div>
      )}

      {/* Action buttons */}
      <div className="flex items-center gap-2 pt-2 border-t border-slate-700/50">
        <button
          onClick={() => {
            if (!showSchedulePicker) {
              setShowSchedulePicker(true);
              return;
            }
            onApproveSchedule(draft.id, selectedVariation, currentText, currentHashtags, scheduleTime);
          }}
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-500 text-white text-sm font-medium rounded-lg transition-colors"
        >
          <Calendar className="w-4 h-4" />
          {showSchedulePicker ? "Confirm Schedule" : "Approve & Schedule"}
        </button>
        <button
          onClick={() => onPublishNow(draft.id, selectedVariation, currentText, currentHashtags)}
          className="inline-flex items-center gap-2 px-4 py-2 bg-green-600 hover:bg-green-500 text-white text-sm font-medium rounded-lg transition-colors"
        >
          <Send className="w-4 h-4" />
          Post Now
        </button>
        <button
          onClick={() => onReject(draft.id)}
          className="inline-flex items-center gap-2 px-4 py-2 text-slate-400 hover:text-white hover:bg-slate-700 text-sm font-medium rounded-lg transition-colors ml-auto"
        >
          <X className="w-4 h-4" />
          Reject
        </button>
      </div>
    </div>
  );
}

// ---------- Scheduled Card ----------

interface ScheduledCardProps {
  draft: SocialDraft;
  onCancel: (draftId: string) => void;
}

function ScheduledCard({ draft, onCancel }: ScheduledCardProps) {
  const scheduledTime = draft.metadata.scheduled_time;
  const text = draft.metadata.edited_text || draft.metadata.variations[draft.metadata.selected_variation_index ?? 0]?.text || "";
  const hashtags = draft.metadata.edited_hashtags || draft.metadata.variations[draft.metadata.selected_variation_index ?? 0]?.hashtags || [];

  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-5">
      <div className="flex items-start justify-between gap-3 mb-3">
        <div className="flex items-center gap-2">
          <Clock className="w-4 h-4 text-primary-400" />
          {scheduledTime && (
            <span className="text-sm text-primary-400 font-medium">
              {formatDateTime(scheduledTime)}
            </span>
          )}
          {scheduledTime && (
            <span className="text-xs text-slate-500 px-2 py-0.5 bg-slate-700/50 rounded-full">
              {formatRelativeTime(scheduledTime)}
            </span>
          )}
        </div>
        <button
          onClick={() => onCancel(draft.id)}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
        >
          <X className="w-3.5 h-3.5" />
          Cancel
        </button>
      </div>
      <p className="text-sm text-slate-300 whitespace-pre-wrap mb-3">{text}</p>
      {hashtags.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {hashtags.map((tag, i) => (
            <span key={`${tag}-${i}`} className="text-xs text-slate-500">
              #{tag.replace(/^#/, "")}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------- Published Card ----------

function PublishedCard({ draft }: { draft: SocialDraft }) {
  const text = draft.metadata.published_text || draft.metadata.edited_text || draft.metadata.variations[draft.metadata.selected_variation_index ?? 0]?.text || "";
  const metrics = draft.metadata.engagement_metrics;
  const engagers = draft.metadata.notable_engagers;
  const [showEngagers, setShowEngagers] = useState(false);

  return (
    <div className="bg-slate-800/50 border border-slate-700 rounded-xl p-5">
      {/* Published time */}
      <div className="flex items-center gap-2 mb-3 text-xs text-slate-500">
        <Check className="w-3.5 h-3.5 text-green-400" />
        <span>
          Published {draft.metadata.published_at ? formatDateTime(draft.metadata.published_at) : draft.completed_at ? formatDateTime(draft.completed_at) : ""}
        </span>
      </div>

      {/* Post text */}
      <p className="text-sm text-slate-300 whitespace-pre-wrap mb-4">{text}</p>

      {/* Engagement stat pills */}
      {metrics && (
        <div className="flex flex-wrap gap-2 mb-4">
          <StatPill icon={<ThumbsUp className="w-3.5 h-3.5 text-blue-400" />} value={metrics.likes} label="likes" />
          <StatPill icon={<MessageSquare className="w-3.5 h-3.5 text-green-400" />} value={metrics.comments} label="comments" />
          <StatPill icon={<Repeat2 className="w-3.5 h-3.5 text-purple-400" />} value={metrics.shares} label="shares" />
          <StatPill icon={<Eye className="w-3.5 h-3.5 text-amber-400" />} value={metrics.impressions} label="impressions" />
        </div>
      )}

      {/* Notable engagers */}
      {engagers && engagers.length > 0 && (
        <div>
          <button
            onClick={() => setShowEngagers(!showEngagers)}
            className="inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-white transition-colors mb-2"
          >
            <ChevronDown className={`w-3.5 h-3.5 transition-transform ${showEngagers ? "rotate-180" : ""}`} />
            Notable engagers ({engagers.length})
          </button>
          {showEngagers && (
            <div className="space-y-2 pl-2">
              {engagers.map((engager, i) => (
                <div key={i} className="flex items-center gap-2 text-sm">
                  <div className="w-6 h-6 rounded-full bg-slate-700 flex items-center justify-center text-xs text-slate-300">
                    {engager.name.charAt(0)}
                  </div>
                  <span className="text-slate-300">{engager.name}</span>
                  {engager.lead_id && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-green-500/20 text-green-400 border border-green-500/30">
                      <Target className="w-3 h-3" />
                      Prospect
                    </span>
                  )}
                  {engager.relationship === "customer" && (
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded-full bg-blue-500/20 text-blue-400 border border-blue-500/30">
                      <Handshake className="w-3 h-3" />
                      Customer
                    </span>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ---------- Reject Modal ----------

interface RejectModalProps {
  isOpen: boolean;
  onClose: () => void;
  onConfirm: (reason: string) => void;
}

function RejectModal({ isOpen, onClose, onConfirm }: RejectModalProps) {
  const [selectedReason, setSelectedReason] = useState<string | null>(null);
  const [customReason, setCustomReason] = useState("");

  if (!isOpen) return null;

  const handleConfirm = () => {
    const reason = selectedReason || customReason || "No reason provided";
    onConfirm(reason);
    setSelectedReason(null);
    setCustomReason("");
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} />
      <div className="relative bg-slate-800 border border-slate-700 rounded-xl p-6 w-full max-w-md mx-4 shadow-2xl">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-medium text-white">Reject Draft</h3>
          <button onClick={onClose} className="text-slate-400 hover:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <p className="text-sm text-slate-400 mb-4">
          Why are you rejecting this draft? This helps ARIA learn your preferences.
        </p>

        <div className="space-y-2 mb-4">
          {PRESET_REJECT_REASONS.map((reason) => (
            <button
              key={reason}
              onClick={() => {
                setSelectedReason(reason);
                setCustomReason("");
              }}
              className={`w-full text-left px-3 py-2 text-sm rounded-lg transition-colors ${
                selectedReason === reason
                  ? "bg-primary-600/20 text-primary-400 border border-primary-500/30"
                  : "text-slate-300 hover:bg-slate-700 border border-transparent"
              }`}
            >
              {reason}
            </button>
          ))}
        </div>

        <textarea
          value={customReason}
          onChange={(e) => {
            setCustomReason(e.target.value);
            setSelectedReason(null);
          }}
          placeholder="Or type a custom reason..."
          rows={2}
          className="w-full bg-slate-900/50 border border-slate-600 rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-primary-500/40 mb-4 resize-none"
        />

        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-slate-400 hover:text-white hover:bg-slate-700 rounded-lg transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            disabled={!selectedReason && !customReason.trim()}
            className="px-4 py-2 text-sm bg-red-600 hover:bg-red-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium rounded-lg transition-colors"
          >
            Reject Draft
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------- SocialPage ----------

export function SocialPage() {
  const [sectionTab, setSectionTab] = useState<SectionTab>("drafts");
  const [rejectModal, setRejectModal] = useState<RejectModalState>({ isOpen: false, draftId: null });

  // Queries
  const { data: allDrafts, isLoading: draftsLoading } = useSocialDrafts();
  const { data: publishedDrafts, isLoading: publishedLoading } = useSocialPublished();
  const { data: stats } = useSocialStats();

  // Mutations
  const approveDraft = useApproveDraft();
  const rejectDraft = useRejectDraft();
  const publishDraft = usePublishDraft();
  const scheduleDraft = useScheduleDraft();

  // Derived: separate drafts into pending vs scheduled
  const pendingDrafts = useMemo(
    () => (allDrafts ?? []).filter((d) => d.status === "pending"),
    [allDrafts]
  );

  const scheduledDrafts = useMemo(
    () => (allDrafts ?? []).filter((d) => d.status === "approved" && d.metadata.scheduled_time),
    [allDrafts]
  );

  const published = useMemo(
    () => publishedDrafts ?? [],
    [publishedDrafts]
  );

  // Counts
  const counts = useMemo(() => ({
    drafts: pendingDrafts.length,
    scheduled: scheduledDrafts.length,
    published: published.length,
  }), [pendingDrafts, scheduledDrafts, published]);

  // Handlers
  const handleApproveSchedule = (draftId: string, variationIndex: number, text: string, hashtags: string[], scheduledTime: string) => {
    scheduleDraft.mutate({
      draftId,
      data: {
        selected_variation_index: variationIndex,
        scheduled_time: scheduledTime,
        edited_text: text,
        edited_hashtags: hashtags,
      },
    });
  };

  const handlePublishNow = (draftId: string, variationIndex: number, text: string, hashtags: string[]) => {
    approveDraft.mutate(
      {
        draftId,
        data: {
          selected_variation_index: variationIndex,
          edited_text: text,
          edited_hashtags: hashtags,
        },
      },
      {
        onSuccess: () => {
          publishDraft.mutate(draftId);
        },
      }
    );
  };

  const handleRejectOpen = (draftId: string) => {
    setRejectModal({ isOpen: true, draftId });
  };

  const handleRejectConfirm = (reason: string) => {
    if (rejectModal.draftId) {
      rejectDraft.mutate({ draftId: rejectModal.draftId, reason });
    }
    setRejectModal({ isOpen: false, draftId: null });
  };

  const handleCancelScheduled = (draftId: string) => {
    rejectDraft.mutate({ draftId, reason: "Cancelled scheduled post" });
  };

  const isLoading = draftsLoading || publishedLoading;

  // Section tabs config
  const sectionTabs: { value: SectionTab; label: string; count: number; icon: typeof Clock }[] = [
    { value: "drafts", label: "Drafts", count: counts.drafts, icon: Share2 },
    { value: "scheduled", label: "Scheduled", count: counts.scheduled, icon: Calendar },
    { value: "published", label: "Published", count: counts.published, icon: Check },
  ];

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
                <h1 className="text-3xl font-display text-white">Social</h1>
                <HelpTooltip
                  content="ARIA drafts LinkedIn posts based on your signals, meetings, and industry insights. Review variations, edit, and schedule or publish directly."
                  placement="right"
                />
              </div>
              <p className="mt-1 text-slate-400">
                Manage AI-drafted LinkedIn posts and track engagement
              </p>
            </div>

            {/* Weekly stats summary */}
            {stats && (
              <div className="flex items-center gap-3">
                <div className="bg-slate-800/50 border border-slate-700 rounded-xl px-4 py-2.5 flex items-center gap-3">
                  <div className="text-sm">
                    <span className="text-white font-medium">{stats.posts_this_week}</span>
                    <span className="text-slate-400">/{stats.posting_goal} posts</span>
                  </div>
                  <div className="w-16 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all ${
                        stats.posting_goal_met ? "bg-green-400" : "bg-primary-400"
                      }`}
                      style={{ width: `${Math.min(100, (stats.posts_this_week / Math.max(1, stats.posting_goal)) * 100)}%` }}
                    />
                  </div>
                  {stats.posting_goal_met && (
                    <Check className="w-4 h-4 text-green-400" />
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Channel tabs */}
          <div className="flex gap-2 mb-6">
            <button
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg bg-primary-600/20 text-primary-400 border border-primary-500/30"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                <path d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433c-1.144 0-2.063-.926-2.063-2.065 0-1.138.92-2.063 2.063-2.063 1.14 0 2.064.925 2.064 2.063 0 1.139-.925 2.065-2.064 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"/>
              </svg>
              LinkedIn
            </button>
            <button
              disabled
              className="inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg text-slate-600 cursor-not-allowed"
            >
              More coming soon
            </button>
          </div>

          {/* Section tabs */}
          <div className="flex gap-2 overflow-x-auto pb-2 mb-6">
            {sectionTabs.map((tab) => {
              const TabIcon = tab.icon;
              return (
                <button
                  key={tab.value}
                  onClick={() => setSectionTab(tab.value)}
                  className={`inline-flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg whitespace-nowrap transition-colors ${
                    sectionTab === tab.value
                      ? "bg-primary-600/20 text-primary-400 border border-primary-500/30"
                      : "text-slate-400 hover:text-white hover:bg-slate-800"
                  }`}
                >
                  <TabIcon className="w-4 h-4" />
                  {tab.label}
                  {tab.count > 0 && (
                    <span
                      className={`ml-1 px-1.5 py-0.5 text-xs rounded-full ${
                        sectionTab === tab.value
                          ? "bg-primary-500/20 text-primary-400"
                          : "bg-slate-700 text-slate-400"
                      }`}
                    >
                      {tab.count}
                    </span>
                  )}
                </button>
              );
            })}
          </div>

          {/* Loading state */}
          {isLoading && (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="w-8 h-8 text-primary-400 animate-spin" />
            </div>
          )}

          {/* Drafts section */}
          {!isLoading && sectionTab === "drafts" && (
            <>
              {pendingDrafts.length === 0 ? (
                <div className="text-center py-16">
                  <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-slate-800/80 border border-slate-700 mb-4">
                    <Share2 className="w-8 h-8 text-slate-500" />
                  </div>
                  <h3 className="text-lg font-medium text-white mb-2">No pending drafts</h3>
                  <p className="text-sm text-slate-400 max-w-md mx-auto">
                    ARIA will draft LinkedIn posts when she detects signals, meeting insights, or content opportunities. Check back soon.
                  </p>
                </div>
              ) : (
                <div className="space-y-4">
                  {pendingDrafts.map((draft, index) => (
                    <div
                      key={draft.id}
                      className="animate-in fade-in slide-in-from-bottom-4"
                      style={{ animationDelay: `${index * 50}ms`, animationFillMode: "both" }}
                    >
                      <DraftCard
                        draft={draft}
                        onApproveSchedule={handleApproveSchedule}
                        onPublishNow={handlePublishNow}
                        onReject={handleRejectOpen}
                      />
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {/* Scheduled section */}
          {!isLoading && sectionTab === "scheduled" && (
            <>
              {scheduledDrafts.length === 0 ? (
                <div className="text-center py-16">
                  <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-slate-800/80 border border-slate-700 mb-4">
                    <Calendar className="w-8 h-8 text-slate-500" />
                  </div>
                  <h3 className="text-lg font-medium text-white mb-2">No scheduled posts</h3>
                  <p className="text-sm text-slate-400 max-w-md mx-auto">
                    Approved drafts with a scheduled time will appear here. Approve a draft and pick a time to get started.
                  </p>
                </div>
              ) : (
                <div className="space-y-4">
                  {scheduledDrafts.map((draft, index) => (
                    <div
                      key={draft.id}
                      className="animate-in fade-in slide-in-from-bottom-4"
                      style={{ animationDelay: `${index * 50}ms`, animationFillMode: "both" }}
                    >
                      <ScheduledCard draft={draft} onCancel={handleCancelScheduled} />
                    </div>
                  ))}
                </div>
              )}
            </>
          )}

          {/* Published section */}
          {!isLoading && sectionTab === "published" && (
            <>
              {published.length === 0 ? (
                <div className="text-center py-16">
                  <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-slate-800/80 border border-slate-700 mb-4">
                    <Check className="w-8 h-8 text-slate-500" />
                  </div>
                  <h3 className="text-lg font-medium text-white mb-2">No published posts yet</h3>
                  <p className="text-sm text-slate-400 max-w-md mx-auto">
                    Published LinkedIn posts and their engagement metrics will appear here.
                  </p>
                </div>
              ) : (
                <div className="space-y-4">
                  {published.map((draft, index) => (
                    <div
                      key={draft.id}
                      className="animate-in fade-in slide-in-from-bottom-4"
                      style={{ animationDelay: `${index * 50}ms`, animationFillMode: "both" }}
                    >
                      <PublishedCard draft={draft} />
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>

        {/* Reject modal */}
        <RejectModal
          isOpen={rejectModal.isOpen}
          onClose={() => setRejectModal({ isOpen: false, draftId: null })}
          onConfirm={handleRejectConfirm}
        />
      </div>
    </DashboardLayout>
  );
}
