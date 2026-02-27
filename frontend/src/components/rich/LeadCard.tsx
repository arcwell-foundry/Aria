import { useState } from 'react';
import { Building2, User, TrendingUp, Plus, Loader2 } from 'lucide-react';

export interface LeadCardData {
  company_name: string;
  contacts?: { name: string; title: string }[];
  fit_score?: number | null;
  signals?: string[];
  total_results?: number;
  lifecycle_stage?: string;
}

export function LeadCard({ data }: { data: LeadCardData }) {
  const [adding, setAdding] = useState(false);
  const [added, setAdded] = useState(false);

  if (!data) return null;

  const handleAddToPipeline = async () => {
    setAdding(true);
    try {
      const { apiClient } = await import('@/api/client');
      await apiClient.post('/leads/pipeline', {
        company_name: data.company_name,
      });
      setAdded(true);
    } catch {
      setAdding(false);
    }
  };

  return (
    <div
      className="rounded-lg border border-[var(--border)] overflow-hidden"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id={`lead-card-${(data.company_name ?? '').toLowerCase().replace(/\s+/g, '-')}`}
    >
      {/* Header */}
      <div
        className="flex items-center gap-2 px-4 py-2.5"
        style={{
          borderBottom: '1px solid var(--border)',
          backgroundColor: 'rgba(46,102,255,0.05)',
        }}
      >
        <Building2 className="w-3.5 h-3.5" style={{ color: 'var(--accent)' }} />
        <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
          {data.company_name}
        </span>
        {data.lifecycle_stage && (
          <span className="ml-auto text-[10px] font-mono uppercase tracking-wider" style={{ color: 'var(--text-secondary)' }}>
            {data.lifecycle_stage}
          </span>
        )}
      </div>

      <div className="px-4 py-3 space-y-2.5">
        {/* Fit Score */}
        {data.fit_score != null && (
          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] font-mono uppercase tracking-wider" style={{ color: 'var(--text-secondary)' }}>
                Fit Score
              </span>
              <span className="text-xs font-mono" style={{ color: 'var(--accent)' }}>
                {data.fit_score}%
              </span>
            </div>
            <div className="h-1.5 rounded-full" style={{ backgroundColor: 'var(--bg-subtle)' }}>
              <div
                className="h-full rounded-full transition-all"
                style={{
                  width: `${Math.min(data.fit_score, 100)}%`,
                  backgroundColor: 'var(--accent)',
                }}
              />
            </div>
          </div>
        )}

        {/* Contacts */}
        {data.contacts && data.contacts.length > 0 && (
          <div className="space-y-1">
            {data.contacts.map((contact, i) => (
              <div key={i} className="flex items-center gap-2">
                <User className="w-3 h-3 shrink-0" style={{ color: 'var(--text-secondary)' }} />
                <span className="text-xs" style={{ color: 'var(--text-primary)' }}>
                  {contact.name}
                </span>
                {contact.title && (
                  <span className="text-[10px]" style={{ color: 'var(--text-secondary)' }}>
                    {contact.title}
                  </span>
                )}
              </div>
            ))}
          </div>
        )}

        {/* Signals */}
        {data.signals && data.signals.length > 0 && (
          <div className="space-y-1">
            {data.signals.map((signal, i) => (
              <div key={i} className="flex items-start gap-2">
                <TrendingUp className="w-3 h-3 mt-0.5 shrink-0 text-emerald-400" />
                <span className="text-xs" style={{ color: 'var(--text-primary)' }}>
                  {signal}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Action */}
        {!added ? (
          <button
            type="button"
            disabled={adding}
            onClick={handleAddToPipeline}
            className="flex items-center gap-1.5 px-2.5 py-1 rounded text-[10px] font-mono uppercase tracking-wider transition-colors"
            style={{
              color: 'var(--accent)',
              border: '1px solid rgba(46,102,255,0.3)',
            }}
          >
            {adding ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <Plus className="w-3 h-3" />
            )}
            Add to Pipeline
          </button>
        ) : (
          <span className="text-[10px] font-mono uppercase tracking-wider text-emerald-400">
            Added to pipeline
          </span>
        )}
      </div>
    </div>
  );
}
