import type { RichContent } from '@/api/chat';
import { GoalPlanCard } from './GoalPlanCard';
import { ExecutionPlanCard } from './ExecutionPlanCard';
import { MeetingCard } from './MeetingCard';
import { SignalCard } from './SignalCard';
import { AlertCard } from './AlertCard';

interface RichContentRendererProps {
  items: RichContent[];
}

export function RichContentRenderer({ items }: RichContentRendererProps) {
  if (items.length === 0) return null;

  return (
    <div className="mt-3 space-y-2">
      {items.map((item, i) => (
        <RichContentItem key={`${item.type}-${i}`} item={item} />
      ))}
    </div>
  );
}

function RichContentItem({ item }: { item: RichContent }) {
  switch (item.type) {
    case 'goal_plan':
      return <GoalPlanCard data={item.data as never} />;
    case 'execution_plan':
      return <ExecutionPlanCard data={item.data as never} />;
    case 'meeting_card':
      return <MeetingCard data={item.data as never} />;
    case 'signal_card':
      return <SignalCard data={item.data as never} />;
    case 'alert_card':
      return <AlertCard data={item.data as never} />;
    default:
      return (
        <div
          className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] px-3 py-2 text-xs text-[var(--text-secondary)]"
          data-aria-id={`rich-content-${item.type}`}
        >
          <span className="font-mono uppercase tracking-wider text-[var(--accent)]">
            {item.type}
          </span>
        </div>
      );
  }
}
