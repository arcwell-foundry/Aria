import type { RichContent } from '@/api/chat';
import { GoalPlanCard, type GoalPlanData } from './GoalPlanCard';
import { ExecutionPlanCard, type ExecutionPlanData } from './ExecutionPlanCard';
import { MeetingCard, type MeetingCardData } from './MeetingCard';
import { SignalCard, type SignalCardData } from './SignalCard';
import { AlertCard, type AlertCardData } from './AlertCard';
import { BriefingCard, type BriefingCardData } from './BriefingCard';

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
      return <GoalPlanCard data={item.data as unknown as GoalPlanData} />;
    case 'execution_plan':
      return <ExecutionPlanCard data={item.data as unknown as ExecutionPlanData} />;
    case 'meeting_card':
      return <MeetingCard data={item.data as unknown as MeetingCardData} />;
    case 'signal_card':
      return <SignalCard data={item.data as unknown as SignalCardData} />;
    case 'alert_card':
      return <AlertCard data={item.data as unknown as AlertCardData} />;
    case 'briefing':
      return <BriefingCard data={item.data as unknown as BriefingCardData} />;
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
