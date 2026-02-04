import {
  Activity,
  Calendar,
  Mail,
  MailOpen,
  MessageSquare,
  Phone,
  Signal,
  Video,
} from "lucide-react";
import type { LeadEvent, EventType } from "@/api/leads";

interface ActivityTabProps {
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

// Event type labels
const eventLabels: Record<EventType, string> = {
  email_sent: "Email Sent",
  email_received: "Email Received",
  meeting: "Meeting",
  call: "Call",
  note: "Note",
  signal: "Signal",
};

// Map event types to icon colors
const eventIconColors: Record<EventType, string> = {
  email_sent: "text-blue-400",
  email_received: "text-cyan-400",
  meeting: "text-purple-400",
  call: "text-green-400",
  note: "text-amber-400",
  signal: "text-rose-400",
};

interface DateGroup {
  label: string;
  events: LeadEvent[];
}

function groupEventsByDate(events: LeadEvent[]): DateGroup[] {
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const yesterday = new Date(today.getTime() - 24 * 60 * 60 * 1000);

  const groups: Map<string, LeadEvent[]> = new Map();

  // Sort events by occurred_at descending
  const sortedEvents = [...events].sort(
    (a, b) => new Date(b.occurred_at).getTime() - new Date(a.occurred_at).getTime()
  );

  for (const event of sortedEvents) {
    const eventDate = new Date(event.occurred_at);
    const eventDay = new Date(eventDate.getFullYear(), eventDate.getMonth(), eventDate.getDate());

    let label: string;
    if (eventDay.getTime() === today.getTime()) {
      label = "Today";
    } else if (eventDay.getTime() === yesterday.getTime()) {
      label = "Yesterday";
    } else {
      label = eventDate.toLocaleDateString("en-US", {
        month: "long",
        day: "numeric",
        year: eventDate.getFullYear() !== now.getFullYear() ? "numeric" : undefined,
      });
    }

    if (!groups.has(label)) {
      groups.set(label, []);
    }
    groups.get(label)!.push(event);
  }

  return Array.from(groups.entries()).map(([label, events]) => ({
    label,
    events,
  }));
}

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMinutes = Math.floor(diffMs / (1000 * 60));
  const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffMinutes < 1) {
    return "Just now";
  } else if (diffMinutes < 60) {
    return `${diffMinutes}m ago`;
  } else if (diffHours < 24) {
    return `${diffHours}h ago`;
  } else if (diffDays === 1) {
    return "Yesterday";
  } else if (diffDays < 7) {
    return `${diffDays}d ago`;
  } else {
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    });
  }
}

interface ActivityRowProps {
  event: LeadEvent;
}

function ActivityRow({ event }: ActivityRowProps) {
  const Icon = eventIcons[event.event_type];
  const label = eventLabels[event.event_type];
  const iconColor = eventIconColors[event.event_type];
  const maxParticipantsShown = 2;

  const truncatedParticipants = event.participants.slice(0, maxParticipantsShown);
  const remainingCount = event.participants.length - maxParticipantsShown;

  return (
    <div className="flex items-center gap-3 py-2.5 px-3 hover:bg-slate-800/30 rounded-lg transition-colors cursor-pointer group">
      {/* Small icon */}
      <div className="shrink-0">
        <Icon className={`w-3.5 h-3.5 ${iconColor}`} />
      </div>

      {/* Event info */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-sm text-slate-300 font-medium truncate">
            {label}
          </span>
          {event.subject && (
            <>
              <span className="text-slate-600">-</span>
              <span className="text-sm text-slate-400 truncate">{event.subject}</span>
            </>
          )}
        </div>
      </div>

      {/* Participants (truncated) */}
      {event.participants.length > 0 && (
        <div className="hidden sm:flex items-center gap-1 shrink-0 max-w-[180px]">
          <span className="text-xs text-slate-500 truncate">
            {truncatedParticipants.join(", ")}
            {remainingCount > 0 && ` +${remainingCount}`}
          </span>
        </div>
      )}

      {/* Relative timestamp */}
      <div className="shrink-0 text-xs text-slate-500 group-hover:text-slate-400 transition-colors">
        {formatRelativeTime(event.occurred_at)}
      </div>
    </div>
  );
}

interface DateGroupHeaderProps {
  label: string;
}

function DateGroupHeader({ label }: DateGroupHeaderProps) {
  return (
    <div className="flex items-center gap-3 py-3">
      <div className="flex items-center gap-2 shrink-0">
        <Calendar className="w-3.5 h-3.5 text-slate-500" />
        <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
          {label}
        </span>
      </div>
      <div className="flex-1 h-px bg-slate-700/50" />
    </div>
  );
}

function ActivitySkeleton() {
  return (
    <div className="space-y-4">
      {[...Array(3)].map((_, groupIdx) => (
        <div key={groupIdx}>
          {/* Date header skeleton */}
          <div className="flex items-center gap-3 py-3 animate-pulse">
            <div className="flex items-center gap-2">
              <div className="w-3.5 h-3.5 bg-slate-700 rounded" />
              <div className="h-3 w-16 bg-slate-700 rounded" />
            </div>
            <div className="flex-1 h-px bg-slate-700/50" />
          </div>

          {/* Activity rows skeleton */}
          <div className="space-y-1">
            {[...Array(3)].map((_, rowIdx) => (
              <div
                key={rowIdx}
                className="flex items-center gap-3 py-2.5 px-3 animate-pulse"
              >
                <div className="w-3.5 h-3.5 bg-slate-700 rounded shrink-0" />
                <div className="flex-1 flex items-center gap-2">
                  <div className="h-4 w-20 bg-slate-700 rounded" />
                  <div className="h-4 w-32 bg-slate-700 rounded" />
                </div>
                <div className="h-3 w-12 bg-slate-700 rounded shrink-0" />
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function EmptyActivity() {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4">
      <div className="w-16 h-16 bg-slate-800/50 rounded-2xl flex items-center justify-center mb-4 border border-slate-700/50">
        <Activity className="w-8 h-8 text-slate-500" />
      </div>
      <h3 className="text-lg font-semibold text-white mb-2">No activity yet</h3>
      <p className="text-slate-400 text-center max-w-sm">
        Activity will appear here as you interact with this lead through emails, meetings, and calls.
      </p>
    </div>
  );
}

export function ActivityTab({ events, isLoading }: ActivityTabProps) {
  if (isLoading) {
    return <ActivitySkeleton />;
  }

  if (events.length === 0) {
    return <EmptyActivity />;
  }

  const groupedEvents = groupEventsByDate(events);

  return (
    <div className="space-y-2">
      {groupedEvents.map((group) => (
        <div key={group.label}>
          <DateGroupHeader label={group.label} />
          <div className="space-y-0.5">
            {group.events.map((event) => (
              <ActivityRow key={event.id} event={event} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
