import { useEffect, useCallback, useRef } from 'react';
import { useConversationStore } from '@/stores/conversationStore';
import { useModalityStore } from '@/stores/modalityStore';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';
import type { AriaMessagePayload, AriaThinkingPayload, RichContent, UICommand } from '@/types/chat';
import { useSession } from '@/contexts/SessionContext';
import { useAuth } from '@/hooks/useAuth';
import { useUICommands } from '@/hooks/useUICommands';
import { AvatarContainer } from './AvatarContainer';
import { TranscriptPanel } from './TranscriptPanel';
import { DialogueHeader } from './DialogueHeader';
import { BriefingControls } from './BriefingControls';

interface DialogueModeProps {
  sessionType?: 'chat' | 'briefing' | 'debrief';
}

export function DialogueMode({ sessionType = 'chat' }: DialogueModeProps) {
  const addMessage = useConversationStore((s) => s.addMessage);
  const appendToMessage = useConversationStore((s) => s.appendToMessage);
  const updateMessageMetadata = useConversationStore((s) => s.updateMessageMetadata);
  const setStreaming = useConversationStore((s) => s.setStreaming);
  const setCurrentSuggestions = useConversationStore((s) => s.setCurrentSuggestions);
  const activeConversationId = useConversationStore((s) => s.activeConversationId);
  const setActiveConversation = useConversationStore((s) => s.setActiveConversation);
  const setIsSpeaking = useModalityStore((s) => s.setIsSpeaking);
  const tavusSession = useModalityStore((s) => s.tavusSession);

  const { session } = useSession();
  const { user } = useAuth();
  useUICommands();

  const streamingIdRef = useRef<string | null>(null);

  // Connect WebSocket on mount
  useEffect(() => {
    if (!user?.id || !session?.id) return;
    wsManager.connect(user.id, session.id);
    return () => {
      wsManager.disconnect();
    };
  }, [user?.id, session?.id]);

  // Wire up event listeners (same pattern as ARIAWorkspace + speaking events)
  useEffect(() => {
    const handleAriaMessage = (payload: unknown) => {
      const data = payload as AriaMessagePayload;
      setStreaming(false);
      setIsSpeaking(false);

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
      if (data.is_thinking) setStreaming(true);
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

    const handleSpeaking = (payload: unknown) => {
      const data = payload as { is_speaking: boolean };
      setIsSpeaking(data.is_speaking);
    };

    wsManager.on(WS_EVENTS.ARIA_MESSAGE, handleAriaMessage);
    wsManager.on(WS_EVENTS.ARIA_THINKING, handleThinking);
    wsManager.on(WS_EVENTS.ARIA_SPEAKING, handleSpeaking);
    wsManager.on('aria.token', handleToken);
    wsManager.on('aria.metadata', handleMetadata);

    return () => {
      wsManager.off(WS_EVENTS.ARIA_MESSAGE, handleAriaMessage);
      wsManager.off(WS_EVENTS.ARIA_THINKING, handleThinking);
      wsManager.off(WS_EVENTS.ARIA_SPEAKING, handleSpeaking);
      wsManager.off('aria.token', handleToken);
      wsManager.off('aria.metadata', handleMetadata);
    };
  }, [addMessage, appendToMessage, updateMessageMetadata, setStreaming, setCurrentSuggestions, activeConversationId, setActiveConversation, setIsSpeaking]);

  const handleSend = useCallback(
    (message: string) => {
      addMessage({
        role: 'user',
        content: message,
        rich_content: [],
        ui_commands: [],
        suggestions: [],
      });
      wsManager.send(WS_EVENTS.USER_MESSAGE, {
        message,
        conversation_id: activeConversationId,
      });
    },
    [addMessage, activeConversationId],
  );

  const isBriefing = sessionType === 'briefing' || tavusSession.sessionType === 'briefing';

  return (
    <div
      className="flex-1 flex flex-col h-full"
      style={{ backgroundColor: '#0A0A0B' }}
      data-aria-id="dialogue-mode"
    >
      <DialogueHeader />

      <div className="flex-1 flex overflow-hidden">
        {/* Left: Avatar */}
        <div className="flex-1 flex flex-col items-center justify-center relative">
          <AvatarContainer />
          {isBriefing && (
            <div className="absolute bottom-8 z-10">
              <BriefingControls
                progress={0}
                isPlaying={true}
                onPlayPause={() => {}}
                onRewind={() => {}}
                onForward={() => {}}
              />
            </div>
          )}
        </div>

        {/* Divider */}
        <div className="w-px bg-[#1A1A2E]" />

        {/* Right: Transcript */}
        <TranscriptPanel onSend={handleSend} />
      </div>
    </div>
  );
}
