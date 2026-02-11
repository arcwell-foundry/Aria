import { TrendingUp, Eye, FileText } from 'lucide-react';

interface Signal {
  message: string;
  strength: 'high' | 'medium' | 'low';
  source: string;
}

const PLACEHOLDER_SIGNALS: Signal[] = [
  {
    message: 'Lonza posted Sr. Dir. Process Development role — expansion signal',
    strength: 'high',
    source: 'Job boards',
  },
  {
    message: 'Catalent visited pricing page 3x this week',
    strength: 'medium',
    source: 'Web analytics',
  },
  {
    message: 'BioConnect downloaded GMP compliance whitepaper',
    strength: 'low',
    source: 'Content tracking',
  },
];

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

export interface BuyingSignalsModuleProps {
  signals?: Signal[];
}

export function BuyingSignalsModule({ signals = PLACEHOLDER_SIGNALS }: BuyingSignalsModuleProps) {
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
                    {signal.strength.toUpperCase()}
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
