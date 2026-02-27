import { Swords } from 'lucide-react';

export interface BattleCardData {
  competitor_name: string;
  our_company?: string;
  rows: { label: string; competitor: string; us: string }[];
}

export function BattleCard({ data }: { data: BattleCardData }) {
  if (!data) return null;

  return (
    <div
      className="rounded-lg border border-[var(--border)] overflow-hidden"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id={`battle-card-${(data.competitor_name ?? '').toLowerCase().replace(/\s+/g, '-')}`}
    >
      <div
        className="flex items-center gap-2 px-4 py-2.5"
        style={{
          borderBottom: '1px solid var(--border)',
          backgroundColor: 'rgba(245,158,11,0.05)',
        }}
      >
        <Swords className="w-3.5 h-3.5 text-amber-400" />
        <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
          {data.our_company || 'Your Team'} vs {data.competitor_name}
        </span>
      </div>

      {data.rows?.length > 0 && (
        <table className="w-full text-xs">
          <thead>
            <tr style={{ borderBottom: '1px solid var(--border)' }}>
              <th className="px-4 py-2 text-left font-mono text-[10px] uppercase tracking-wider" style={{ color: 'var(--text-secondary)', width: '25%' }} />
              <th className="px-4 py-2 text-left font-mono text-[10px] uppercase tracking-wider" style={{ color: 'var(--accent)', width: '37.5%' }}>
                {data.our_company || 'Us'}
              </th>
              <th className="px-4 py-2 text-left font-mono text-[10px] uppercase tracking-wider" style={{ color: 'var(--text-secondary)', width: '37.5%' }}>
                {data.competitor_name}
              </th>
            </tr>
          </thead>
          <tbody>
            {data.rows?.map((row, i) => (
              <tr
                key={i}
                style={{ borderBottom: i < (data.rows?.length ?? 0) - 1 ? '1px solid var(--border)' : undefined }}
              >
                <td className="px-4 py-2 font-mono text-[10px] uppercase tracking-wider" style={{ color: 'var(--text-secondary)' }}>
                  {row.label}
                </td>
                <td className="px-4 py-2 font-mono" style={{ color: 'var(--text-primary)' }}>
                  {row.us}
                </td>
                <td className="px-4 py-2 font-mono" style={{ color: 'var(--text-primary)' }}>
                  {row.competitor}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
