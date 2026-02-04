import { Mail, Pencil, User, Users } from "lucide-react";
import type { Stakeholder, Sentiment, StakeholderRole } from "@/api/leads";

interface StakeholdersTabProps {
  stakeholders: Stakeholder[];
  isLoading: boolean;
  onEdit: (stakeholder: Stakeholder) => void;
}

// Role configuration
const roleConfig: Record<StakeholderRole, { label: string; color: string }> = {
  decision_maker: { label: "Decision Maker", color: "text-purple-400 bg-purple-500/10" },
  influencer: { label: "Influencer", color: "text-blue-400 bg-blue-500/10" },
  champion: { label: "Champion", color: "text-emerald-400 bg-emerald-500/10" },
  blocker: { label: "Blocker", color: "text-red-400 bg-red-500/10" },
  user: { label: "User", color: "text-slate-400 bg-slate-500/10" },
};

// Sentiment configuration
const sentimentConfig: Record<Sentiment, { label: string; color: string; bg: string }> = {
  positive: { label: "Positive", color: "bg-emerald-400", bg: "bg-emerald-500/20" },
  neutral: { label: "Neutral", color: "bg-amber-400", bg: "bg-amber-500/20" },
  negative: { label: "Negative", color: "bg-red-400", bg: "bg-red-500/20" },
  unknown: { label: "Unknown", color: "bg-slate-400", bg: "bg-slate-500/20" },
};

function formatDate(dateStr: string | null): string {
  if (!dateStr) return "Never";
  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) {
    return "Today";
  } else if (diffDays === 1) {
    return "Yesterday";
  } else if (diffDays < 7) {
    return `${diffDays} days ago`;
  } else if (diffDays < 30) {
    const weeks = Math.floor(diffDays / 7);
    return `${weeks} week${weeks > 1 ? "s" : ""} ago`;
  } else {
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    });
  }
}

interface StakeholderCardProps {
  stakeholder: Stakeholder;
  onEdit: () => void;
}

