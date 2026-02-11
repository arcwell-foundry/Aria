import { Shield, Briefcase, Users } from 'lucide-react';

interface CompetitorMove {
  message: string;
  source: string;
  competitor: string;
  time: string;
}

const PLACEHOLDER_MOVES: CompetitorMove[] = [
  {
    message: 'Launched new CDMO pricing tier targeting mid-market',
    competitor: 'Thermo Fisher',
    source: 'News',
    time: '6h ago',
  },
  {
    message: 'Acquired BioProcess Solutions Ltd for $120M',
    competitor: 'Sartorius',
    source: 'SEC filing',
    time: '1d ago',
  },
  {
    message: 'Hired VP of Commercial from Lonza',
    competitor: 'Catalent',
    source: 'LinkedIn',
    time: '2d ago',
  },
];

const SOURCE_ICONS: Record<string, typeof Shield> = {
  News: Shield,
  'SEC filing': Briefcase,
  LinkedIn: Users,
};

export interface CompetitiveIntelModuleProps {
  moves?: CompetitorMove[];
}

export function CompetitiveIntelModule({ moves = PLACEHOLDER_MOVES }: CompetitiveIntelModuleProps) {
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
