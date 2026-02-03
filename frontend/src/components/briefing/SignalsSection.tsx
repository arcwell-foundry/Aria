import { Radio, Building2, TrendingUp, Swords } from "lucide-react";
import type { BriefingSignal, BriefingSignals } from "@/api/briefings";
import { CollapsibleSection } from "@/components/ui/CollapsibleSection";

interface SignalsSectionProps {
  signals: BriefingSignals;
}

function SignalCard({ signal }: { signal: BriefingSignal }) {
  const typeConfig = {
    company_news: {
      icon: <Building2 className="w-4 h-4 text-blue-400" />,
      bg: "bg-blue-500/10",
      border: "border-blue-500/30",
    },
    market_trend: {
      icon: <TrendingUp className="w-4 h-4 text-emerald-400" />,
      bg: "bg-emerald-500/10",
      border: "border-emerald-500/30",
    },
    competitive_intel: {
      icon: <Swords className="w-4 h-4 text-purple-400" />,
      bg: "bg-purple-500/10",
      border: "border-purple-500/30",
    },
  };

  const config = typeConfig[signal.type];

  return (
    <div
      className={`p-3 bg-slate-700/30 border ${config.border} rounded-lg hover:bg-slate-700/50 transition-colors`}
    >
      <div className="flex items-start gap-3">
        <div className={`flex-shrink-0 p-2 ${config.bg} rounded-lg`}>{config.icon}</div>
        <div className="flex-1 min-w-0">
          <h4 className="text-white font-medium">{signal.title}</h4>
          <p className="mt-1 text-sm text-slate-400 line-clamp-2">{signal.summary}</p>
          {signal.source && (
            <p className="mt-2 text-xs text-slate-500">Source: {signal.source}</p>
          )}
        </div>
      </div>
    </div>
  );
}

export function SignalsSection({ signals }: SignalsSectionProps) {
  const { company_news, market_trends, competitive_intel } = signals;
  const totalCount = company_news.length + market_trends.length + competitive_intel.length;

  if (totalCount === 0) {
    return (
      <CollapsibleSection
        title="Market Signals"
        icon={<Radio className="w-5 h-5" />}
        badge={0}
        badgeColor="slate"
      >
        <div className="text-center py-6 text-slate-400">
          <Radio className="w-8 h-8 mx-auto mb-2 opacity-50" />
          <p>No signals detected today</p>
        </div>
      </CollapsibleSection>
    );
  }

  return (
    <CollapsibleSection
      title="Market Signals"
      icon={<Radio className="w-5 h-5" />}
      badge={totalCount}
      badgeColor="green"
    >
      <div className="space-y-4">
        {company_news.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-blue-400 uppercase tracking-wider mb-2">
              Company News
            </h4>
            <div className="space-y-2">
              {company_news.map((signal) => (
                <SignalCard key={signal.id} signal={signal} />
              ))}
            </div>
          </div>
        )}

        {market_trends.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-emerald-400 uppercase tracking-wider mb-2">
              Market Trends
            </h4>
            <div className="space-y-2">
              {market_trends.map((signal) => (
                <SignalCard key={signal.id} signal={signal} />
              ))}
            </div>
          </div>
        )}

        {competitive_intel.length > 0 && (
          <div>
            <h4 className="text-xs font-medium text-purple-400 uppercase tracking-wider mb-2">
              Competitive Intel
            </h4>
            <div className="space-y-2">
              {competitive_intel.map((signal) => (
                <SignalCard key={signal.id} signal={signal} />
              ))}
            </div>
          </div>
        )}
      </div>
    </CollapsibleSection>
  );
}
