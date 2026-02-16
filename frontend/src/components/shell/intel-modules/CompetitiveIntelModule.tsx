import { Shield, Briefcase, Users } from 'lucide-react';
import { useIntelBattleCards, formatRelativeTime } from '@/hooks/useIntelPanelData';

interface CompetitorMove {
  message: string;
  source: string;
  competitor: string;
  time: string;
}

const SOURCE_ICONS: Record<string, typeof Shield> = {
  News: Shield,
  'SEC filing': Briefcase,
  LinkedIn: Users,
  auto: Shield,
  manual: Briefcase,
  demo_seed: Shield,
};

function CompetitiveIntelSkeleton() {
  return (
    <div className="space-y-2">
      <div className="h-3 w-36 rounded bg-[var(--border)] animate-pulse" />
      <div className="h-20 rounded-lg bg-[var(--border)] animate-pulse" />
      <div className="h-20 rounded-lg bg-[var(--border)] animate-pulse" />
    </div>
  );
}

export interface CompetitiveIntelModuleProps {
  moves?: CompetitorMove[];
}

export function CompetitiveIntelModule({ moves: propMoves }: CompetitiveIntelModuleProps) {
  const { data: battleCards, isLoading } = useIntelBattleCards();

  if (isLoading && !propMoves) return <CompetitiveIntelSkeleton />;

  const moves: CompetitorMove[] = propMoves ?? (battleCards ?? []).slice(0, 5).map((card) => ({
    message: card.overview ?? card.strengths?.[0] ?? `Competitive intelligence on ${card.competitor_name}`,
    competitor: card.competitor_name,
    source: card.update_source === 'auto' ? 'Auto-detected' : card.update_source === 'manual' ? 'Manual' : 'Intelligence',
    time: formatRelativeTime(card.last_updated),
  }));

  if (moves.length === 0) {
    return (
      <div data-aria-id="intel-competitive" className="space-y-2">
        <h3
          className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
          style={{ color: 'var(--text-secondary)' }}
        >
          Competitive Intelligence
        </h3>
        <div
          className="rounded-lg border p-4"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <p className="font-sans text-[12px]" style={{ color: 'var(--text-secondary)' }}>
            No competitor intelligence yet. Set up competitive monitoring to start tracking.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div data-aria-id="intel-competitive" className="space-y-2">
      <h3
        className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
        style={{ color: 'var(--text-secondary)' }}
      >
        Competitive Intelligence
      </h3>
      {moves.map((move, i) => {
        const Icon = SOURCE_ICONS[move.source] || Shield;
        return (
          <div
            key={i}
            className="rounded-lg border p-3"
            style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
          >
            <div className="flex items-start gap-2">
              <Icon size={14} className="mt-0.5 flex-shrink-0" style={{ color: 'var(--accent)' }} />
              <div className="min-w-0">
                <p className="font-mono text-[10px] font-medium mb-1" style={{ color: 'var(--accent)' }}>
                  {move.competitor}
                </p>
                <p className="font-sans text-[13px] leading-[1.5]" style={{ color: 'var(--text-primary)' }}>
                  {move.message}
                </p>
                <p className="font-mono text-[10px] mt-1" style={{ color: 'var(--text-secondary)' }}>
                  {move.source} · {move.time}
                </p>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
