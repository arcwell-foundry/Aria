import { TrendingUp, Eye, FileText } from 'lucide-react';
import { useSignals } from '@/hooks/useIntelPanelData';

interface Signal {
  message: string;
  strength: 'high' | 'medium' | 'low';
  source: string;
}

const STRENGTH_COLORS: Record<string, string> = {
  high: 'var(--success)',
  medium: 'var(--warning)',
  low: 'var(--text-secondary)',
};

const SIGNAL_ICONS: Record<string, typeof TrendingUp> = {
  high: TrendingUp,
  medium: Eye,
  low: FileText,
};

function mapConfidenceToStrength(signalType: string): 'high' | 'medium' | 'low' {
  const high = ['hiring', 'expansion', 'budget_approval', 'rfp_issued'];
  const medium = ['website_visit', 'content_download', 'event_attendance'];
  if (high.includes(signalType)) return 'high';
  if (medium.includes(signalType)) return 'medium';
  return 'low';
}

function BuyingSignalsSkeleton() {
  return (
    <div className="space-y-2">
      <div className="h-3 w-28 rounded bg-[var(--border)] animate-pulse" />
      <div className="h-16 rounded-lg bg-[var(--border)] animate-pulse" />
      <div className="h-16 rounded-lg bg-[var(--border)] animate-pulse" />
    </div>
  );
}

export interface BuyingSignalsModuleProps {
  signals?: Signal[];
}

export function BuyingSignalsModule({ signals: propSignals }: BuyingSignalsModuleProps) {
  const { data: apiSignals, isLoading } = useSignals({ limit: 5 });

  if (isLoading && !propSignals) return <BuyingSignalsSkeleton />;

  const signals: Signal[] = propSignals ?? (apiSignals ?? []).map((s) => ({
    message: s.content,
    strength: mapConfidenceToStrength(s.signal_type),
    source: s.source ?? s.company_name ?? 'ARIA',
  }));

  if (signals.length === 0) {
    return (
      <div data-aria-id="intel-buying-signals" className="space-y-2">
        <h3
          className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
          style={{ color: 'var(--text-secondary)' }}
        >
          Buying Signals
        </h3>
        <div
          className="rounded-lg border p-4"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <p className="font-sans text-[12px]" style={{ color: 'var(--text-secondary)' }}>
            No buying signals detected yet. ARIA is scanning for intent signals.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div data-aria-id="intel-buying-signals" className="space-y-2">
      <h3
        className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
        style={{ color: 'var(--text-secondary)' }}
      >
        Buying Signals
      </h3>
      {signals.map((signal, i) => {
        const Icon = SIGNAL_ICONS[signal.strength] || TrendingUp;
        return (
          <div
            key={i}
            className="rounded-lg border p-3"
            style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
          >
            <div className="flex items-start gap-2">
              <Icon
                size={14}
                className="mt-0.5 flex-shrink-0"
                style={{ color: STRENGTH_COLORS[signal.strength] }}
              />
              <div className="min-w-0">
                <p className="font-sans text-[13px] leading-[1.5]" style={{ color: 'var(--text-primary)' }}>
                  {signal.message}
                </p>
                <div className="flex items-center gap-2 mt-1">
                  <span
                    className="font-mono text-[10px]"
                    style={{ color: STRENGTH_COLORS[signal.strength] }}
                  >
                    {signal.strength?.toUpperCase() ?? 'UNKNOWN'}
                  </span>
                  <span className="font-mono text-[10px]" style={{ color: 'var(--text-secondary)' }}>
                    · {signal.source}
                  </span>
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
