/**
 * CompetitorActivityTimeline - Chronological competitor signal activity
 *
 * Shows a bar-chart-style timeline of competitor signals over the last 30 days.
 * Top 3 competitors by signal count, with deduped (cluster primary only) signals.
 * Data from GET /api/v1/intelligence/competitor-activity.
 */

import { BarChart3 } from 'lucide-react';
import { useCompetitorActivity } from '@/hooks/useIntelPanelData';
import { sanitizeSignalText } from '@/utils/sanitizeSignalText';

const SIGNAL_TYPE_COLORS: Record<string, string> = {
  funding: '#22c55e',
  fda_approval: '#3b82f6',
  clinical_trial: '#a855f7',
  patent: '#f59e0b',
  leadership: '#64748b',
  earnings: '#10b981',
  partnership: '#6366f1',
  regulatory: '#f97316',
  product: '#06b6d4',
  hiring: '#ec4899',
};

function formatSignalDate(dateStr: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString('en-US', { month: 'numeric', day: 'numeric' });
}

function capitalizeFirst(str: string): string {
  return str.charAt(0).toUpperCase() + str.slice(1).replace(/_/g, ' ');
}

export function CompetitorActivityTimeline() {
  const { data: activityData, isLoading } = useCompetitorActivity(30);

  if (isLoading) {
    return (
      <section>
        <h2
          className="text-base font-medium mb-4 flex items-center gap-2"
          style={{ color: 'var(--text-primary)' }}
        >
          <BarChart3 className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
          Competitor Activity
        </h2>
        <div className="space-y-4 animate-pulse">
          <div className="h-24 rounded-xl" style={{ backgroundColor: '#F1F5F9' }} />
          <div className="h-24 rounded-xl" style={{ backgroundColor: '#F1F5F9' }} />
        </div>
      </section>
    );
  }

  const activity = activityData?.activity ?? [];
  if (activity.length === 0) return null;

  const topCompetitors = activity.slice(0, 5);
  const maxSignals = Math.max(...topCompetitors.map((c) => c.signal_count));

  return (
    <section>
      <h2
        className="text-base font-medium mb-4 flex items-center gap-2"
        style={{ color: 'var(--text-primary)' }}
      >
        <BarChart3 className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
        Competitor Activity
        <span
          className="text-xs font-normal ml-1"
          style={{ color: 'var(--text-secondary)' }}
        >
          ({activityData?.days ?? 30} days)
        </span>
      </h2>

      <div
        className="rounded-xl border overflow-hidden"
        style={{ backgroundColor: '#FFFFFF', borderColor: '#E2E8F0' }}
      >
        {topCompetitors.map((competitor, idx) => {
          const barWidth = maxSignals > 0 ? (competitor.signal_count / maxSignals) * 100 : 0;
          const isLast = idx === topCompetitors.length - 1;

          return (
            <div
              key={competitor.competitor}
              className="p-4"
              style={{
                borderBottom: isLast ? 'none' : '1px solid #F1F5F9',
              }}
            >
              {/* Competitor name + signal count bar */}
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium" style={{ color: '#1E293B' }}>
                  {competitor.competitor}
                </span>
                <span className="text-xs font-mono" style={{ color: '#5B6E8A' }}>
                  {competitor.signal_count} signal{competitor.signal_count !== 1 ? 's' : ''}
                </span>
              </div>

              {/* Activity bar */}
              <div className="h-2 rounded-full mb-3" style={{ backgroundColor: '#F1F5F9' }}>
                <div
                  className="h-full rounded-full transition-all"
                  style={{
                    width: `${barWidth}%`,
                    background: `linear-gradient(90deg, #2E66FF, #60A5FA)`,
                    minWidth: barWidth > 0 ? '8px' : '0',
                  }}
                />
              </div>

              {/* Signal timeline */}
              <div className="space-y-1 ml-2">
                {competitor.signals.slice(0, 4).map((signal, i) => {
                  const typeColor = SIGNAL_TYPE_COLORS[signal.signal_type] ?? '#94A3B8';
                  return (
                    <div key={i} className="flex items-start gap-2">
                      {/* Tree line */}
                      <div className="flex flex-col items-center flex-shrink-0 mt-1">
                        <span
                          className="w-1.5 h-1.5 rounded-full"
                          style={{ backgroundColor: typeColor }}
                        />
                        {i < Math.min(competitor.signals.length - 1, 3) && (
                          <span
                            className="w-px flex-1 min-h-[12px]"
                            style={{ backgroundColor: '#E2E8F0' }}
                          />
                        )}
                      </div>
                      <div className="flex-1 min-w-0 pb-1">
                        <span className="text-xs" style={{ color: '#94A3B8' }}>
                          {formatSignalDate(signal.detected_at)}
                        </span>
                        <span className="text-xs mx-1.5" style={{ color: typeColor }}>
                          {capitalizeFirst(signal.signal_type)}:
                        </span>
                        <span className="text-xs" style={{ color: '#5B6E8A' }}>
                          {sanitizeSignalText(signal.headline, 80)}
                        </span>
                      </div>
                    </div>
                  );
                })}
                {competitor.signals.length > 4 && (
                  <div className="text-[10px] ml-4" style={{ color: '#94A3B8' }}>
                    +{competitor.signals.length - 4} more signal{competitor.signals.length - 4 !== 1 ? 's' : ''}
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
