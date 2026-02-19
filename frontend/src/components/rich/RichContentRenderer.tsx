import type { RichContent } from '@/api/chat';
import type { BriefingActionItem } from '@/api/briefings';
import { GoalPlanCard, type GoalPlanData } from './GoalPlanCard';
import { ExecutionPlanCard, type ExecutionPlanData } from './ExecutionPlanCard';
import { MeetingCard, type MeetingCardData } from './MeetingCard';
import { SignalCard, type SignalCardData } from './SignalCard';
import { AlertCard, type AlertCardData } from './AlertCard';
import { ActionApprovalCard, type ActionApprovalData } from './ActionApprovalCard';
import { BriefingCard, type BriefingCardData } from './BriefingCard';
import { BriefingSummaryCard } from '@/components/briefing';
import { LeadCard, type LeadCardData } from './LeadCard';
import { BattleCard, type BattleCardData } from './BattleCard';
import { PipelineChart, type PipelineChartData } from './PipelineChart';
import { ResearchResultsCard, type ResearchResultsData } from './ResearchResultsCard';
import { EmailDraftCard, type EmailDraftData } from './EmailDraftCard';
import { VideoSessionSummaryCard } from './VideoSessionSummaryCard';
import type { VideoSessionSummaryData } from '@/types/chat';
import { ExecutionProgressCard } from './ExecutionProgressCard';
import type { ExecutionProgressData } from '@/types/execution';
import { useNavigate } from 'react-router-dom';
import { useConversationStore } from '@/stores/conversationStore';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';

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

interface BriefingSummaryData {
  key_points: string[];
  action_items: BriefingActionItem[];
  completed_at: string;
}

// Wrapper component for BriefingSummaryCard with handlers
function BriefingSummaryWrapper({ data }: { data: BriefingSummaryData }) {
  const navigate = useNavigate();
  const addMessage = useConversationStore((s) => s.addMessage);
  const activeConversationId = useConversationStore((s) => s.activeConversationId);
  const setActiveConversation = useConversationStore((s) => s.setActiveConversation);

  const handleReplay = () => {
    navigate('/briefing?replay=true');
  };

  const handleActionItemClick = (item: BriefingActionItem) => {
    // Ensure conversation exists
    let conversationId = activeConversationId;
    if (!conversationId) {
      conversationId = crypto.randomUUID();
      setActiveConversation(conversationId);
    }

    // Send contextual message
    addMessage({
      role: 'user',
      content: `I'd like to work on: ${item.text}`,
      rich_content: [],
      ui_commands: [],
      suggestions: [],
    });

    wsManager.send(WS_EVENTS.USER_MESSAGE, {
      message: `I'd like to work on: ${item.text}`,
      conversation_id: conversationId,
    });
  };

  return (
    <BriefingSummaryCard
      briefingId=""
      completedAt={data.completed_at}
      keyPoints={data.key_points}
      actionItems={data.action_items}
      onReplay={handleReplay}
      onActionItemClick={handleActionItemClick}
    />
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
    case 'action_approval':
      return <ActionApprovalCard data={item.data as unknown as ActionApprovalData} />;
    case 'briefing':
      return <BriefingCard data={item.data as unknown as BriefingCardData} />;
    case 'briefing_summary':
      return <BriefingSummaryWrapper data={item.data as unknown as BriefingSummaryData} />;
    case 'lead_card':
      return <LeadCard data={item.data as unknown as LeadCardData} />;
    case 'battle_card':
      return <BattleCard data={item.data as unknown as BattleCardData} />;
    case 'pipeline_chart':
      return <PipelineChart data={item.data as unknown as PipelineChartData} />;
    case 'research_results':
      return <ResearchResultsCard data={item.data as unknown as ResearchResultsData} />;
    case 'email_draft':
      return <EmailDraftCard data={item.data as unknown as EmailDraftData} />;
    case 'video_session_summary':
      return <VideoSessionSummaryCard data={item.data as unknown as VideoSessionSummaryData} />;
    case 'execution_progress':
      return <ExecutionProgressCard data={item.data as unknown as ExecutionProgressData} />;
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
