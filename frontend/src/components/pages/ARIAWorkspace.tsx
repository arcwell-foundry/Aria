import { useEffect, useCallback, useRef } from 'react';
import { Video } from 'lucide-react';
import { ConversationThread } from '@/components/conversation/ConversationThread';
import { InputBar } from '@/components/conversation/InputBar';
import { SuggestionChips } from '@/components/conversation/SuggestionChips';
import { useConversationStore } from '@/stores/conversationStore';
import { wsManager } from '@/core/WebSocketManager';
import { modalityController } from '@/core/ModalityController';
import { WS_EVENTS } from '@/types/chat';
import type { AriaMessagePayload, AriaThinkingPayload, StreamErrorPayload, RichContent, UICommand } from '@/types/chat';
import { useSession } from '@/contexts/SessionContext';
import { useAuth } from '@/hooks/useAuth';
import { useUICommands } from '@/hooks/useUICommands';
import { useEmotionDetection } from '@/hooks/useEmotionDetection';
import { EmotionIndicator } from '@/components/shell/EmotionIndicator';
import { listConversations, getConversation } from '@/api/chat';

export function ARIAWorkspace() {
  const addMessage = useConversationStore((s) => s.addMessage);
  const appendToMessage = useConversationStore((s) => s.appendToMessage);
  const updateMessageMetadata = useConversationStore((s) => s.updateMessageMetadata);
  const setStreaming = useConversationStore((s) => s.setStreaming);
  const setCurrentSuggestions = useConversationStore((s) => s.setCurrentSuggestions);
  const activeConversationId = useConversationStore((s) => s.activeConversationId);
  const setActiveConversation = useConversationStore((s) => s.setActiveConversation);

  const { session } = useSession();
  const { user } = useAuth();
  useUICommands();
  useEmotionDetection();

  const streamingIdRef = useRef<string | null>(null);
  const conversationLoadedRef = useRef(false);

  // Connect WebSocket on mount
  useEffect(() => {
    if (!user?.id || !session?.id) return;

    wsManager.connect(user.id, session.id);

    return () => {
      wsManager.disconnect();
    };
  }, [user?.id, session?.id]);

  // Load most recent conversation on mount (hydrates first conversation after onboarding)
  useEffect(() => {
    if (conversationLoadedRef.current) return;
    const messages = useConversationStore.getState().messages;
    if (messages.length > 0) return;

    conversationLoadedRef.current = true;

    listConversations()
      .then((conversations) => {
        if (!conversations.length) return;
        // Load the most recent conversation
        const latest = conversations[0];
        return getConversation(latest.id).then((chatMessages) => {
          if (!chatMessages.length) return;
          const store = useConversationStore.getState();
          // Only load if store is still empty (avoid race with WebSocket)
          if (store.messages.length > 0) return;
          store.setActiveConversation(latest.id);
          for (const msg of chatMessages) {
            store.addMessage({
              role: msg.role === 'assistant' ? 'aria' : 'user',
              content: msg.content,
              rich_content: [],
              ui_commands: [],
              suggestions: [],
            });
          }
        });
      })
      .catch(() => {
        // Silently fail — workspace will just be empty
      });
  }, []);

  // Wire up event listeners
  useEffect(() => {
    const handleAriaMessage = (payload: unknown) => {
      const data = payload as AriaMessagePayload;
      setStreaming(false);

      if (streamingIdRef.current) {
        updateMessageMetadata(streamingIdRef.current, {
          rich_content: data.rich_content || [],
          ui_commands: data.ui_commands || [],
          suggestions: data.suggestions || [],
        });
        streamingIdRef.current = null;
        return;
      }

      addMessage({
        role: 'aria',
        content: data.message,
        rich_content: data.rich_content || [],
        ui_commands: data.ui_commands || [],
        suggestions: data.suggestions || [],
      });

      if (data.suggestions?.length) {
        setCurrentSuggestions(data.suggestions);
      }

      if (data.conversation_id && !activeConversationId) {
        setActiveConversation(data.conversation_id);
      }
    };

    const handleThinking = (payload: unknown) => {
      const data = payload as AriaThinkingPayload;
      if (data.is_thinking) {
        setStreaming(true);
      }
    };

    const handleToken = (payload: unknown) => {
      const data = payload as { content: string; full_content: string };

      if (!streamingIdRef.current) {
        const store = useConversationStore.getState();
        store.addMessage({
          role: 'aria',
          content: data.content,
          rich_content: [],
          ui_commands: [],
          suggestions: [],
          isStreaming: true,
        });
        const msgs = useConversationStore.getState().messages;
        streamingIdRef.current = msgs[msgs.length - 1]?.id ?? null;
        setStreaming(true, streamingIdRef.current);
      } else {
        appendToMessage(streamingIdRef.current, data.content);
      }
    };

    const handleMetadata = (payload: unknown) => {
      const data = payload as {
        message_id: string;
        rich_content: RichContent[];
        ui_commands: UICommand[];
        suggestions: string[];
      };

      if (streamingIdRef.current) {
        updateMessageMetadata(streamingIdRef.current, {
          rich_content: data.rich_content,
          ui_commands: data.ui_commands,
          suggestions: data.suggestions,
        });
      }
    };

    const handleStreamError = (payload: unknown) => {
      const data = payload as StreamErrorPayload;
      setStreaming(false);
      streamingIdRef.current = null;

      addMessage({
        role: 'system',
        content: data.error,
        rich_content: [],
        ui_commands: [],
        suggestions: data.recoverable ? ['Try again'] : [],
      });
    };

    const handleStreamComplete = () => {
      // Positive signal that the LLM stream finished normally.
      // The final aria.message event handles setting streaming to false,
      // so this is a no-op unless the aria.message is delayed.
    };

    wsManager.on(WS_EVENTS.ARIA_MESSAGE, handleAriaMessage);
    wsManager.on(WS_EVENTS.ARIA_THINKING, handleThinking);
    wsManager.on('aria.token', handleToken);
    wsManager.on('aria.metadata', handleMetadata);
    wsManager.on(WS_EVENTS.ARIA_STREAM_ERROR, handleStreamError);
    wsManager.on(WS_EVENTS.ARIA_STREAM_COMPLETE, handleStreamComplete);

    return () => {
      wsManager.off(WS_EVENTS.ARIA_MESSAGE, handleAriaMessage);
      wsManager.off(WS_EVENTS.ARIA_THINKING, handleThinking);
      wsManager.off('aria.token', handleToken);
      wsManager.off('aria.metadata', handleMetadata);
      wsManager.off(WS_EVENTS.ARIA_STREAM_ERROR, handleStreamError);
      wsManager.off(WS_EVENTS.ARIA_STREAM_COMPLETE, handleStreamComplete);
    };
  }, [
    addMessage,
    appendToMessage,
    updateMessageMetadata,
    setStreaming,
    setCurrentSuggestions,
    activeConversationId,
    setActiveConversation,
  ]);

  const handleSend = useCallback(
    (message: string) => {
      // Ensure conversation_id exists before sending — prevents fragmentation
      let conversationId = activeConversationId;
      if (!conversationId) {
        conversationId = crypto.randomUUID();
        setActiveConversation(conversationId);
      }

      addMessage({
        role: 'user',
        content: message,
        rich_content: [],
        ui_commands: [],
        suggestions: [],
      });

      wsManager.send(WS_EVENTS.USER_MESSAGE, {
        message,
        conversation_id: conversationId,
      });
    },
    [addMessage, activeConversationId, setActiveConversation],
  );

  return (
    <div
      className="flex-1 flex flex-col h-full"
      style={{ backgroundColor: '#0A0A0B' }}
      data-aria-id="aria-workspace"
    >
      {/* Header with avatar toggle */}
      <div className="flex items-center justify-end gap-3 px-6 py-2">
        <EmotionIndicator />
        <button
          onClick={() => modalityController.switchTo('avatar')}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[#8B8FA3] hover:text-[#2E66FF] hover:bg-[#2E66FF]/10 transition-colors"
          aria-label="Switch to Dialogue Mode"
        >
          <Video size={14} />
          <span className="text-xs">Avatar</span>
        </button>
      </div>
      <ConversationThread />
      <SuggestionChips onSelect={handleSend} />
      <InputBar onSend={handleSend} />
    </div>
  );
}
