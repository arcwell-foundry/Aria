/**
 * ChatIntelligencePanel - Collapsible right panel for ARIA Chat page
 *
 * Shows contextual intelligence while chatting:
 * - Upcoming meetings (max 3)
 * - Recent market signals (max 3)
 * - Quick stats (drafts, tasks, battle cards)
 *
 * 320px when open, collapses to a thin toggle bar.
 * State persisted in localStorage.
 */

import { useState, useEffect, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ChevronLeft,
  ChevronRight,
  Clock,
  Radio,
  Mail,
  CheckSquare,
  Swords,
  Users,
} from 'lucide-react';
import { useIntelligencePanel } from '@/hooks/useIntelligencePanel';
import type { UpcomingMeeting, RecentSignal } from '@/api/intelligencePanel';
import { sanitizeSignalText } from '@/utils/sanitizeSignalText';

const STORAGE_KEY = 'aria-intel-panel-open';

interface ChatIntelligencePanelProps {
  onSendMessage: (message: string) => void;
}

function getInitialOpen(): boolean {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored !== null) return stored === 'true';
  } catch {
    // localStorage unavailable
  }
  // Default: open on wide screens, closed on narrow
  return window.innerWidth >= 1200;
}

// --- Skeleton components ---

function MeetingSkeleton() {
  return (
    <div className="rounded-lg p-3 animate-pulse" style={{ backgroundColor: '#1A1A24' }}>
      <div className="h-3 w-16 rounded" style={{ backgroundColor: '#2A2F42' }} />
      <div className="h-4 w-40 rounded mt-2" style={{ backgroundColor: '#2A2F42' }} />
      <div className="h-3 w-20 rounded mt-1.5" style={{ backgroundColor: '#2A2F42' }} />
    </div>
  );
}

function SignalSkeleton() {
  return (
    <div className="rounded-lg p-3 animate-pulse" style={{ backgroundColor: '#1A1A24' }}>
      <div className="h-3 w-20 rounded" style={{ backgroundColor: '#2A2F42' }} />
      <div className="h-4 w-full rounded mt-2" style={{ backgroundColor: '#2A2F42' }} />
    </div>
  );
}

// --- Card components ---

function MeetingCard({
  meeting,
  onClick,
}: {
  meeting: UpcomingMeeting;
  onClick: () => void;
}) {
  const attendeeCount = meeting.attendees.length;

  return (
    <button
      onClick={onClick}
      className="w-full text-left rounded-lg p-3 transition-colors duration-150 cursor-pointer group"
      style={{ backgroundColor: '#1A1A24' }}
      onMouseEnter={(e) => {
        e.currentTarget.style.backgroundColor = '#1E2436';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.backgroundColor = '#1A1A24';
      }}
    >
      <div className="flex items-center gap-1.5">
        <Clock size={12} className="text-[#2E66FF] flex-shrink-0" />
        <span
          className="text-xs font-mono"
          style={{ color: '#2E66FF' }}
        >
          {meeting.time}
        </span>
      </div>
      <p
        className="text-sm mt-1 leading-snug line-clamp-2"
        style={{ color: '#E0E0E0' }}
      >
        {meeting.title}
      </p>
      <div className="flex items-center gap-2 mt-1">
        <span className="text-xs" style={{ color: '#666' }}>
          {meeting.date}
        </span>
        {attendeeCount > 0 && (
          <span className="flex items-center gap-1 text-xs" style={{ color: '#666' }}>
            <Users size={10} />
            {attendeeCount} {attendeeCount === 1 ? 'person' : 'people'}
          </span>
        )}
      </div>
    </button>
  );
}

function SignalCard({
  signal,
  onClick,
}: {
  signal: RecentSignal;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left rounded-lg p-3 transition-colors duration-150 cursor-pointer group"
      style={{ backgroundColor: '#1A1A24' }}
      onMouseEnter={(e) => {
        e.currentTarget.style.backgroundColor = '#1E2436';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.backgroundColor = '#1A1A24';
      }}
    >
      <div className="flex items-center gap-1.5">
        <Radio size={12} className="text-[#2E66FF] flex-shrink-0" />
        <span
          className="text-xs font-mono px-1.5 py-0.5 rounded"
          style={{ backgroundColor: '#2A2F42', color: '#8B8FA3' }}
        >
          {signal.type}
        </span>
      </div>
      <p
        className="text-sm mt-1.5 leading-snug line-clamp-2"
        style={{ color: '#E0E0E0' }}
      >
        {sanitizeSignalText(signal.headline)}
      </p>
    </button>
  );
}

function SectionHeader({ children }: { children: string }) {
  return (
    <h3
      className="text-[11px] font-semibold uppercase tracking-wider mb-3"
      style={{ color: '#555', fontFamily: 'Inter, sans-serif' }}
    >
      {children}
    </h3>
  );
}

function Divider() {
  return <div className="my-4" style={{ borderTop: '1px solid #2A2F42' }} />;
}

function StatRow({
  icon,
  label,
  count,
}: {
  icon: React.ReactNode;
  label: string;
  count: number;
}) {
  return (
    <div className="flex items-center gap-2.5 py-1.5">
      <span className="text-[#8B8FA3] flex-shrink-0">{icon}</span>
      <span className="text-sm" style={{ color: '#E0E0E0' }}>
        <span className="font-mono text-[#2E66FF]">{count}</span>{' '}
        {label}
      </span>
    </div>
  );
}

// --- Collapse toggle ---

