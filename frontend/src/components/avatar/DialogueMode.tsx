import { useEffect, useCallback, useRef, useState } from 'react';
import { useConversationStore } from '@/stores/conversationStore';
import { useModalityStore } from '@/stores/modalityStore';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';
import type { AriaMessagePayload, AriaThinkingPayload, StreamErrorPayload, RichContent, UICommand } from '@/types/chat';
import { useSession } from '@/contexts/SessionContext';
import { useAuth } from '@/hooks/useAuth';
import { useUICommands } from '@/hooks/useUICommands';
import { useEmotionDetection } from '@/hooks/useEmotionDetection';
import { apiClient } from '@/api/client';
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
  useEmotionDetection();

  const streamingIdRef = useRef<string | null>(null);

  const isBriefing = sessionType === 'briefing' || tavusSession.sessionType === 'briefing';

  // Briefing playback state
  const [isBriefingPlaying, setIsBriefingPlaying] = useState(true);
  const [briefingProgress, setBriefingProgress] = useState(0);
  const briefingProgressRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Connect WebSocket on mount
  useEffect(() => {
    if (!user?.id || !session?.id) return;
    wsManager.connect(user.id, session.id);
    return () => {
      wsManager.disconnect();
    };
  }, [user?.id, session?.id]);

  // Trigger briefing delivery when entering briefing mode
  useEffect(() => {
    if (sessionType !== 'briefing') return;

    const deliverBriefing = async () => {
      try {
        await apiClient.post('/briefings/deliver');
      } catch (err) {
        // Briefing delivery failure handled by WebSocket fallback
        console.warn('Briefing delivery request failed:', err);
      }
    };

    deliverBriefing();
  }, [sessionType]);

  // Track briefing progress based on aria.speaking events
  useEffect(() => {
    if (!isBriefing) return;

    const handleBriefingSpeaking = (payload: unknown) => {
      const data = payload as { is_speaking: boolean };
      setIsBriefingPlaying(data.is_speaking);

      if (data.is_speaking) {
        // Start gradual progress increment while speaking
        if (briefingProgressRef.current) clearInterval(briefingProgressRef.current);
        briefingProgressRef.current = setInterval(() => {
          setBriefingProgress((prev) => Math.min(prev + 1, 100));
        }, 1000);
      } else {
        // Stop progress increment when not speaking
        if (briefingProgressRef.current) {
          clearInterval(briefingProgressRef.current);
          briefingProgressRef.current = null;
        }
      }
    };

    wsManager.on(WS_EVENTS.ARIA_SPEAKING, handleBriefingSpeaking);

    return () => {
      wsManager.off(WS_EVENTS.ARIA_SPEAKING, handleBriefingSpeaking);
      if (briefingProgressRef.current) {
        clearInterval(briefingProgressRef.current);
        briefingProgressRef.current = null;
      }
    };
  }, [isBriefing]);

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

    const handleStreamError = (payload: unknown) => {
      const data = payload as StreamErrorPayload;
      setStreaming(false);
      setIsSpeaking(false);
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
    };

    wsManager.on(WS_EVENTS.ARIA_MESSAGE, handleAriaMessage);
    wsManager.on(WS_EVENTS.ARIA_THINKING, handleThinking);
    wsManager.on(WS_EVENTS.ARIA_SPEAKING, handleSpeaking);
    wsManager.on('aria.token', handleToken);
    wsManager.on('aria.metadata', handleMetadata);
    wsManager.on(WS_EVENTS.ARIA_STREAM_ERROR, handleStreamError);
    wsManager.on(WS_EVENTS.ARIA_STREAM_COMPLETE, handleStreamComplete);

    return () => {
      wsManager.off(WS_EVENTS.ARIA_MESSAGE, handleAriaMessage);
      wsManager.off(WS_EVENTS.ARIA_THINKING, handleThinking);
      wsManager.off(WS_EVENTS.ARIA_SPEAKING, handleSpeaking);
      wsManager.off('aria.token', handleToken);
      wsManager.off('aria.metadata', handleMetadata);
      wsManager.off(WS_EVENTS.ARIA_STREAM_ERROR, handleStreamError);
      wsManager.off(WS_EVENTS.ARIA_STREAM_COMPLETE, handleStreamComplete);
    };
  }, [addMessage, appendToMessage, updateMessageMetadata, setStreaming, setCurrentSuggestions, activeConversationId, setActiveConversation, setIsSpeaking]);

  // Briefing control handlers
  // Ensure conversation_id exists before any send — prevents fragmentation
  const ensureConversationId = useCallback(() => {
    if (activeConversationId) return activeConversationId;
    const id = crypto.randomUUID();
    setActiveConversation(id);
    return id;
  }, [activeConversationId, setActiveConversation]);

  const handlePlayPause = useCallback(() => {
    setIsBriefingPlaying((prev) => {
      const conversationId = ensureConversationId();
      if (prev) {
        // Pausing: stop progress and send interrupt to Tavus via WS
        if (briefingProgressRef.current) {
          clearInterval(briefingProgressRef.current);
          briefingProgressRef.current = null;
        }
        wsManager.send(WS_EVENTS.USER_MESSAGE, {
          message: '/briefing pause',
          conversation_id: conversationId,
        });
      } else {
        // Resuming: send resume to Tavus via WS
        wsManager.send(WS_EVENTS.USER_MESSAGE, {
          message: '/briefing resume',
          conversation_id: conversationId,
        });
      }
      return !prev;
    });
  }, [ensureConversationId]);

  const handleRewind = useCallback(() => {
    // Cannot truly seek in a live Tavus stream; ask ARIA to repeat last point
    wsManager.send(WS_EVENTS.USER_MESSAGE, {
      message: '/briefing repeat',
      conversation_id: ensureConversationId(),
    });
  }, [ensureConversationId]);

  const handleForward = useCallback(() => {
    // Cannot truly seek in a live Tavus stream; ask ARIA to skip to next point
    wsManager.send(WS_EVENTS.USER_MESSAGE, {
      message: '/briefing next',
      conversation_id: ensureConversationId(),
    });
  }, [ensureConversationId]);

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
        conversation_id: ensureConversationId(),
      });
    },
    [addMessage, ensureConversationId],
  );

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
                progress={briefingProgress}
                isPlaying={isBriefingPlaying}
                onPlayPause={handlePlayPause}
                onRewind={handleRewind}
                onForward={handleForward}
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
