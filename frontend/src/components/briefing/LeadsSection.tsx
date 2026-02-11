import { Flame, AlertTriangle, Activity, Users } from "lucide-react";
import { Link } from "react-router-dom";
import type { BriefingLead, BriefingLeads } from "@/api/briefings";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";

interface LeadsSectionProps {
  leads?: BriefingLeads;
}

function LeadCard({ lead, variant }: { lead: BriefingLead; variant: "hot" | "attention" | "active" }) {
  const variantStyles = {
    hot: {
      border: "border-orange-500/30 hover:border-orange-500/50",
      icon: <Flame className="w-4 h-4 text-orange-400" />,
      bg: "bg-orange-500/10",
    },
    attention: {
      border: "border-warning/30 hover:border-warning/50",
      icon: <AlertTriangle className="w-4 h-4 text-warning" />,
      bg: "bg-warning/10",
    },
    active: {
      border: "border-green-500/30 hover:border-green-500/50",
      icon: <Activity className="w-4 h-4 text-green-400" />,
      bg: "bg-green-500/10",
    },
  };

  const style = variantStyles[variant];

  return (
    <Link
      to={`/leads/${lead.id}`}
      className={`block p-3 bg-slate-700/30 border ${style.border} rounded-lg transition-colors group`}
    >
      <div className="flex items-start gap-3">
        <div className={`flex-shrink-0 p-2 ${style.bg} rounded-lg`}>{style.icon}</div>
        <div className="flex-1 min-w-0">
          <h4 className="text-white font-medium truncate group-hover:text-primary-300 transition-colors">
            {lead.name}
          </h4>
          <p className="text-sm text-slate-400 truncate">{lead.company}</p>
          {lead.health_score !== undefined && (
            <div className="mt-1 flex items-center gap-2">
              <div className="flex-1 h-1.5 bg-slate-600 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${
                    lead.health_score >= 70
                      ? "bg-green-500"
                      : lead.health_score >= 40
                        ? "bg-warning"
                        : "bg-critical"
                  }`}
                  style={{ width: `${lead.health_score}%` }}
                />
              </div>
              <span className="text-xs text-slate-400">{lead.health_score}%</span>
            </div>
          )}
        </div>
      </div>
    </Link>
  );
}

export function LeadsSection({ leads }: LeadsSectionProps) {
  const { hot_leads = [], needs_attention = [], recently_active = [] } = leads ?? {};
  const totalCount = hot_leads.length + needs_attention.length + recently_active.length;

  if (totalCount === 0) {
    return (
      <CollapsibleSection
        title="Leads"
        icon={<Users className="w-5 h-5" />}
        badge={0}
        badgeColor="slate"
      >
        <div className="text-center py-6 text-slate-400">
          <Users className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p>No lead activity to report</p>
        </div>
      </CollapsibleSection>
    );
  }

  return (
    <CollapsibleSection
      title="Leads"
      icon={<Users className="w-5 h-5" />}
      badge={totalCount}
      badgeColor={hot_leads.length > 0 ? "amber" : "primary"}
    >
      <div className="space-y-4">
        {hot_leads.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-orange-400 uppercase tracking-wider mb-2">
              Hot Leads
            </h4>
            <div className="space-y-2">
              {hot_leads.map((lead) => (
                <LeadCard key={lead.id} lead={lead} variant="hot" />
              ))}
            </div>
          </div>
        )}

        {needs_attention.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-warning uppercase tracking-wider mb-2">
              Needs Attention
            </h4>
            <div className="space-y-2">
              {needs_attention.map((lead) => (
                <LeadCard key={lead.id} lead={lead} variant="attention" />
              ))}
            </div>
          </div>
        )}

        {recently_active.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-green-400 uppercase tracking-wider mb-2">
              Recently Active
            </h4>
            <div className="space-y-2">
              {recently_active.map((lead) => (
                <LeadCard key={lead.id} lead={lead} variant="active" />
              ))}
            </div>
          </div>
        )}
      </div>
    </CollapsibleSection>
  );
}