function CollapseToggle({
  isOpen,
  onToggle,
}: {
  isOpen: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      onClick={onToggle}
      className="flex items-center justify-center transition-colors duration-150 cursor-pointer flex-shrink-0"
      style={{
        width: '24px',
        height: '100%',
        backgroundColor: '#121218',
        borderLeft: isOpen ? 'none' : '1px solid #2A2F42',
        borderRight: isOpen ? '1px solid #2A2F42' : 'none',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.backgroundColor = '#2E66FF';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.backgroundColor = '#121218';
      }}
      aria-label={isOpen ? 'Collapse intelligence panel' : 'Expand intelligence panel'}
      data-aria-id="intel-panel-toggle"
    >
      {isOpen ? (
        <ChevronRight size={14} className="text-[#8B8FA3]" />
      ) : (
        <div className="flex flex-col items-center gap-1">
          <ChevronLeft size={14} className="text-[#8B8FA3]" />
          <span
            className="text-[9px] font-semibold uppercase tracking-wider"
            style={{
              color: '#8B8FA3',
              writingMode: 'vertical-lr',
              textOrientation: 'mixed',
            }}
          >
            Intel
          </span>
        </div>
      )}
    </button>
  );
}

// --- Main component ---

export function ChatIntelligencePanel({ onSendMessage }: ChatIntelligencePanelProps) {
  const [isOpen, setIsOpen] = useState(getInitialOpen);
  const { data, isLoading } = useIntelligencePanel();

  // Persist open/closed state
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, String(isOpen));
    } catch {
      // localStorage unavailable
    }
  }, [isOpen]);

  const toggle = useCallback(() => setIsOpen((prev) => !prev), []);

  const handleMeetingClick = useCallback(
    (meeting: UpcomingMeeting) => {
      onSendMessage(`Prep me for my ${meeting.time} ${meeting.title} meeting`);
    },
    [onSendMessage],
  );

  const handleSignalClick = useCallback(
    (signal: RecentSignal) => {
      onSendMessage(`Tell me more about ${signal.headline}`);
    },
    [onSendMessage],
  );

  return (
    <div className="flex flex-shrink-0 h-full">
      {/* Toggle bar */}
      <CollapseToggle isOpen={isOpen} onToggle={toggle} />

      {/* Panel content */}
      <AnimatePresence initial={false}>
        {isOpen && (
          <motion.aside
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 320, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: 'easeInOut' }}
            className="flex flex-col h-full overflow-hidden"
            style={{
              backgroundColor: '#121218',
              borderLeft: '1px solid #2A2F42',
            }}
            data-aria-id="chat-intelligence-panel"
          >
            {/* Header */}
            <div
              className="flex items-center gap-2 px-4 py-3 flex-shrink-0"
              style={{ borderBottom: '1px solid #2A2F42' }}
            >
              <h2
                className="text-sm font-semibold uppercase tracking-wider"
                style={{ color: '#E0E0E0' }}
              >
                Intelligence
              </h2>
            </div>

            {/* Scrollable content */}
            <div className="flex-1 overflow-y-auto px-4 py-4">
              {/* UPCOMING MEETINGS */}
              <SectionHeader>Upcoming</SectionHeader>
              <div className="space-y-2">
                {isLoading ? (
                  <>
                    <MeetingSkeleton />
                    <MeetingSkeleton />
                  </>
                ) : data?.meetings.upcoming.length ? (
                  data.meetings.upcoming.map((meeting, i) => (
                    <MeetingCard
                      key={`meeting-${i}`}
                      meeting={meeting}
                      onClick={() => handleMeetingClick(meeting)}
                    />
                  ))
                ) : (
                  <p className="text-xs" style={{ color: '#555' }}>
                    No upcoming meetings
                  </p>
                )}
              </div>

              <Divider />

              {/* RECENT SIGNALS */}
              <SectionHeader>Recent Signals</SectionHeader>
              <div className="space-y-2">
                {isLoading ? (
                  <>
                    <SignalSkeleton />
                    <SignalSkeleton />
                  </>
                ) : data?.signals.recent.length ? (
                  data.signals.recent.map((signal, i) => (
                    <SignalCard
                      key={`signal-${i}`}
                      signal={signal}
                      onClick={() => handleSignalClick(signal)}
                    />
                  ))
                ) : (
                  <p className="text-xs" style={{ color: '#555' }}>
                    No recent signals
                  </p>
                )}
              </div>

              <Divider />

              {/* QUICK STATS */}
              <SectionHeader>Quick Stats</SectionHeader>
              {isLoading ? (
                <div className="space-y-2 animate-pulse">
                  <div className="h-4 w-32 rounded" style={{ backgroundColor: '#2A2F42' }} />
                  <div className="h-4 w-28 rounded" style={{ backgroundColor: '#2A2F42' }} />
                  <div className="h-4 w-36 rounded" style={{ backgroundColor: '#2A2F42' }} />
                </div>
              ) : data ? (
                <div>
                  <StatRow
                    icon={<Mail size={14} />}
                    label="drafts"
                    count={data.quick_stats.pending_drafts}
                  />
                  <StatRow
                    icon={<CheckSquare size={14} />}
                    label="open tasks"
                    count={data.quick_stats.open_tasks}
                  />
                  <StatRow
                    icon={<Swords size={14} />}
                    label="battle cards"
                    count={data.quick_stats.battle_cards}
                  />
                </div>
              ) : null}
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </div>
  );
}
