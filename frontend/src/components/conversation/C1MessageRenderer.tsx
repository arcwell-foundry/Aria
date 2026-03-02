/**
 * C1MessageRenderer - Renders C1 generative UI content in chat messages
 *
 * This component wraps the Thesys C1Component and provides:
 * - Custom ARIA-specific React components
 * - Action handling integration with ARIA's action system
 * - Loading and error states
 */

import { C1Component } from '@thesysai/genui-sdk';
import { Loader2 } from 'lucide-react';
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
  /** Handler for user actions from C1 components */
  onAction?: (humanMessage: string, llmMessage: string) => void;
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
  onAction,
  className = '',
}: C1MessageRendererProps) {
  // Handle actions from C1 components
  const handleAction = (event: C1ActionEvent) => {
    // Extract messages from the action event params (new format) or directly (legacy format)
    const humanMessage = event.params?.humanFriendlyMessage as string | undefined
      || event.humanFriendlyMessage
      || '';
    const llmMessage = event.params?.llmFriendlyMessage as string | undefined
      || event.llmFriendlyMessage
      || '';

    if (onAction) {
      onAction(humanMessage, llmMessage);
    }
    // Log for debugging
    console.log('[C1Action]', { type: event.type, humanMessage, llmMessage, params: event.params });
  };

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
  if (!c1Response) {
    return null;
  }

  return (
    <div className={`c1-message-renderer ${className}`}>
      <C1Component
        c1Response={c1Response}
        isStreaming={isStreaming}
        onAction={handleAction}
        customComponents={customComponents}
      />
    </div>
  );
}
