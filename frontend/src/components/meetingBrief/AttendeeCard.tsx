import { Building2, ExternalLink, MessageCircle, User } from "lucide-react";
import type { AttendeeProfile } from "@/api/meetingBriefs";

interface AttendeeCardProps {
  attendee: AttendeeProfile;
}

function getInitials(name: string | null, email: string): string {
  if (name) {
    return name
      .split(" ")
      .map((n) => n[0])
      .join("")
      .toUpperCase()
      .slice(0, 2);
  }
  return email[0].toUpperCase();
}

function getAvatarColor(email: string): string {
  const colors = [
    "from-blue-500 to-blue-600",
    "from-purple-500 to-purple-600",
    "from-success to-success",
    "from-amber-500 to-amber-600",
    "from-rose-500 to-rose-600",
    "from-cyan-500 to-cyan-600",
  ];
  const index = email.split("").reduce((acc, char) => acc + char.charCodeAt(0), 0);
  return colors[index % colors.length];
}

export function AttendeeCard({ attendee }: AttendeeCardProps) {
  const { name, email, title, company, linkedin_url, background, recent_activity, talking_points } =
    attendee;

  return (
    <div className="bg-slate-700/30 border border-slate-600/30 rounded-xl p-5 space-y-4 hover:border-slate-500/50 transition-colors">
      {/* Header with avatar */}
      <div className="flex items-start gap-4">
        <div
          className={`flex-shrink-0 w-14 h-14 rounded-full bg-gradient-to-br ${getAvatarColor(email)} flex items-center justify-center shadow-lg`}
        >
          <span className="text-lg font-semibold text-white">{getInitials(name, email)}</span>
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h4 className="text-white font-semibold truncate">{name || email}</h4>
            {linkedin_url && (
              <a
                href={linkedin_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-slate-400 hover:text-primary-400 transition-colors"
                title="View LinkedIn profile"
              >
                <ExternalLink className="w-4 h-4" />
              </a>
            )}
          </div>
          {title && (
            <div className="flex items-center gap-1.5 mt-0.5 text-sm text-slate-400">
              <User className="w-3.5 h-3.5" />
              <span className="truncate">{title}</span>
            </div>
          )}
          {company && (
            <div className="flex items-center gap-1.5 mt-0.5 text-sm text-slate-400">
              <Building2 className="w-3.5 h-3.5" />
              <span className="truncate">{company}</span>
            </div>
          )}
        </div>
      </div>

      {/* Background */}
      {background && (
        <div className="text-sm text-slate-300 leading-relaxed">{background}</div>
      )}

      {/* Recent activity */}
      {recent_activity.length > 0 && (
        <div className="space-y-2">
          <h5 className="text-xs font-medium text-slate-400 uppercase tracking-wider">
            Recent Activity
          </h5>
          <ul className="space-y-1.5">
            {recent_activity.slice(0, 3).map((activity, i) => (
              <li key={i} className="text-sm text-slate-300 flex items-start gap-2">
                <span className="text-primary-400 mt-1.5">•</span>
                {activity}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Talking points */}
      {talking_points.length > 0 && (
        <div className="space-y-2">
          <h5 className="text-xs font-medium text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
            <MessageCircle className="w-3.5 h-3.5" />
            Talking Points
          </h5>
          <div className="flex flex-wrap gap-2">
            {talking_points.map((point, i) => (
              <span
                key={i}
                className="px-3 py-1.5 text-sm bg-primary-500/10 text-primary-300 border border-primary-500/20 rounded-full"
              >
                {point}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
