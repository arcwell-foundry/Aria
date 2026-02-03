import { Building2, Newspaper, Users2 } from "lucide-react";
import type { CompanyResearch } from "@/api/meetingBriefs";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";

interface CompanySectionProps {
  company: CompanyResearch | null;
}

export function CompanySection({ company }: CompanySectionProps) {
  if (!company) {
    return null;
  }

  const { name, industry, size, recent_news, our_history } = company;

  return (
    <CollapsibleSection
      title="Company Intel"
      icon={<Building2 className="w-5 h-5" />}
      badge={name}
      badgeColor="primary"
    >
      <div className="space-y-5">
        {/* Company overview */}
        <div className="flex items-start gap-4 p-4 bg-slate-700/30 border border-slate-600/30 rounded-xl">
          <div className="flex-shrink-0 w-12 h-12 bg-slate-600/50 rounded-xl flex items-center justify-center">
            <Building2 className="w-6 h-6 text-slate-300" />
          </div>
          <div className="flex-1 min-w-0">
            <h4 className="text-lg font-semibold text-white">{name}</h4>
            <div className="mt-1 flex flex-wrap items-center gap-3 text-sm text-slate-400">
              {industry && (
                <span className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 bg-primary-400 rounded-full" />
                  {industry}
                </span>
              )}
              {size && (
                <span className="flex items-center gap-1.5">
                  <Users2 className="w-3.5 h-3.5" />
                  {size} employees
                </span>
              )}
            </div>
          </div>
        </div>

        {/* Our history with this company */}
        {our_history && (
          <div className="space-y-2">
            <h5 className="text-xs font-medium text-slate-400 uppercase tracking-wider">
              Our History
            </h5>
            <p className="text-sm text-slate-300 leading-relaxed">{our_history}</p>
          </div>
        )}

        {/* Recent news */}
        {recent_news.length > 0 && (
          <div className="space-y-3">
            <h5 className="text-xs font-medium text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
              <Newspaper className="w-3.5 h-3.5" />
              Recent News
            </h5>
            <ul className="space-y-2">
              {recent_news.slice(0, 5).map((news, i) => (
                <li
                  key={i}
                  className="flex items-start gap-3 p-3 bg-slate-700/20 border border-slate-600/20 rounded-lg"
                >
                  <span className="flex-shrink-0 w-1.5 h-1.5 mt-2 bg-amber-400 rounded-full" />
                  <span className="text-sm text-slate-300">{news}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </CollapsibleSection>
  );
}
