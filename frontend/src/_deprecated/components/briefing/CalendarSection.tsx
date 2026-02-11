import { Calendar, Clock, FileText, Users } from "lucide-react";
import { Link } from "react-router-dom";
import type { BriefingCalendar } from "@/api/briefings";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";

interface CalendarSectionProps {
  calendar?: BriefingCalendar;
}

export function CalendarSection({ calendar }: CalendarSectionProps) {
  const { meeting_count = 0, key_meetings = [] } = calendar ?? {};

  if (meeting_count === 0) {
    return (
      <CollapsibleSection
        title="Calendar"
        icon={<Calendar className="w-5 h-5" />}
        badge={0}
        badgeColor="slate"
      >
        <div className="text-center py-6 text-slate-400">
          <Calendar className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p>No meetings scheduled for today</p>
        </div>
      </CollapsibleSection>
    );
  }

  return (
    <CollapsibleSection
      title="Calendar"
      icon={<Calendar className="w-5 h-5" />}
      badge={meeting_count}
      badgeColor="primary"
    >
      <div className="space-y-3">
        {key_meetings.map((meeting, index) => {
          // Generate a calendar event ID from meeting data for linking
          const calendarEventId = meeting.title
            ? encodeURIComponent(meeting.title.toLowerCase().replace(/\s+/g, "-"))
            : `meeting-${index}`;

          return (
            <div
              key={index}
              className="flex items-start gap-4 p-3 bg-slate-700/30 border border-slate-600/30 rounded-lg group"
            >
              <div className="flex-shrink-0 flex items-center justify-center w-12 h-12 bg-primary-500/10 border border-primary-500/20 rounded-lg">
                <Clock className="w-5 h-5 text-primary-400" />
              </div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-primary-400">{meeting.time}</span>
                </div>
                <h4 className="text-white font-medium truncate">{meeting.title}</h4>
                {meeting.attendees && meeting.attendees.length > 0 && (
                  <div className="mt-1 flex items-center gap-1.5 text-xs text-slate-400">
                    <Users className="w-3.5 h-3.5" />
                    <span className="truncate">
                      {meeting.attendees.slice(0, 3).join(", ")}
                      {meeting.attendees.length > 3 && ` +${meeting.attendees.length - 3} more`}
                    </span>
                  </div>
                )}
              </div>
              {/* Brief link */}
              <Link
                to={`/dashboard/meetings/${calendarEventId}/brief`}
                className="flex-shrink-0 p-2 text-slate-500 hover:text-primary-400 hover:bg-primary-500/10 rounded-lg opacity-0 group-hover:opacity-100 transition-all"
                title="View meeting brief"
              >
                <FileText className="w-5 h-5" />
              </Link>
            </div>
          );
        })}
      </div>
    </CollapsibleSection>
  );
}
