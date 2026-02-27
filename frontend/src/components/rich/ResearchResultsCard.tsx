import { BookOpen, ExternalLink, Bookmark, Loader2 } from 'lucide-react';
import { useState } from 'react';

export interface ResearchResult {
  title: string;
  authors?: string;
  date?: string;
  excerpt?: string;
  url?: string;
  source?: string;
}

export interface ResearchResultsData {
  query: string;
  total_count: number;
  results: ResearchResult[];
  source?: string;
}

export function ResearchResultsCard({ data }: { data: ResearchResultsData }) {
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  if (!data?.results) return null;

  const handleSave = async () => {
    setSaving(true);
    try {
      const { apiClient } = await import('@/api/client');
      await apiClient.post('/intelligence/save', {
        type: 'research',
        query: data.query,
        results: data.results,
        source: data.source,
      });
      setSaved(true);
    } catch {
      setSaving(false);
    }
  };

  const remaining = data.total_count - data.results.length;

  return (
    <div
      className="rounded-lg border border-[var(--border)] overflow-hidden"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id="research-results-card"
    >
      <div
        className="flex items-center justify-between px-4 py-2.5"
        style={{
          borderBottom: '1px solid var(--border)',
          backgroundColor: 'rgba(139,92,246,0.05)',
        }}
      >
        <div className="flex items-center gap-2">
          <BookOpen className="w-3.5 h-3.5 text-violet-400" />
          <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
            Research Results
          </span>
        </div>
        <span className="text-[10px] font-mono" style={{ color: 'var(--text-secondary)' }}>
          {data.total_count} found
        </span>
      </div>

      <div className="divide-y" style={{ borderColor: 'var(--border)' }}>
        {data.results.map((result, i) => (
          <div key={i} className="px-4 py-2.5">
            <div className="flex items-start justify-between gap-2">
              <p className="text-xs font-medium leading-snug" style={{ color: 'var(--text-primary)' }}>
                {result.title}
              </p>
              {result.url && (
                <a
                  href={result.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="shrink-0 mt-0.5"
                >
                  <ExternalLink className="w-3 h-3" style={{ color: 'var(--text-secondary)' }} />
                </a>
              )}
            </div>
            <div className="flex items-center gap-2 mt-1 text-[10px] font-mono" style={{ color: 'var(--text-secondary)' }}>
              {result.authors && <span>{result.authors}</span>}
              {result.date && <span>{result.date}</span>}
              {result.source && (
                <span className="px-1 py-0.5 rounded bg-violet-500/10 text-violet-400">
                  {result.source}
                </span>
              )}
            </div>
            {result.excerpt && (
              <p className="text-[11px] mt-1 leading-relaxed" style={{ color: 'var(--text-secondary)' }}>
                {result.excerpt}
              </p>
            )}
          </div>
        ))}
      </div>

      <div
        className="flex items-center justify-between px-4 py-2"
        style={{ borderTop: '1px solid var(--border)' }}
      >
        {remaining > 0 && (
          <span className="text-[10px] font-mono" style={{ color: 'var(--text-secondary)' }}>
            +{remaining} more
          </span>
        )}
        <div className="ml-auto">
          {!saved ? (
            <button
              type="button"
              disabled={saving}
              onClick={handleSave}
              className="flex items-center gap-1.5 px-2.5 py-1 rounded text-[10px] font-mono uppercase tracking-wider transition-colors"
              style={{
                color: 'var(--accent)',
                border: '1px solid rgba(46,102,255,0.3)',
              }}
            >
              {saving ? (
                <Loader2 className="w-3 h-3 animate-spin" />
              ) : (
                <Bookmark className="w-3 h-3" />
              )}
              Save to Intelligence
            </button>
          ) : (
            <span className="text-[10px] font-mono uppercase tracking-wider text-emerald-400">
              Saved
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
