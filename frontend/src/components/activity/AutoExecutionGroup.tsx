/**
 * AutoExecutionGroup — Collapsed row for auto-executed actions in ActivityFeed.
 *
 * Groups consecutive auto-executed items of the same type into a single
 * collapsible row: "[AgentAvatar] ARIA auto-sent 3 follow-up emails today — 2h ago"
 * Click to expand and see individual items.
 */

import { memo, useState } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { AgentAvatar } from '@/components/common/AgentAvatar';
import { resolveAgent } from '@/constants/agents';
import type { ActivityItem } from '@/api/activity';

/** Maps activity_type → human-readable group label (with count placeholder). */
const GROUP_LABELS: Record<string, (n: number) => string> = {
  email_drafted: (n) => `auto-sent ${n} follow-up email${n !== 1 ? 's' : ''}`,
  crm_update: (n) => `auto-updated ${n} CRM record${n !== 1 ? 's' : ''}`,
  lead_discovered: (n) => `auto-qualified ${n} new lead${n !== 1 ? 's' : ''}`,
  meeting_prepped: (n) => `auto-prepped ${n} meeting${n !== 1 ? 's' : ''}`,
};

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return date.toLocaleDateString();
}

interface AutoExecutionGroupProps {
  items: ActivityItem[];
  activityType: string;
}

export const AutoExecutionGroup = memo(function AutoExecutionGroup({
  items,
  activityType,
}: AutoExecutionGroupProps) {
  const [expanded, setExpanded] = useState(false);

  if (items.length === 0) return null;

  const labelFn = GROUP_LABELS[activityType] ?? ((n: number) => `auto-completed ${n} action${n !== 1 ? 's' : ''}`);
  const primaryAgent = items[0].agent;
  const agent = primaryAgent ? resolveAgent(primaryAgent) : null;
  const mostRecentTime = items[0].created_at;

  return (
    <div
      className="border border-[var(--border)] rounded-lg overflow-hidden"
      style={{ backgroundColor: 'var(--bg-elevated)' }}
    >
      {/* Collapsed summary row */}
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className="w-full flex items-center gap-3 p-3 text-left transition-colors hover:bg-[var(--bg-subtle)]"
      >
        {/* Agent avatar */}
        <div
          className="w-7 h-7 rounded-full flex items-center justify-center shrink-0"
          style={{
            backgroundColor: agent?.color ? `${agent.color}15` : 'var(--bg-subtle)',
            color: agent?.color ?? 'var(--text-secondary)',
          }}
        >
          {agent ? (
            <AgentAvatar agentKey={agent.type} size={20} />
          ) : (
            <span className="text-xs">A</span>
          )}
        </div>

        {/* Label */}
        <p className="flex-1 text-xs text-[var(--text-primary)] truncate">
          <span className="font-medium">ARIA</span>{' '}
          <span className="text-[var(--text-secondary)]">{labelFn(items.length)}</span>
        </p>

        {/* Timestamp */}
        <span className="text-[10px] font-mono text-[var(--text-secondary)] shrink-0">
          {formatRelativeTime(mostRecentTime)}
        </span>

        {/* Expand chevron */}
        {expanded ? (
          <ChevronUp className="w-3.5 h-3.5 text-[var(--text-secondary)] shrink-0" />
        ) : (
          <ChevronDown className="w-3.5 h-3.5 text-[var(--text-secondary)] shrink-0" />
        )}
      </button>

      {/* Expanded items */}
      <AnimatePresence>
        {expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="border-t border-[var(--border)] px-3 py-2 space-y-2">
              {items.map((item) => (
                <div key={item.id} className="flex items-center gap-2 py-1">
                  <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ backgroundColor: 'var(--accent)' }} />
                  <p className="text-xs text-[var(--text-primary)] truncate flex-1">{item.title}</p>
                  <span className="text-[10px] font-mono text-[var(--text-secondary)] shrink-0">
                    {formatRelativeTime(item.created_at)}
                  </span>
                </div>
              ))}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
});
