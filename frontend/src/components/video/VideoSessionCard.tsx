/**
 * VideoSessionCard - Individual session card with expandable details.
 *
 * Displays session metadata with perception insights on expand.
 * Design: Intelligence briefing aesthetic — precise, data-rich, confident.
 */

import { useState } from "react";
import {
  MessageSquare,
  Target,
  ClipboardList,
  Lightbulb,
  Eye,
  Heart,
  AlertTriangle,
  ChevronDown,
  Clock,
  Calendar,
  Video,
  Users,
  Sparkles,
} from "lucide-react";
import type { VideoSession, SessionType, VideoSessionStatus } from "@/api/video";
import { Badge } from "@/components/primitives/Badge";

// Session type configuration
const SESSION_TYPE_CONFIG: Record<
  SessionType,
  { icon: typeof MessageSquare; label: string; color: string }
> = {
  chat: { icon: MessageSquare, label: "Chat", color: "text-blue-400" },
  briefing: { icon: Target, label: "Briefing", color: "text-amber-400" },
  debrief: { icon: ClipboardList, label: "Debrief", color: "text-emerald-400" },
  consultation: { icon: Lightbulb, label: "Consultation", color: "text-violet-400" },
};

// Status badge mapping
const STATUS_CONFIG: Record<
  VideoSessionStatus,
  { variant: "success" | "warning" | "error" | "default"; label: string }
> = {
  created: { variant: "default", label: "Created" },
  active: { variant: "info" as "default", label: "Active" },
  ended: { variant: "success", label: "Completed" },
  error: { variant: "error", label: "Error" },
};

// Perception analysis type
interface PerceptionInsights {
  engagement_score?: number;
  emotional_trajectory?: string;
  attention_flags?: string[];
  dominant_emotions?: string[];
  distraction_events?: number;
}

/**
 * Parse perception analysis from session data
 */
function parsePerceptionAnalysis(
  perception?: Record<string, unknown>
): PerceptionInsights | null {
  if (!perception) return null;

  return {
    engagement_score:
      typeof perception.engagement_score === "number"
        ? perception.engagement_score
        : typeof perception.user_engagement_score === "number"
          ? perception.user_engagement_score
          : undefined,
    emotional_trajectory:
      typeof perception.emotional_trajectory === "string"
        ? perception.emotional_trajectory
        : typeof perception.emotional_summary === "string"
          ? perception.emotional_summary
          : undefined,
    attention_flags: Array.isArray(perception.attention_flags)
      ? perception.attention_flags.filter((f): f is string => typeof f === "string")
      : undefined,
    dominant_emotions: Array.isArray(perception.dominant_emotions)
      ? perception.dominant_emotions.filter((e): e is string => typeof e === "string")
      : undefined,
    distraction_events:
      typeof perception.distraction_events === "number"
        ? perception.distraction_events
        : undefined,
  };
}

/**
 * Format duration from seconds to human readable
 */
function formatDuration(seconds: number | null): string {
  if (!seconds) return "—";

  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;

  if (mins === 0) return `${secs}s`;
  if (secs === 0) return `${mins}m`;
  return `${mins}m ${secs}s`;
}

/**
 * Format date for display
 */
function formatSessionDate(dateString: string | null): {
  date: string;
  time: string;
  relative: string;
} {
  if (!dateString) {
    return { date: "—", time: "—", relative: "Unknown" };
  }

  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  let relative: string;
  if (diffDays === 0) {
    relative = "Today";
  } else if (diffDays === 1) {
    relative = "Yesterday";
  } else if (diffDays < 7) {
    relative = `${diffDays} days ago`;
  } else {
    relative = date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }

  return {
    date: date.toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
    }),
    time: date.toLocaleTimeString("en-US", {
      hour: "2-digit",
      minute: "2-digit",
    }),
    relative,
  };
}

/**
 * Generate transcript summary from entries
 */
function generateTranscriptSummary(transcripts?: VideoSession["transcripts"]): string {
  if (!transcripts || transcripts.length === 0) {
    return "No transcript available for this session.";
  }

  // Get word count estimate
  const totalWords = transcripts.reduce(
    (sum, t) => sum + t.content.split(/\s+/).length,
    0
  );

  // Extract key topics (simplified - just first 150 chars of last meaningful exchange)
  const lastExchange = transcripts
    .filter((t) => t.content.length > 20)
    .slice(-3)
    .map((t) => t.content)
    .join(" ")
    .slice(0, 150);

  return `${transcripts.length} exchanges recorded (~${totalWords} words). Last discussed: "${lastExchange}..."`;
}

/**
 * Extract key topics from transcript (simplified heuristic)
 */