function StakeholderCard({ stakeholder, onEdit }: StakeholderCardProps) {
  const role = stakeholder.role ? roleConfig[stakeholder.role] : null;
  const sentiment = sentimentConfig[stakeholder.sentiment];

  // Get display name - fallback to email prefix
  const displayName =
    stakeholder.contact_name ||
    stakeholder.contact_email.split("@")[0].replace(/[._-]/g, " ");

  // Influence level is 0-10
  const influencePercent = (stakeholder.influence_level / 10) * 100;

  return (
    <div className="group relative bg-slate-800/40 backdrop-blur-sm border border-slate-700/50 rounded-xl p-5 transition-all duration-300 hover:bg-slate-800/60 hover:border-slate-600/50">
      {/* Edit button - hover reveal */}
      <button
        onClick={onEdit}
        className="absolute top-4 right-4 p-2 rounded-lg bg-slate-700/50 text-slate-400 opacity-0 group-hover:opacity-100 hover:bg-primary-500/20 hover:text-primary-400 transition-all duration-200"
        title="Edit stakeholder"
      >
        <Pencil className="w-4 h-4" />
      </button>

      {/* Avatar and name */}
      <div className="flex items-start gap-4 mb-4">
        <div className="flex-shrink-0 w-12 h-12 bg-gradient-to-br from-slate-700 to-slate-800 rounded-xl flex items-center justify-center border border-slate-600/50">
          <User className="w-6 h-6 text-slate-400" />
        </div>
        <div className="flex-1 min-w-0 pr-8">
          <h4 className="text-base font-semibold text-white truncate capitalize">
            {displayName}
          </h4>
          {stakeholder.title && (
            <p className="text-sm text-slate-400 truncate">{stakeholder.title}</p>
          )}
        </div>
      </div>

      {/* Email */}
      <div className="flex items-center gap-2 mb-4 text-sm text-slate-400">
        <Mail className="w-4 h-4 text-slate-500 flex-shrink-0" />
        <span className="truncate">{stakeholder.contact_email}</span>
      </div>

      {/* Role badge and sentiment indicator */}
      <div className="flex items-center gap-2 mb-4">
        {role && (
          <span
            className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium ${role.color}`}
          >
            {role.label}
          </span>
        )}
        <div className="flex items-center gap-1.5">
          <span
            className={`w-2 h-2 rounded-full ${sentiment.color}`}
            title={sentiment.label}
          />
          <span className="text-xs text-slate-500">{sentiment.label}</span>
        </div>
      </div>

      {/* Influence progress bar */}
      <div className="mb-4">
        <div className="flex items-center justify-between mb-1.5">
          <span className="text-xs text-slate-500">Influence</span>
          <span className="text-xs text-slate-400">
            {stakeholder.influence_level}/10
          </span>
        </div>
        <div className="w-full h-1.5 bg-slate-700/50 rounded-full overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-primary-500 to-primary-400 rounded-full transition-all duration-300"
            style={{ width: `${influencePercent}%` }}
          />
        </div>
      </div>

      {/* Last contacted */}
      <div className="text-xs text-slate-500 mb-3">
        Last contacted: {formatDate(stakeholder.last_contacted_at)}
      </div>

      {/* Notes preview */}
      {stakeholder.notes && (
        <p className="text-sm text-slate-400 line-clamp-2 pt-3 border-t border-slate-700/50">
          {stakeholder.notes}
        </p>
      )}
    </div>
  );
}

function StakeholdersSkeleton() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {[...Array(4)].map((_, i) => (
        <div
          key={i}
          className="bg-slate-800/40 border border-slate-700/50 rounded-xl p-5 animate-pulse"
        >
          {/* Avatar and name skeleton */}
          <div className="flex items-start gap-4 mb-4">
            <div className="w-12 h-12 bg-slate-700 rounded-xl shrink-0" />
            <div className="flex-1">
              <div className="h-5 bg-slate-700 rounded w-3/4 mb-2" />
              <div className="h-4 bg-slate-700 rounded w-1/2" />
            </div>
          </div>

          {/* Email skeleton */}
          <div className="flex items-center gap-2 mb-4">
            <div className="w-4 h-4 bg-slate-700 rounded" />
            <div className="h-4 bg-slate-700 rounded w-2/3" />
          </div>

          {/* Badge skeleton */}
          <div className="flex items-center gap-2 mb-4">
            <div className="h-6 bg-slate-700 rounded-full w-24" />
            <div className="w-2 h-2 bg-slate-700 rounded-full" />
            <div className="h-3 bg-slate-700 rounded w-12" />
          </div>

          {/* Progress bar skeleton */}
          <div className="mb-4">
            <div className="flex justify-between mb-1.5">
              <div className="h-3 bg-slate-700 rounded w-12" />
              <div className="h-3 bg-slate-700 rounded w-8" />
            </div>
            <div className="h-1.5 bg-slate-700 rounded-full" />
          </div>

          {/* Date skeleton */}
          <div className="h-3 bg-slate-700 rounded w-32" />
        </div>
      ))}
    </div>
  );
}

function EmptyStakeholders() {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4">
      <div className="w-16 h-16 bg-slate-800/50 rounded-2xl flex items-center justify-center mb-4 border border-slate-700/50">
        <Users className="w-8 h-8 text-slate-500" />
      </div>
      <h3 className="text-lg font-semibold text-white mb-2">No stakeholders yet</h3>
      <p className="text-slate-400 text-center max-w-sm">
        Add stakeholders to track key contacts involved in this deal and their
        influence on the decision.
      </p>
    </div>
  );
}

export function StakeholdersTab({
  stakeholders,
  isLoading,
  onEdit,
}: StakeholdersTabProps) {
  if (isLoading) {
    return <StakeholdersSkeleton />;
  }

  if (stakeholders.length === 0) {
    return <EmptyStakeholders />;
  }

  // Sort stakeholders by influence level descending
  const sortedStakeholders = [...stakeholders].sort(
    (a, b) => b.influence_level - a.influence_level
  );

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {sortedStakeholders.map((stakeholder) => (
        <StakeholderCard
          key={stakeholder.id}
          stakeholder={stakeholder}
          onEdit={() => onEdit(stakeholder)}
        />
      ))}
    </div>
  );
}
