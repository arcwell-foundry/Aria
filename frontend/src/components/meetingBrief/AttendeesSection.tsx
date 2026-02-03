import { Users } from "lucide-react";
import type { AttendeeProfile } from "@/api/meetingBriefs";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";
import { AttendeeCard } from "./AttendeeCard";

interface AttendeesSectionProps {
  attendees: AttendeeProfile[];
}

export function AttendeesSection({ attendees }: AttendeesSectionProps) {
  if (attendees.length === 0) {
    return (
      <CollapsibleSection
        title="Attendees"
        icon={<Users className="w-5 h-5" />}
        badge={0}
        badgeColor="slate"
      >
        <div className="text-center py-6 text-slate-400">
          <Users className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p>No attendee information available</p>
        </div>
      </CollapsibleSection>
    );
  }

  return (
    <CollapsibleSection
      title="Attendees"
      icon={<Users className="w-5 h-5" />}
      badge={attendees.length}
      badgeColor="primary"
    >
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {attendees.map((attendee) => (
          <AttendeeCard key={attendee.email} attendee={attendee} />
        ))}
      </div>
    </CollapsibleSection>
  );
}