function extractKeyTopics(transcripts?: VideoSession["transcripts"]): string[] {
  if (!transcripts || transcripts.length === 0) return [];

  // Simplified topic extraction - look for capitalized phrases and repeated terms
  const allContent = transcripts.map((t) => t.content).join(" ");

  // Common business terms to look for
  const topicPatterns = [
    /\b(?:pipeline|forecast|revenue|deal|contract|proposal|lead|prospect)\b/gi,
    /\b(?:Lonza|Catalent|Samsung|Thermo|Merck)\b/gi,
    /\b(?:CDMO|manufacturing|formulation|development)\b/gi,
  ];

  const foundTopics: string[] = [];
  for (const pattern of topicPatterns) {
    const matches = allContent.match(pattern);
    if (matches) {
      foundTopics.push(
        ...[...new Set(matches.map((m) => m.toLowerCase()))].slice(0, 2)
      );
    }
  }

  return [...new Set(foundTopics)].slice(0, 4);
}

/**
 * Generate action items (placeholder - would come from AI analysis)
 */
function extractActionItems(
  transcripts?: VideoSession["transcripts"]
): Array<{ item: string; priority: "high" | "medium" | "low" }> {
  if (!transcripts || transcripts.length === 0) return [];

  // Look for action-oriented phrases
  const actionPhrases = [
    "follow up",
    "send",
    "schedule",
    "prepare",
    "review",
    "call",
    "email",
  ];

  const actions: Array<{ item: string; priority: "high" | "medium" | "low" }> = [];

  for (const t of transcripts) {
    const content = t.content.toLowerCase();
    for (const phrase of actionPhrases) {
      if (content.includes(phrase) && actions.length < 3) {
        // Extract surrounding context
        const idx = content.indexOf(phrase);
        const start = Math.max(0, idx - 20);
        const end = Math.min(t.content.length, idx + 50);
        const context = t.content.slice(start, end).trim();

        if (context.length > 10) {
          actions.push({
            item: context.length > 60 ? context.slice(0, 57) + "..." : context,
            priority: content.includes("urgent") || content.includes("asap")
              ? "high"
              : "medium",
          });
        }
      }
    }
  }

  return actions.slice(0, 3);
}

interface VideoSessionCardProps {
  session: VideoSession;
  defaultExpanded?: boolean;
  className?: string;
  /** Click handler for selecting the session */
  onClick?: () => void;
}

