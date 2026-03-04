/**
 * C1MessageRenderer - Renders C1 generative UI content in chat messages
 *
 * This component wraps the Thesys C1Component and provides:
 * - Custom ARIA-specific React components
 * - Action handling integration with ARIA's action system
 * - Loading and error states
 */

import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { C1Component } from '@thesysai/genui-sdk';
import { Loader2 } from 'lucide-react';
import { approveGoalPlan, startGoal } from '@/api/goals';
import { dismissDraft, sendDraft } from '@/api/drafts';
import { markSignalRead } from '@/api/signals';
import { wsManager } from '@/core/WebSocketManager';
import {
  GoalPlanCard,
  EmailDraftCard,
  AgentStatusCard,
  SignalAlertCard,
  ApprovalCard,
} from '../c1';

/** C1 action event type (matches SDK's internal C1Action type) */
interface C1ActionEvent {
  type?: string;
  params?: Record<string, unknown>;
  humanFriendlyMessage?: string;
  llmFriendlyMessage?: string;
}

export interface C1MessageRendererProps {
  /** The C1 response content to render */
  c1Response: string;
  /** Whether the response is still streaming */
  isStreaming?: boolean;
  /** Handler for user actions from C1 components (sends message to conversation) */
  onSendMessage?: (message: string) => void;
  /** Additional CSS classes */
  className?: string;
}

/**
 * Custom components to pass to C1Component.
 * Keys must match the schema names registered with the backend.
 */
const customComponents = {
  GoalPlanCard,
  EmailDraftCard,
  AgentStatusCard,
  SignalAlertCard,
  ApprovalCard,
};

export function C1MessageRenderer({
  c1Response,
  isStreaming = false,
  onSendMessage,
  className = '',
}: C1MessageRendererProps) {
  const navigate = useNavigate();

  // Diagnostic: Log what we receive
  console.log('[C1MessageRenderer] Received c1Response:', {
    length: c1Response?.length ?? 0,
    preview: c1Response?.slice(0, 200),
    isStreaming,
  });

  // Handle C1 SDK errors - this tells us if parsing failed
  const handleC1Error = useCallback((error: { code: number; c1Response: string }) => {
    console.error('[C1MessageRenderer] C1 SDK error:', {
      code: error.code,
      responseLength: error.c1Response?.length,
      responsePreview: error.c1Response?.slice(0, 300),
    });
  }, []);

  const handleAction = useCallback(
    async (event: C1ActionEvent) => {
      // C1Action has optional type and params - handle missing type
      if (!event.type) {
        // Default to continue_conversation behavior
        const params = event.params ?? {};
        const message =
          (params.llmFriendlyMessage as string) ||
          (params.humanFriendlyMessage as string) ||
          event.llmFriendlyMessage ||
          event.humanFriendlyMessage ||
          '';
        if (message && onSendMessage) {
          onSendMessage(message);
        }
        return;
      }

      const params = event.params ?? {};

      try {
        switch (event.type) {
          // --- Goal Actions ---
          case 'approve_goal':
          case 'approve_plan': {
            const goalId = params.goal_id as string;
            await approveGoalPlan(goalId);
            navigate(`/goals/${goalId}`);
            break;
          }

          case 'modify_goal':
          case 'modify_plan': {
            const goalId = params.goal_id as string;
            if (onSendMessage) {
              onSendMessage(`I'd like to modify the plan for goal ${goalId}`);
            }
            break;
          }

          case 'start_goal': {
            const goalId = params.goal_id as string;
            await startGoal(goalId);
            navigate(`/goals/${goalId}`);
            break;
          }

          // --- Email Actions ---
          case 'approve_email':
          case 'send_email': {
            const draftId = params.email_draft_id as string;
            await sendDraft(draftId);
            break;
          }

          case 'edit_email': {
            const draftId = params.email_draft_id as string;
            if (onSendMessage) {
              onSendMessage(`I'd like to edit email draft ${draftId}`);
            }
            break;
          }

          case 'dismiss_email': {
            const draftId = params.email_draft_id as string;
            await dismissDraft(draftId);
            break;
          }

          case 'save_to_client': {
            const draftId = params.email_draft_id as string;
            console.log('[C1MessageRenderer] save_to_client for draft:', draftId);
            break;
          }

          // --- Signal Actions ---
          case 'investigate_signal': {
            const signalId = params.signal_id as string;
            await markSignalRead(signalId);
            navigate(`/intelligence/signals?highlight=${signalId}`);
            break;
          }

          case 'dismiss_signal': {
            const signalId = params.signal_id as string;
            await markSignalRead(signalId);
            break;
          }

          // --- Navigation Actions ---
          case 'view_lead_detail': {
            const leadId = params.lead_id as string;
            navigate(`/pipeline/leads/${leadId}`);
            break;
          }

          case 'view_battle_card': {
            const competitorId = params.competitor_id as string;
            navigate(`/intelligence/battle-cards/${competitorId}`);
            break;
          }

          case 'view_goal_detail': {
            const goalId = params.goal_id as string;
            navigate(`/goals/${goalId}`);
            break;
          }

          // --- Task Actions ---
          case 'execute_task': {
            const taskId = params.task_id as string;
            console.log('[C1MessageRenderer] execute_task:', taskId);
            wsManager.send('task.execute', { task_id: taskId });
            break;
          }

          // --- C1 Built-in Actions ---
          case 'open_url': {
            const url = params.url as string;
            window.open(url, '_blank', 'noopener,noreferrer');
            break;
          }

          case 'continue_conversation':
          default: {
            const message =
              (params.llmFriendlyMessage as string) ||
              (params.humanFriendlyMessage as string) ||
              event.llmFriendlyMessage ||
              event.humanFriendlyMessage ||
              '';
            if (message && onSendMessage) {
              onSendMessage(message);
            }
            break;
          }
        }
      } catch (error) {
        console.error('[C1MessageRenderer] Action failed:', event.type, error);
      }
    },
    [navigate, onSendMessage]
  );

  // Loading state while streaming
  if (isStreaming && !c1Response) {
    return (
      <div className={`flex items-center gap-2 text-secondary ${className}`}>
        <Loader2 className="w-4 h-4 animate-spin" />
        <span className="text-sm">Generating response...</span>
      </div>
    );
  }

  // Empty state
  if (!c1Response || c1Response.trim() === '') {
    return null;
  }

  return (
    <div className={`c1-message-renderer ${className}`}>
      <C1Component
        c1Response={c1Response}
        isStreaming={isStreaming}
        onAction={handleAction}
        onError={handleC1Error}
        customComponents={customComponents}
      />
    </div>
  );
}
