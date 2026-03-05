/**
 * VideoBriefingCard - Card shown when a video briefing is ready
 *
 * Displays in ARIA Workspace when briefing is ready and not yet viewed.
 * User can watch video, read summary (C1 stream), or skip.
 */

import { Play, ChevronRight, FileText, X } from 'lucide-react';
import { cn } from '@/utils/cn';

interface VideoBriefingCardProps {
  briefingId: string;
  duration: number; // 2, 5, or 10 minutes
  topics: string[]; // Summary line topics from /status endpoint
  userName?: string; // User's first name for greeting
  onPlay: () => void; // Navigate to /briefing
  onRead: () => void; // Trigger C1 stream
  onSkip: () => void; // Collapse to minimal bar
  isCollapsed?: boolean; // Show minimal bar when true
  onExpand?: () => void; // Expand from collapsed state
}

export function VideoBriefingCard({
  duration,
  topics,
  userName,
  onPlay,
  onRead,
  onSkip,
  isCollapsed = false,
  onExpand,
}: VideoBriefingCardProps) {
  // Get time of day greeting (using EST/business hours logic)
  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour >= 5 && hour < 12) return 'Good morning';
    if (hour >= 12 && hour < 17) return 'Good afternoon';
    return 'Good evening';
  };

  // Build summary line from topics array
  const summaryLine = topics.slice(0, 3).join(' · ') || 'Your daily briefing is ready';

  // Get first name from full name
  const firstName = userName ? userName.split(' ')[0] : null;

  // Collapsed state - minimal bar
  if (isCollapsed) {
    return (
      <div
        className="rounded-lg px-4 py-3 flex items-center justify-between"
        style={{
          backgroundColor: '#161B2E',
          border: '1px solid #2A2F42',
        }}
        data-aria-id="video-briefing-card-collapsed"
      >
        <div className="flex items-center gap-2">
          <span className="text-sm" style={{ color: '#A0AEC0' }}>
            Daily briefing available
          </span>
          {duration > 0 && (
            <span className="text-xs" style={{ color: '#666' }}>
              ({duration} min)
            </span>
          )}
        </div>
        <button
          onClick={onExpand}
          className={cn(
            'flex items-center gap-1 px-3 py-1.5 rounded-lg text-sm',
            'transition-colors',
            'hover:bg-white/5'
          )}
          style={{ color: '#2E66FF' }}
        >
          Open
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    );
  }

  // Full card state
  return (
    <div
      className="rounded-xl p-6"
      style={{
        backgroundColor: '#161B2E',
        border: '1px solid #2A2F42',
      }}
      data-aria-id="video-briefing-card"
    >
      {/* Header */}
      <div className="flex items-center justify-between mb-2">
        <h2
          className="text-xl font-medium"
          style={{ color: '#fff' }}
        >
          {getGreeting()}{firstName ? `, ${firstName}` : ''}
        </h2>
        <button
          onClick={onSkip}
          className="p-1.5 rounded-lg hover:bg-white/5 transition-colors"
          style={{ color: '#666' }}
          aria-label="Skip briefing"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <p
        className="text-sm mb-3"
        style={{ color: '#A0AEC0' }}
      >
        I've prepared your daily briefing
      </p>

      {/* Summary line */}
      <p
        className="text-sm mb-5"
        style={{ color: '#A0AEC0' }}
      >
        {summaryLine}
      </p>

      {/* Three pill buttons */}
      <div className="flex items-center gap-3">
        {/* Watch Video - primary action */}
        <button
          onClick={onPlay}
          className={cn(
            'flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium',
            'transition-all duration-200',
            'hover:opacity-90'
          )}
          style={{
            backgroundColor: '#2E66FF',
            color: '#fff',
            height: '40px',
          }}
        >
          <Play className="w-4 h-4" />
          Watch Video
        </button>

        {/* Read Summary - secondary action */}
        <button
          onClick={onRead}
          className={cn(
            'flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium',
            'transition-all duration-200',
            'hover:bg-[#2A2F42]'
          )}
          style={{
            backgroundColor: 'transparent',
            border: '1px solid #2A2F42',
            color: '#A0AEC0',
            height: '40px',
          }}
        >
          <FileText className="w-4 h-4" />
          Read Summary
        </button>

        {/* Skip - tertiary action */}
        <button
          onClick={onSkip}
          className={cn(
            'px-4 py-2.5 rounded-lg text-sm',
            'transition-colors',
            'hover:bg-white/5'
          )}
          style={{
            backgroundColor: 'transparent',
            color: '#666',
            height: '40px',
          }}
        >
          Skip
        </button>
      </div>
    </div>
  );
}
