import { useState } from 'react';
import { Video, Phone, ChevronDown, ChevronUp, CheckCircle2, Clock } from 'lucide-react';
import type { VideoSessionSummaryData } from '@/types/chat';

function formatDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  if (mins < 1) return '<1 min';
  return `${mins} min`;
}

function formatTimestamp(ts: string): string {
  const date = new Date(ts);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function VideoSessionSummaryCard({ data }: { data: VideoSessionSummaryData }) {
  const [expanded, setExpanded] = useState(false);
  const Icon = data.is_audio_only ? Phone : Video;
  const label = data.is_audio_only ? 'Voice Call' : 'Video Session';
  const topicCount = data.topics.length;
  const actionCount = data.action_items.length;

  return (
    <div
      className="rounded-lg border border-[var(--border)] overflow-hidden"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
      data-aria-id="video-session-summary"
    >
      {/* Collapsed header — always visible */}
      <button
        onClick={() => setExpanded((v) => !v)}
        className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-[rgba(46,102,255,0.04)] transition-colors"
      >
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-[#2E66FF]/10 flex items-center justify-center flex-shrink-0">
            <Icon size={16} className="text-[#2E66FF]" />
          </div>
          <div>
            <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
              {label}
            </span>
            <div className="flex items-center gap-3 mt-0.5">
              <span className="flex items-center gap-1 font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                <Clock size={10} />
                {formatDuration(data.duration_seconds)}
              </span>
              {topicCount > 0 && (
                <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                  {topicCount} topic{topicCount !== 1 ? 's' : ''}
                </span>
              )}
              {actionCount > 0 && (
                <span className="font-mono text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                  {actionCount} action item{actionCount !== 1 ? 's' : ''}
                </span>
              )}
            </div>
          </div>
        </div>

        {expanded ? (
          <ChevronUp size={16} className="text-[var(--text-secondary)]" />
        ) : (
          <ChevronDown size={16} className="text-[var(--text-secondary)]" />
        )}
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="border-t border-[var(--border)] px-4 py-3 space-y-4">
          {/* Action items */}
          {data.action_items.length > 0 && (
            <div>
              <h4 className="font-mono text-[10px] uppercase tracking-wider mb-2" style={{ color: 'var(--text-secondary)' }}>
                Action Items
              </h4>
              <ul className="space-y-1.5">
                {data.action_items.map((item, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <CheckCircle2
                      size={14}
                      className="mt-0.5 flex-shrink-0"
                      style={{ color: item.is_tracked ? '#2E66FF' : 'var(--text-secondary)' }}
                    />
                    <span className="text-xs" style={{ color: 'var(--text-primary)' }}>
                      {item.text}
                    </span>
                    {item.is_tracked && (
                      <span className="ml-auto flex-shrink-0 font-mono text-[10px] px-1.5 py-0.5 rounded bg-[#2E66FF]/10 text-[#2E66FF]">
                        Tracked
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Topics */}
          {data.topics.length > 0 && (
            <div>
              <h4 className="font-mono text-[10px] uppercase tracking-wider mb-2" style={{ color: 'var(--text-secondary)' }}>
                Topics Discussed
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {data.topics.map((topic, i) => (
                  <span
                    key={i}
                    className="text-[11px] px-2 py-0.5 rounded-full border border-[var(--border)]"
                    style={{ color: 'var(--text-secondary)' }}
                  >
                    {topic}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Transcript */}
          {data.transcript_entries.length > 0 && (
            <div>
              <h4 className="font-mono text-[10px] uppercase tracking-wider mb-2" style={{ color: 'var(--text-secondary)' }}>
                Transcript
              </h4>
              <div
                className="max-h-[300px] overflow-y-auto space-y-2 rounded-lg p-3"
                style={{ backgroundColor: 'rgba(0,0,0,0.15)' }}
              >
                {data.transcript_entries.map((entry, i) => (
                  <div key={i} className="flex gap-2 text-xs">
                    <span className="font-mono text-[10px] flex-shrink-0 mt-0.5" style={{ color: 'var(--text-secondary)' }}>
                      {formatTimestamp(entry.timestamp)}
                    </span>
                    <span className="font-semibold flex-shrink-0" style={{ color: entry.speaker === 'aria' ? '#2E66FF' : 'var(--text-primary)' }}>
                      {entry.speaker === 'aria' ? 'ARIA' : 'You'}:
                    </span>
                    <span style={{ color: 'var(--text-primary)' }}>{entry.text}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Watch recording — future */}
          <div className="pt-1">
            <span className="text-[11px] italic" style={{ color: 'var(--text-secondary)' }}>
              Watch recording (coming soon)
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
