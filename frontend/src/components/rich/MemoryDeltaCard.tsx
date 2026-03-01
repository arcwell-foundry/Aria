import { useCallback, useState } from 'react';
import { apiClient } from '@/api/client';

export interface MemoryDeltaFact {
  id: string;
  fact: string;
  confidence: number;
  source: string;
  category: string;
  /** Pre-calibrated language from the backend based on confidence tier. */
  language: string;
}

export interface MemoryDeltaData {
  domain: string;
  facts: MemoryDeltaFact[];
  summary: string;
  timestamp: string;
}

interface MemoryDeltaCardProps {
  data: MemoryDeltaData;
}

const CONFIDENCE_STYLES: Record<string, { bg: string; text: string; border: string }> = {
  high: { bg: 'bg-emerald-500/10', text: 'text-emerald-400', border: 'border-emerald-500/20' },
  medium: { bg: 'bg-amber-500/10', text: 'text-amber-400', border: 'border-amber-500/20' },
  low: { bg: 'bg-blue-500/10', text: 'text-blue-300', border: 'border-blue-500/20' },
};

function getConfidenceTier(confidence: number): 'high' | 'medium' | 'low' {
  if (confidence >= 0.8) return 'high';
  if (confidence >= 0.6) return 'medium';
  return 'low';
}

function FactRow({ fact }: { fact: MemoryDeltaFact }) {
  const [status, setStatus] = useState<'idle' | 'confirmed' | 'correcting' | 'corrected'>('idle');
  const [correction, setCorrection] = useState('');

  const tier = getConfidenceTier(fact.confidence);
  const style = CONFIDENCE_STYLES[tier];

  const handleConfirm = useCallback(async () => {
    try {
      await apiClient.post('/memory/correct', {
        fact_id: fact.id,
        corrected_value: fact.fact,
        correction_type: 'confirm',
      });
      setStatus('confirmed');
    } catch {
      // Silently fail — non-critical interaction
    }
  }, [fact.id, fact.fact]);

  const handleCorrect = useCallback(async () => {
    if (!correction.trim()) return;
    try {
      await apiClient.post('/memory/correct', {
        fact_id: fact.id,
        corrected_value: correction.trim(),
        correction_type: 'factual',
      });
      setStatus('corrected');
    } catch {
      // Silently fail
    }
  }, [fact.id, correction]);

  if (status === 'confirmed') {
    return (
      <div className={`rounded-md ${style.bg} px-3 py-2 text-sm text-[var(--text-primary)] opacity-70`}>
        <span className="text-emerald-400 mr-1.5">&#x2713;</span>
        {fact.fact}
      </div>
    );
  }

  if (status === 'corrected') {
    return (
      <div className="rounded-md bg-blue-500/10 px-3 py-2 text-sm text-[var(--text-primary)] opacity-70">
        <span className="text-blue-400 mr-1.5">&#x2713;</span>
        Corrected
      </div>
    );
  }

  return (
    <div className={`rounded-md border ${style.border} ${style.bg} px-3 py-2`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <p className="text-sm text-[var(--text-primary)] leading-relaxed">
            <span className={`${style.text} text-xs font-mono mr-1.5`}>
              {fact.language}
            </span>
            {fact.fact}
          </p>
          <div className="flex items-center gap-2 mt-1">
            <span className="text-[9px] font-mono uppercase tracking-wider text-[var(--text-secondary)]">
              {fact.source}
            </span>
            {fact.category && (
              <span className="text-[9px] font-mono uppercase tracking-wider text-[var(--text-secondary)]">
                {fact.category}
              </span>
            )}
          </div>
        </div>
        {status === 'idle' && (
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={handleConfirm}
              className="px-2 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/10 transition-colors"
            >
              Confirm
            </button>
            <button
              onClick={() => setStatus('correcting')}
              className="px-2 py-0.5 rounded text-[10px] font-mono uppercase tracking-wider text-[var(--text-secondary)] border border-[var(--border)] hover:bg-[var(--bg-elevated)] transition-colors"
            >
              Correct
            </button>
          </div>
        )}
      </div>
      {status === 'correcting' && (
        <div className="mt-2 flex items-center gap-2">
          <input
            type="text"
            value={correction}
            onChange={(e) => setCorrection(e.target.value)}
            placeholder="Enter correction..."
            className="flex-1 px-2 py-1 rounded text-sm bg-[var(--bg-base)] border border-[var(--border)] text-[var(--text-primary)] placeholder:text-[var(--text-secondary)] focus:outline-none focus:border-[var(--accent)]"
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleCorrect();
              if (e.key === 'Escape') setStatus('idle');
            }}
            autoFocus
          />
          <button
            onClick={handleCorrect}
            disabled={!correction.trim()}
            className="px-2 py-1 rounded text-[10px] font-mono uppercase tracking-wider text-[var(--accent)] border border-[rgba(46,102,255,0.3)] hover:bg-[rgba(46,102,255,0.1)] transition-colors disabled:opacity-40"
          >
            Submit
          </button>
        </div>
      )}
    </div>
  );
}

export function MemoryDeltaCard({ data }: MemoryDeltaCardProps) {
  if (!data || !data.facts || data.facts.length === 0) return null;

  return (
    <div
      className="rounded-lg border border-[var(--border)] px-4 py-3"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id="memory-delta-card"
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-mono uppercase tracking-wider text-[var(--accent)]">
          Memory Update
        </span>
        {data.domain && (
          <span className="text-[9px] font-mono uppercase tracking-wider text-[var(--text-secondary)]">
            {data.domain}
          </span>
        )}
      </div>
      {data.summary && (
        <p className="text-xs text-[var(--text-secondary)] mb-2 leading-relaxed">
          {data.summary}
        </p>
      )}
      <div className="space-y-1.5">
        {data.facts.map((fact) => (
          <FactRow key={fact.id} fact={fact} />
        ))}
      </div>
    </div>
  );
}
