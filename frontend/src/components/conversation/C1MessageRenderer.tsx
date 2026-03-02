// frontend/src/components/conversation/C1MessageRenderer.tsx

import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { C1Component } from '@thesysai/genui-sdk';
import { approveGoalPlan, startGoal } from '@/api/goals';
import { dismissDraft, sendDraft } from '@/api/drafts';
import { markSignalRead } from '@/api/signals';
import { wsManager } from '@/core/WebSocketManager';

// C1Action type based on @thesysai/genui-sdk internal types
// The SDK's C1Action = C1ActionEvent & LegacyAction
interface C1ActionEvent {
  type?: string;
  params?: Record<string, unknown>;
}

interface LegacyAction {
  llmFriendlyMessage?: string;
  humanFriendlyMessage?: string;
}

type C1Action = C1ActionEvent & LegacyAction;

interface C1MessageRendererProps {
  c1Response: string;
  isStreaming: boolean;
  onSendMessage: (message: string) => void;
}

/**
 * C1MessageRenderer - Wraps C1Component with ARIA-specific action routing.
 *
 * Handles custom actions from C1-generated UI and maps them to
 * existing ARIA backend endpoints and WebSocket events.
 */
export function C1MessageRenderer({
  c1Response,
  isStreaming,
  onSendMessage,
}: C1MessageRendererProps) {
  const navigate = useNavigate();

  const handleAction = useCallback(
    async (event: C1Action) => {
      // C1Action has optional type and params - handle missing type
      if (!event.type) {
        // Default to continue_conversation behavior
        const params = event.params ?? {};
        const message = (params.llmFriendlyMessage as string) || (params.humanFriendlyMessage as string) || '';
        if (message) {
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
            // Navigate to goal detail to show execution starting
            navigate(`/goals/${goalId}`);
            break;
          }

          case 'modify_goal':
          case 'modify_plan': {
            const goalId = params.goal_id as string;
            // Navigate to goal edit or send modification message
            onSendMessage(`I'd like to modify the plan for goal ${goalId}`);
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
            // Navigate to email editor or open modal
            onSendMessage(`I'd like to edit email draft ${draftId}`);
            break;
          }

          case 'dismiss_email': {
            const draftId = params.email_draft_id as string;
            await dismissDraft(draftId);
            break;
          }

          case 'save_to_client': {
            const draftId = params.email_draft_id as string;
            // TODO: Implement save-to-client endpoint call
            console.log('[C1MessageRenderer] save_to_client for draft:', draftId);
            break;
          }

          // --- Signal Actions ---
          case 'investigate_signal': {
            const signalId = params.signal_id as string;
            await markSignalRead(signalId);
            // Navigate to signals page filtered by this signal
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
            // TODO: Implement task execution endpoint
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
            // Extract LLM-friendly message for follow-up
            const message = (params.llmFriendlyMessage as string) || (params.humanFriendlyMessage as string) || '';
            if (message) {
              onSendMessage(message);
            }
            break;
          }
        }
      } catch (error) {
        console.error('[C1MessageRenderer] Action failed:', event.type, error);
        // Could emit an error event or show a toast notification
      }
    },
    [navigate, onSendMessage]
  );

  // Fallback: if c1Response is empty, return null (parent will use markdown)
  if (!c1Response || c1Response.trim() === '') {
    return null;
  }

  return (
    <div className="c1-component-wrapper">
      <C1Component
        c1Response={c1Response}
        isStreaming={isStreaming}
        onAction={handleAction}
      />
    </div>
  );
}
