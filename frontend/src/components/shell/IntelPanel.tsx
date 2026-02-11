/**
 * IntelPanel - ARIA Intelligence Panel (right column)
 *
 * The context-adaptive right panel in ARIA's three-column layout.
 * Displays route-specific intelligence, alerts, and agent status.
 * Width: 320px (w-80). Always renders content — visibility is
 * controlled by the parent (AppShell).
 *
 * Design System:
 * - Background: var(--bg-elevated)
 * - Left border: 1px solid var(--border)
 * - Title: Instrument Serif (font-display)
 * - Body: Satoshi/Inter (font-sans)
 * - Data labels: JetBrains Mono (font-mono)
 */

import { useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import { MoreHorizontal } from 'lucide-react';

interface IntelPanelProps {
  /** Additional CSS classes from parent for positioning */
  className?: string;
}

interface PanelConfig {
  title: string;
  description: string;
  items: string[];
}

function getPanelConfig(pathname: string): PanelConfig {
  if (pathname.startsWith('/pipeline')) {
    return {
      title: 'Pipeline Alerts',
      description:
        'Real-time signals and risk indicators across your active pipeline.',
      items: [
        'Deal velocity changes detected by Scout',
        'Stalled opportunities flagged by Analyst',
        'Competitive signals from Hunter',
      ],
    };
  }

  if (pathname.startsWith('/intelligence')) {
    return {
      title: 'ARIA Intel',
      description:
        'Curated intelligence from across your connected data sources.',
      items: [
        'Market signals and competitor movements',
        'Account-level insights from Analyst',
        'Relationship mapping updates from Scout',
      ],
    };
  }

  if (pathname.startsWith('/communications')) {
    return {
      title: 'ARIA Insights',
      description:
        'Contextual suggestions for your outreach and follow-ups.',
      items: [
        'Optimal send-time recommendations',
        'Tone and messaging guidance from Scribe',
        'Follow-up priority scoring',
      ],
    };
  }

  if (pathname.startsWith('/actions')) {
    return {
      title: 'Agent Status',
      description: 'Live status of ARIA\'s six core agents and active tasks.',
      items: [
        'Hunter, Analyst, Strategist activity',
        'Scribe, Operator, Scout task queues',
        'Pending approvals and completions',
      ],
    };
  }

  return {
    title: 'ARIA Intelligence',
    description:
      'Contextual intelligence that updates based on your current focus.',
    items: [
      'Signals will appear as ARIA detects them',
      'Agent activity and goal progress',
      'Proactive recommendations',
    ],
  };
}

export function IntelPanel({ className }: IntelPanelProps) {
  const location = useLocation();

  const config = useMemo(
    () => getPanelConfig(location.pathname),
    [location.pathname]
  );

  return (
    <aside
      className={`w-80 flex-shrink-0 flex flex-col h-full border-l ${className ?? ''}`}
      style={{
        borderColor: 'var(--border)',
        backgroundColor: 'var(--bg-elevated)',
      }}
      data-aria-id="intel-panel"
    >
      {/* Header */}
      <div
        className="h-14 flex items-center justify-between px-5 flex-shrink-0 border-b"
        style={{ borderColor: 'var(--border)' }}
      >
        <h2
          className="font-display text-[18px] leading-tight italic"
          style={{ color: 'var(--text-primary)' }}
        >
          {config.title}
        </h2>
        <button
          className="p-1.5 rounded-md transition-colors duration-150 cursor-pointer"
          style={{ color: 'var(--text-secondary)' }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = 'var(--bg-subtle)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'transparent';
          }}
          aria-label="Panel options"
        >
          <MoreHorizontal size={18} strokeWidth={1.5} />
        </button>
      </div>

      {/* Scrollable Content */}
      <div className="flex-1 overflow-y-auto px-5 py-4">
        {/* Description */}
        <p
          className="font-sans text-[13px] leading-[1.6] mb-6"
          style={{ color: 'var(--text-secondary)' }}
        >
          {config.description}
        </p>

        {/* Placeholder items */}
        <div className="space-y-3">
          {config.items.map((item, index) => (
            <div
              key={index}
              className="rounded-lg p-3 border"
              style={{
                borderColor: 'var(--border)',
                backgroundColor: 'var(--bg-subtle)',
              }}
            >
              <div className="flex items-start gap-2.5">
                {/* Status dot */}
                <div
                  className="w-1.5 h-1.5 rounded-full mt-1.5 flex-shrink-0"
                  style={{ backgroundColor: 'var(--accent)' }}
                />
                <p
                  className="font-sans text-[13px] leading-[1.5]"
                  style={{ color: 'var(--text-primary)' }}
                >
                  {item}
                </p>
              </div>
            </div>
          ))}
        </div>

        {/* Timestamp placeholder */}
        <p
          className="font-mono text-[11px] mt-6"
          style={{ color: 'var(--text-secondary)' }}
        >
          Last updated: just now
        </p>
      </div>
    </aside>
  );
}
