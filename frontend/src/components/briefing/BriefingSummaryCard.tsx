/**
 * BriefingSummaryCard - Post-briefing summary shown in conversation
 *
 * Displays after video briefing ends. Shows key points, action items,
 * and a replay link. Action items are clickable with contextual follow-up.
 */

import { CheckCircle2, Circle, RotateCcw, ArrowRight } from 'lucide-react';
import { cn } from '@/utils/cn';
import type { BriefingActionItem } from '@/api/briefings';

interface BriefingSummaryCardProps {
  briefingId: string;
  completedAt: string; // ISO timestamp
  keyPoints: string[];
  actionItems: BriefingActionItem[];
  onReplay: () => void; // Navigate to /briefing?replay=true
  onActionItemClick: (item: BriefingActionItem) => void; // Send contextual message
}

export function BriefingSummaryCard({
  completedAt,
  keyPoints,
  actionItems,
  onReplay,
  onActionItemClick,
}: BriefingSummaryCardProps) {
  // Format completed time
  const formatTime = (isoString: string) => {
    const date = new Date(isoString);
    return date.toLocaleTimeString('en-US', {
      hour: 'numeric',
      minute: '2-digit',
      hour12: true,
    });
  };

  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{
        backgroundColor: 'var(--bg-elevated)',
        border: '1px solid var(--border)',
      }}
      data-aria-id="briefing-summary-card"
    >
      {/* Header */}
      <div
        className="flex items-center justify-between px-4 py-3"
        style={{ backgroundColor: 'var(--bg-subtle)' }}
      >
        <div className="flex items-center gap-2">
          <CheckCircle2
            className="w-4 h-4"
            style={{ color: 'var(--accent)' }}
          />
          <span
            className="text-sm font-medium"
            style={{ color: 'var(--text-primary)' }}
          >
            Briefing Complete
          </span>
        </div>
        <span
          className="text-xs font-mono"
          style={{ color: 'var(--text-secondary)' }}
        >
          {formatTime(completedAt)}
        </span>
      </div>

      {/* Content */}
      <div className="p-4 space-y-4">
        {/* Key points */}
        <div>
          <h4
            className="text-xs font-medium uppercase tracking-wide mb-2"
            style={{ color: 'var(--text-secondary)' }}
          >
            What ARIA covered
          </h4>
          <ul className="space-y-1.5">
            {keyPoints.map((point, index) => (
              <li
                key={index}
                className="flex items-start gap-2 text-sm"
                style={{ color: 'var(--text-primary)' }}
              >
                <span
                  className="mt-1.5 w-1.5 h-1.5 rounded-full flex-shrink-0"
                  style={{ backgroundColor: 'var(--accent)' }}
                />
                <span>{point}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Action items */}
        {actionItems.length > 0 && (
          <div>
            <h4
              className="text-xs font-medium uppercase tracking-wide mb-2"
              style={{ color: 'var(--text-secondary)' }}
            >
              Action items
            </h4>
            <ul className="space-y-1.5">
              {actionItems.map((item) => (
                <li key={item.id}>
                  <button
                    onClick={() => onActionItemClick(item)}
                    className={cn(
                      'w-full flex items-center gap-2 p-2 rounded-lg text-sm text-left',
                      'transition-colors',
                      'hover:bg-[var(--accent)]/5'
                    )}
                  >
                    {item.status === 'done' ? (
                      <CheckCircle2
                        className="w-4 h-4 flex-shrink-0"
                        style={{ color: 'var(--accent)' }}
                      />
                    ) : (
                      <Circle
                        className="w-4 h-4 flex-shrink-0"
                        style={{ color: 'var(--text-secondary)' }}
                      />
                    )}
                    <span
                      className="flex-1"
                      style={{ color: item.status === 'done' ? 'var(--text-secondary)' : 'var(--text-primary)' }}
                    >
                      {item.text}
                    </span>
                    <span
                      className="text-xs px-1.5 py-0.5 rounded"
                      style={{
                        backgroundColor: item.status === 'done' ? 'var(--accent)' : 'var(--bg-subtle)',
                        color: item.status === 'done' ? 'white' : 'var(--text-secondary)',
                      }}
                    >
                      {item.status}
                    </span>
                    <ArrowRight
                      className="w-3.5 h-3.5 flex-shrink-0 opacity-0 group-hover:opacity-100"
                      style={{ color: 'var(--accent)' }}
                    />
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Replay link */}
        <button
          onClick={onReplay}
          className={cn(
            'flex items-center gap-1.5 text-sm',
            'transition-colors',
            'hover:opacity-80'
          )}
          style={{ color: 'var(--accent)' }}
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>Replay briefing</span>
        </button>
      </div>
    </div>
  );
}
