/**
 * VideoBriefingCard - Card shown when a video briefing is ready
 *
 * Displays in ARIA Workspace when briefing is ready and not yet viewed.
 * User can play video, dismiss, or read text instead.
 */

import { Play, Clock, ChevronRight, FileText } from 'lucide-react';
import { cn } from '@/utils/cn';

interface VideoBriefingCardProps {
  briefingId: string;
  duration: number; // 2, 5, or 10 minutes
  topics: string[]; // Top 3 topics preview
  onPlay: () => void; // Navigate to /briefing
  onDismiss: () => void; // Collapse to conversation
  onReadInstead: () => void; // Show text briefing
}

export function VideoBriefingCard({
  duration,
  topics,
  onPlay,
  onDismiss,
  onReadInstead,
}: VideoBriefingCardProps) {
  // Get time of day greeting
  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good morning';
    if (hour < 17) return 'Good afternoon';
    return 'Good evening';
  };

  // Format topics preview — convert any snake_case to Title Case as safety net
  const formatTopic = (topic: string) =>
    topic.includes('_') ? topic.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()) : topic;
  const topicsPreview = topics.slice(0, 3).map(formatTopic).join(', ') || 'Your daily briefing';

  return (
    <div
      className="rounded-xl p-6"
      style={{
        background: 'linear-gradient(135deg, #15161E 0%, #1a1b26 100%)',
        border: '1px solid rgba(46, 102, 255, 0.2)',
      }}
      data-aria-id="video-briefing-card"
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-2">
        <h2
          className="text-xl font-medium"
          style={{ color: 'var(--text-primary)' }}
        >
          {getGreeting()}
        </h2>
      </div>

      <p
        className="text-sm mb-4"
        style={{ color: 'var(--text-secondary)' }}
      >
        I've prepared your daily briefing
      </p>

      {/* Play card */}
      <button
        onClick={onPlay}
        className={cn(
          'w-full rounded-lg p-4 mb-4',
          'flex items-center gap-4',
          'transition-all duration-200',
          'hover:scale-[1.02] hover:shadow-lg',
          'cursor-pointer'
        )}
        style={{
          background: 'linear-gradient(135deg, rgba(46, 102, 255, 0.15) 0%, rgba(46, 102, 255, 0.05) 100%)',
          border: '1px solid rgba(46, 102, 255, 0.3)',
        }}
      >
        {/* Play button */}
        <div
          className="flex items-center justify-center w-12 h-12 rounded-full"
          style={{ backgroundColor: 'var(--accent)' }}
        >
          <Play className="w-5 h-5 text-white ml-0.5" />
        </div>

        {/* Content */}
        <div className="flex-1 text-left">
          <div className="flex items-center gap-2 mb-1">
            <Clock className="w-3.5 h-3.5" style={{ color: 'var(--accent)' }} />
            <span
              className="text-sm font-medium"
              style={{ color: 'var(--text-primary)' }}
            >
              {duration > 0 ? `${duration} min briefing ready` : 'Briefing ready'}
            </span>
          </div>
          <p
            className="text-xs"
            style={{ color: 'var(--text-secondary)' }}
          >
            Today: {topicsPreview}
          </p>
        </div>

        <ChevronRight
          className="w-5 h-5"
          style={{ color: 'var(--text-secondary)' }}
        />
      </button>

      {/* Action buttons */}
      <div className="flex items-center justify-between">
        <button
          onClick={onDismiss}
          className={cn(
            'px-3 py-1.5 rounded-lg text-sm',
            'transition-colors',
            'hover:bg-white/5'
          )}
          style={{ color: 'var(--text-secondary)' }}
        >
          Maybe later
        </button>

        <button
          onClick={onReadInstead}
          className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm',
            'transition-colors',
            'hover:bg-white/5'
          )}
          style={{ color: 'var(--text-secondary)' }}
        >
          <FileText className="w-3.5 h-3.5" />
          Read instead
        </button>
      </div>
    </div>
  );
}
