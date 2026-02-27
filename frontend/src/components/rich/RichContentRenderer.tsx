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
import { ChallengeCard, type ChallengeCardProps } from '@/components/friction';
import { IntegrationRequestCard, type IntegrationRequestData } from './IntegrationRequestCard';
import { GoalCompletionCard, type GoalCompletionData } from './GoalCompletionCard';
import { ExecutionSummaryCard, type ExecutionSummaryData } from './ExecutionSummaryCard';
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
    <div className="mt-3 space-y-2 max-w-full overflow-hidden">
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
    case 'integration_request':
      return <IntegrationRequestCard data={item.data as unknown as IntegrationRequestData} />;
    case 'goal_completion':
      return <GoalCompletionCard data={item.data as unknown as GoalCompletionData} />;
    case 'execution_summary':
      return <ExecutionSummaryCard data={item.data as unknown as ExecutionSummaryData} />;
    case 'plan_approved': {
      const pa = item.data as Record<string, unknown>;
      return (
        <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 px-4 py-3 my-2 max-w-full">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-emerald-500/20 text-emerald-400 text-xs">
              &#x2713;
            </span>
            <span className="text-emerald-300 font-medium text-sm">
              Plan approved — executing {(pa?.title as string) || 'your plan'}
            </span>
          </div>
        </div>
      );
    }
    case 'task_progress': {
      const tp = item.data as Record<string, unknown>;
      return (
        <div className="rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)] px-4 py-2 my-1 max-w-full">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-emerald-500/20 text-emerald-400 text-[10px]">
              &#x2713;
            </span>
            <span className="text-sm text-[var(--text-primary)]">
              <strong>{(tp?.task_title as string) || 'Task'}</strong>
              <span className="text-[var(--text-secondary)]"> complete</span>
            </span>
            {tp?.agent && (
              <span className="text-[9px] font-mono uppercase tracking-wider text-[var(--text-secondary)] ml-auto">
                {tp.agent as string}
              </span>
            )}
          </div>
        </div>
      );
    }
    case 'friction_decision': {
      const fd = item.data as unknown as Omit<ChallengeCardProps, 'onApprove' | 'onModify' | 'onCancel'>;
      return (
        <ChallengeCard
          frictionId={fd.frictionId}
          level={fd.level}
          reasoning={fd.reasoning}
          userMessage={fd.userMessage}
        />
      );
    }
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
