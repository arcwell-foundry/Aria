import {
  Calendar,
  Mail,
  MailOpen,
  MessageSquare,
  Phone,
  Signal,
  Video,
} from "lucide-react";
import type { LeadEvent, EventType } from "@/api/leads";

interface TimelineTabProps {
  events: LeadEvent[];
  isLoading: boolean;
}

// Map event types to icons
const eventIcons: Record<EventType, React.ComponentType<{ className?: string }>> = {
  email_sent: Mail,
  email_received: MailOpen,
  meeting: Video,
  call: Phone,
  note: MessageSquare,
  signal: Signal,
};

// Map event types to colors
const eventColors: Record<EventType, { bg: string; icon: string; line: string }> = {
  email_sent: {
    bg: "bg-info/20",
    icon: "text-info",
    line: "bg-info/30",
  },
  email_received: {
    bg: "bg-cyan-500/20",
    icon: "text-cyan-400",
    line: "bg-cyan-500/30",
  },
  meeting: {
    bg: "bg-purple-500/20",
    icon: "text-purple-400",
    line: "bg-purple-500/30",
  },
  call: {
    bg: "bg-green-500/20",
    icon: "text-green-400",
    line: "bg-green-500/30",
  },
  note: {
    bg: "bg-warning/20",
    icon: "text-warning",
    line: "bg-warning/30",
  },
  signal: {
    bg: "bg-rose-500/20",
    icon: "text-rose-400",
    line: "bg-rose-500/30",
  },
};

// Event type labels
const eventLabels: Record<EventType, string> = {
  email_sent: "Email Sent",
  email_received: "Email Received",
  meeting: "Meeting",
  call: "Call",
  note: "Note",
  signal: "Signal Detected",
};

function formatTimestamp(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    return date.toLocaleTimeString("en-US", {
      hour: "numeric",
      minute: "2-digit",
      hour12: true,
    });
  } else if (diffDays === 1) {
    return "Yesterday";
  } else if (diffDays < 7) {
    return date.toLocaleDateString("en-US", { weekday: "long" });
  } else {
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
      year: date.getFullYear() !== now.getFullYear() ? "numeric" : undefined,
    });
  }
}

interface TimelineEventProps {
  event: LeadEvent;
  isLast: boolean;
}

function TimelineEvent({ event, isLast }: TimelineEventProps) {
  const Icon = eventIcons[event.event_type];
  const colors = eventColors[event.event_type];
  const label = eventLabels[event.event_type];
  const maxParticipantsShown = 3;

  return (
    <div className="relative flex gap-4">
      {/* Timeline connector */}
      <div className="flex flex-col items-center">
        <div
          className={`w-10 h-10 rounded-xl ${colors.bg} flex items-center justify-center shrink-0`}
        >
          <Icon className={`w-5 h-5 ${colors.icon}`} />
        </div>
        {!isLast && (
          <div className={`w-0.5 flex-1 mt-2 ${colors.line} min-h-[24px]`} />
        )}
      </div>

      {/* Event content */}
      <div className="flex-1 pb-6">
        <div className="flex items-center gap-2 mb-1">
          <span className="text-sm font-medium text-slate-300">{label}</span>
          <span className="text-xs text-slate-500">
            {formatTimestamp(event.occurred_at)}
          </span>
        </div>

        {event.subject && (
          <h4 className="text-white font-medium mb-1">{event.subject}</h4>
        )}

        {event.content && (
          <p className="text-sm text-slate-400 line-clamp-3 mb-2">
            {event.content}
          </p>
        )}

        {/* Participant badges */}
        {event.participants.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-2">
            {event.participants.slice(0, maxParticipantsShown).map((participant, idx) => (
              <span
                key={idx}
                className="inline-flex items-center px-2 py-0.5 bg-slate-700/50 text-slate-300 text-xs rounded-full"
              >
                {participant}
              </span>
            ))}
            {event.participants.length > maxParticipantsShown && (
              <span className="inline-flex items-center px-2 py-0.5 bg-slate-700/50 text-slate-400 text-xs rounded-full">
                +{event.participants.length - maxParticipantsShown}
              </span>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function TimelineSkeleton() {
  return (
    <div className="space-y-0">
      {[...Array(4)].map((_, i) => (
        <div key={i} className="relative flex gap-4 animate-pulse">
          {/* Timeline connector skeleton */}
          <div className="flex flex-col items-center">
            <div className="w-10 h-10 bg-slate-700 rounded-xl shrink-0" />
            {i < 3 && (
              <div className="w-0.5 flex-1 mt-2 bg-slate-700 min-h-[24px]" />
            )}
          </div>

          {/* Content skeleton */}
          <div className="flex-1 pb-6">
            <div className="flex items-center gap-2 mb-2">
              <div className="h-4 bg-slate-700 rounded w-20" />
              <div className="h-3 bg-slate-700 rounded w-16" />
            </div>
            <div className="h-5 bg-slate-700 rounded w-3/4 mb-2" />
            <div className="h-4 bg-slate-700 rounded w-full mb-1" />
            <div className="h-4 bg-slate-700 rounded w-2/3" />
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyTimeline() {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4">
      <div className="w-16 h-16 bg-slate-800/50 rounded-2xl flex items-center justify-center mb-4 border border-slate-700/50">
        <Calendar className="w-8 h-8 text-slate-500" />
      </div>
      <h3 className="text-lg font-semibold text-white mb-2">No activity yet</h3>
      <p className="text-slate-400 text-center max-w-sm">
        Events will appear here as you interact with this lead through emails, meetings, and calls.
      </p>
    </div>
  );
}

export function TimelineTab({ events, isLoading }: TimelineTabProps) {
  if (isLoading) {
    return <TimelineSkeleton />;
  }

  if (events.length === 0) {
    return <EmptyTimeline />;
  }

  // Sort events by occurred_at descending (most recent first)
  const sortedEvents = [...events].sort(
    (a, b) => new Date(b.occurred_at).getTime() - new Date(a.occurred_at).getTime()
  );

  return (
    <div className="space-y-0">
      {sortedEvents.map((event, index) => (
        <TimelineEvent
          key={event.id}
          event={event}
          isLast={index === sortedEvents.length - 1}
        />
      ))}
    </div>
  );
}
