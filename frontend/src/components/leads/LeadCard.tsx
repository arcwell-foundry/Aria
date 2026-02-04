import { Building2, Calendar, DollarSign, MessageSquarePlus, TrendingUp } from "lucide-react";
import { Link } from "react-router-dom";
import type { Lead } from "@/api/leads";

interface LeadCardProps {
  lead: Lead;
  isSelected: boolean;
  onSelect: () => void;
  onAddNote: () => void;
}

function HealthBadge({ score }: { score: number }) {
  const getHealthConfig = (score: number) => {
    if (score >= 70) {
      return {
        emoji: "🟢",
        bg: "bg-emerald-500/10",
        border: "border-emerald-500/20",
        text: "text-emerald-400",
        label: "Healthy",
      };
    }
    if (score >= 40) {
      return {
        emoji: "🟡",
        bg: "bg-amber-500/10",
        border: "border-amber-500/20",
        text: "text-amber-400",
        label: "Attention",
      };
    }
    return {
      emoji: "🔴",
      bg: "bg-red-500/10",
      border: "border-red-500/20",
      text: "text-red-400",
      label: "At Risk",
    };
  };

  const config = getHealthConfig(score);

  return (
    <div
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full ${config.bg} ${config.border} border`}
    >
      <span className="text-sm">{config.emoji}</span>
      <span className={`text-xs font-medium ${config.text}`}>{score}</span>
    </div>
  );
}

function StageBadge({ stage }: { stage: string }) {
  const stageConfig: Record<string, { bg: string; text: string }> = {
    lead: { bg: "bg-slate-500/10", text: "text-slate-400" },
    opportunity: { bg: "bg-primary-500/10", text: "text-primary-400" },
    account: { bg: "bg-accent-500/10", text: "text-accent-400" },
  };

  const config = stageConfig[stage] || stageConfig.lead;

  return (
    <span
      className={`inline-flex items-center px-2 py-0.5 rounded text-xs font-medium capitalize ${config.bg} ${config.text}`}
    >
      {stage}
    </span>
  );
}

export function LeadCard({ lead, isSelected, onSelect, onAddNote }: LeadCardProps) {
  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return "—";
    const date = new Date(dateStr);
    return date.toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    });
  };

  const formatCurrency = (value: number | null) => {
    if (!value) return "—";
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      notation: "compact",
      maximumFractionDigits: 1,
    }).format(value);
  };

  return (
    <div
      className={`group relative bg-slate-800/40 backdrop-blur-sm border rounded-xl p-5 transition-all duration-300 hover:bg-slate-800/60 hover:shadow-lg hover:shadow-primary-500/5 hover:-translate-y-0.5 ${
        isSelected
          ? "border-primary-500/50 ring-1 ring-primary-500/20"
          : "border-slate-700/50 hover:border-slate-600/50"
      }`}
    >
      {/* Selection checkbox */}
      <div className="absolute top-4 right-4 z-10">
        <button
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onSelect();
          }}
          className={`w-5 h-5 rounded border-2 transition-all duration-200 flex items-center justify-center ${
            isSelected
              ? "bg-primary-500 border-primary-500"
              : "border-slate-600 hover:border-slate-500 group-hover:border-slate-500"
          }`}
        >
          {isSelected && (
            <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
            </svg>
          )}
        </button>
      </div>

      <Link to={`/dashboard/leads/${lead.id}`} className="block">
        {/* Header */}
        <div className="flex items-start gap-4 mb-4">
          <div className="flex-shrink-0 w-12 h-12 bg-gradient-to-br from-slate-700 to-slate-800 rounded-xl flex items-center justify-center border border-slate-600/50">
            <Building2 className="w-6 h-6 text-slate-400" />
          </div>
          <div className="flex-1 min-w-0 pr-8">
            <h3 className="text-lg font-semibold text-white truncate group-hover:text-primary-300 transition-colors">
              {lead.company_name}
            </h3>
            <div className="flex items-center gap-2 mt-1">
              <StageBadge stage={lead.lifecycle_stage} />
              <span
                className={`text-xs capitalize ${
                  lead.status === "active"
                    ? "text-emerald-400"
                    : lead.status === "won"
                      ? "text-primary-400"
                      : lead.status === "lost"
                        ? "text-red-400"
                        : "text-slate-500"
                }`}
              >
                {lead.status}
              </span>
            </div>
          </div>
        </div>

        {/* Health Score */}
        <div className="mb-4">
          <HealthBadge score={lead.health_score} />
        </div>

        {/* Meta info */}
        <div className="grid grid-cols-2 gap-3 text-sm">
          <div className="flex items-center gap-2 text-slate-400">
            <Calendar className="w-4 h-4 text-slate-500" />
            <span>Last: {formatDate(lead.last_activity_at)}</span>
          </div>
          <div className="flex items-center gap-2 text-slate-400">
            <DollarSign className="w-4 h-4 text-slate-500" />
            <span>{formatCurrency(lead.expected_value)}</span>
          </div>
          {lead.expected_close_date && (
            <div className="flex items-center gap-2 text-slate-400 col-span-2">
              <TrendingUp className="w-4 h-4 text-slate-500" />
              <span>Close: {formatDate(lead.expected_close_date)}</span>
            </div>
          )}
        </div>

        {/* Tags */}
        {lead.tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-4 pt-4 border-t border-slate-700/50">
            {lead.tags.slice(0, 3).map((tag) => (
              <span
                key={tag}
                className="px-2 py-0.5 text-xs rounded-full bg-slate-700/50 text-slate-400"
              >
                {tag}
              </span>
            ))}
            {lead.tags.length > 3 && (
              <span className="px-2 py-0.5 text-xs rounded-full bg-slate-700/50 text-slate-500">
                +{lead.tags.length - 3}
              </span>
            )}
          </div>
        )}
      </Link>

      {/* Quick action - Add Note */}
      <button
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
          onAddNote();
        }}
        className="absolute bottom-4 right-4 p-2 rounded-lg bg-slate-700/50 text-slate-400 opacity-0 group-hover:opacity-100 hover:bg-primary-500/20 hover:text-primary-400 transition-all duration-200"
        title="Add note"
      >
        <MessageSquarePlus className="w-4 h-4" />
      </button>
    </div>
  );
}