export function VideoSessionCard({
  session,
  defaultExpanded = false,
  className = "",
  onClick,
}: VideoSessionCardProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);

  const typeConfig = SESSION_TYPE_CONFIG[session.session_type];
  const statusConfig = STATUS_CONFIG[session.status];
  const TypeIcon = typeConfig.icon;

  const dateInfo = formatSessionDate(session.started_at || session.created_at);
  const duration = formatDuration(session.duration_seconds);
  const perception = parsePerceptionAnalysis(session.perception_analysis);
  const transcriptSummary = generateTranscriptSummary(session.transcripts);
  const keyTopics = extractKeyTopics(session.transcripts);
  const actionItems = extractActionItems(session.transcripts);

  return (
    <div
      className={`
        bg-elevated border border-border rounded-xl overflow-hidden
        transition-all duration-300 ease-out
        ${isExpanded ? "shadow-lg shadow-black/20" : "hover:border-interactive/30"}
        ${className}
      `}
    >
      {/* Card Header - Always Visible */}
      <button
        type="button"
        onClick={() => {
          setIsExpanded(!isExpanded);
          onClick?.();
        }}
        className="w-full p-4 flex items-center gap-4 text-left hover:bg-subtle/50 transition-colors"
        aria-expanded={isExpanded}
      >
        {/* Session Type Icon */}
        <div
          className={`
            w-10 h-10 rounded-lg flex items-center justify-center
            bg-subtle/50 border border-white/5
            ${typeConfig.color}
          `}
        >
          <TypeIcon size={20} />
        </div>

        {/* Session Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="font-medium text-content truncate">
              {typeConfig.label} Session
            </span>
            <Badge variant={statusConfig.variant} size="sm">
              {statusConfig.label}
            </Badge>
          </div>

          <div className="flex items-center gap-3 text-xs text-secondary font-mono">
            <span className="flex items-center gap-1">
              <Calendar size={12} />
              {dateInfo.relative}
            </span>
            <span className="flex items-center gap-1">
              <Clock size={12} />
              {dateInfo.time}
            </span>
            <span className="flex items-center gap-1">
              <Video size={12} />
              {duration}
            </span>
          </div>
        </div>

        {/* Expand Indicator */}
        <ChevronDown
          size={18}
          className={`
            text-secondary transition-transform duration-200
            ${isExpanded ? "rotate-180" : ""}
          `}
        />
      </button>

      {/* Expanded Content */}
      <div
        className={`
          transition-all duration-300 ease-out overflow-hidden
          ${isExpanded ? "max-h-[800px] opacity-100" : "max-h-0 opacity-0"}
        `}
      >
        <div className="px-4 pb-4 space-y-4 border-t border-border/50 pt-4">
          {/* Transcript Summary */}
          <div className="space-y-2">
            <h4 className="text-xs font-semibold text-secondary uppercase tracking-wider flex items-center gap-2">
              <MessageSquare size={12} />
              Transcript Summary
            </h4>
            <p className="text-sm text-content/80 leading-relaxed">
              {transcriptSummary}
            </p>
          </div>

          {/* Key Topics */}
          {keyTopics.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-semibold text-secondary uppercase tracking-wider flex items-center gap-2">
                <Sparkles size={12} />
                Key Topics
              </h4>
              <div className="flex flex-wrap gap-2">
                {keyTopics.map((topic, idx) => (
                  <span
                    key={idx}
                    className="px-2 py-1 text-xs bg-accent/10 text-accent rounded-md font-mono"
                  >
                    {topic}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Action Items */}
          {actionItems.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-semibold text-secondary uppercase tracking-wider flex items-center gap-2">
                <ClipboardList size={12} />
                Action Items
              </h4>
              <ul className="space-y-1.5">
                {actionItems.map((action, idx) => (
                  <li
                    key={idx}
                    className="flex items-start gap-2 text-sm text-content/80"
                  >
                    <span
                      className={`
                        w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0
                        ${action.priority === "high" ? "bg-critical" : "bg-warning"}
                      `}
                    />
                    <span className="capitalize">{action.item}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Raven-1 Perception Insights */}
          {perception && (
            <div className="space-y-3 pt-2 border-t border-border/30">
              <h4 className="text-xs font-semibold text-secondary uppercase tracking-wider flex items-center gap-2">
                <Eye size={12} />
                Raven-1 Perception Insights
              </h4>

              <div className="grid grid-cols-2 gap-3">
                {/* Engagement Score */}
                {perception.engagement_score !== undefined && (
                  <div className="bg-subtle/30 rounded-lg p-3 border border-white/5">
                    <div className="flex items-center gap-2 mb-1.5">
                      <Users size={14} className="text-accent" />
                      <span className="text-xs text-secondary">Engagement</span>
                    </div>
                    <div className="flex items-baseline gap-1">
                      <span className="text-xl font-semibold text-content font-mono">
                        {Math.round(perception.engagement_score * 100)}
                      </span>
                      <span className="text-xs text-secondary">% screen time</span>
                    </div>
                    <div className="mt-2 h-1.5 bg-subtle rounded-full overflow-hidden">
                      <div
                        className="h-full bg-accent rounded-full transition-all duration-500"
                        style={{ width: `${perception.engagement_score * 100}%` }}
                      />
                    </div>
                  </div>
                )}

                {/* Distraction Events */}
                {perception.distraction_events !== undefined && (
                  <div className="bg-subtle/30 rounded-lg p-3 border border-white/5">
                    <div className="flex items-center gap-2 mb-1.5">
                      <AlertTriangle
                        size={14}
                        className={
                          perception.distraction_events > 3
                            ? "text-warning"
                            : "text-secondary"
                        }
                      />
                      <span className="text-xs text-secondary">Distractions</span>
                    </div>
                    <div className="flex items-baseline gap-1">
                      <span
                        className={`
                          text-xl font-semibold font-mono
                          ${perception.distraction_events > 3 ? "text-warning" : "text-content"}
                        `}
                      >
                        {perception.distraction_events}
                      </span>
                      <span className="text-xs text-secondary">events detected</span>
                    </div>
                  </div>
                )}
              </div>

              {/* Emotional Trajectory */}
              {perception.emotional_trajectory && (
                <div className="bg-subtle/30 rounded-lg p-3 border border-white/5">
                  <div className="flex items-center gap-2 mb-2">
                    <Heart size={14} className="text-pink-400" />
                    <span className="text-xs text-secondary">Emotional Trajectory</span>
                  </div>
                  <p className="text-sm text-content/80 leading-relaxed">
                    {perception.emotional_trajectory}
                  </p>
                </div>
              )}

              {/* Attention Flags */}
              {perception.attention_flags &&
                perception.attention_flags.length > 0 && (
                  <div className="space-y-1.5">
                    <span className="text-xs text-secondary">Attention Flags:</span>
                    <div className="flex flex-wrap gap-1.5">
                      {perception.attention_flags.map((flag, idx) => (
                        <span
                          key={idx}
                          className="px-2 py-0.5 text-xs bg-warning/10 text-warning rounded font-mono"
                        >
                          {flag}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

              {/* Dominant Emotions */}
              {perception.dominant_emotions &&
                perception.dominant_emotions.length > 0 && (
                  <div className="space-y-1.5">
                    <span className="text-xs text-secondary">Emotions Detected:</span>
                    <div className="flex flex-wrap gap-1.5">
                      {perception.dominant_emotions.map((emotion, idx) => (
                        <span
                          key={idx}
                          className="px-2 py-0.5 text-xs bg-pink-500/10 text-pink-400 rounded capitalize"
                        >
                          {emotion}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
            </div>
          )}

          {/* No perception data message */}
          {!perception && (
            <div className="text-center py-4 text-xs text-secondary italic">
              No perception analysis available for this session.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
