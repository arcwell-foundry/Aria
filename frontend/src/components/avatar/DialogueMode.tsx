import { useEffect, useCallback, useRef, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
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
import { AudioCallControls } from './AudioCallControls';
import { VideoToastStack } from '@/components/video/VideoToastStack';
import type { ToastItem } from '@/components/video/VideoContentToast';

interface DialogueModeProps {
  sessionType?: 'chat' | 'briefing' | 'debrief';
}

export function DialogueMode({ sessionType = 'chat' }: DialogueModeProps) {
  const [searchParams] = useSearchParams();
  const addMessage = useConversationStore((s) => s.addMessage);
  const appendToMessage = useConversationStore((s) => s.appendToMessage);
  const updateMessageMetadata = useConversationStore((s) => s.updateMessageMetadata);
  const setStreaming = useConversationStore((s) => s.setStreaming);
  const setCurrentSuggestions = useConversationStore((s) => s.setCurrentSuggestions);
  const activeConversationId = useConversationStore((s) => s.activeConversationId);
  const setActiveConversation = useConversationStore((s) => s.setActiveConversation);
  const setIsSpeaking = useModalityStore((s) => s.setIsSpeaking);
  const tavusSession = useModalityStore((s) => s.tavusSession);
  const isAudioOnly = tavusSession.isAudioOnly;

  const { session } = useSession();
  const { user } = useAuth();
  useUICommands();
  useEmotionDetection();

  const streamingIdRef = useRef<string | null>(null);

  // Check if this is a replay
  const isReplay = searchParams.get('replay') === 'true';

  const isBriefing = sessionType === 'briefing' || tavusSession.sessionType === 'briefing';

  // Briefing playback state
  const [isBriefingPlaying, setIsBriefingPlaying] = useState(true);
  const [briefingProgress, setBriefingProgress] = useState(0);
  const briefingProgressRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const [toasts, setToasts] = useState<ToastItem[]>([]);

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
        // If replay, use the replay endpoint; otherwise, deliver new briefing
        if (isReplay) {
          await apiClient.post('/briefings/replay');
        } else {
          await apiClient.post('/briefings/deliver');
        }
      } catch (err) {
        // Briefing delivery failure handled by WebSocket fallback
        console.warn('Briefing delivery request failed:', err);
      }
    };

    deliverBriefing();
  }, [sessionType, isReplay]);

  // Track briefing progress based on aria.speaking events
  useEffect(() => {
    if (!isBriefing) return;

    const handleBriefingSpeaking = (payload: unknown) => {
      const data = (payload ?? {}) as Partial<{ is_speaking: boolean }>;
      setIsBriefingPlaying(data.is_speaking ?? false);

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

  const toastTitleForContent = useCallback((type: string, data: Record<string, unknown>): string => {
    switch (type) {
      case 'lead_card':
        return `Lead: ${(data.company_name as string) || 'Company'}`;
      case 'battle_card':
        return `Battle Card: ${(data.competitor_name as string) || 'Competitor'}`;
      case 'pipeline_chart':
        return `Pipeline: ${(data.total as number) || 0} leads`;
      case 'research_results':
        return `Research: ${(data.query as string) || 'Results'}`;
      case 'email_draft':
        return `Draft: ${(data.subject as string) || 'Email'}`;
      default:
        return type.replace(/_/g, ' ');
    }
  }, []);

  // Wire up event listeners (same pattern as ARIAWorkspace + speaking events)
  useEffect(() => {
    const handleAriaMessage = (payload: unknown) => {
      const data = (payload ?? {}) as Partial<AriaMessagePayload>;
      setStreaming(false);
      setIsSpeaking(false);

      if (streamingIdRef.current) {
        updateMessageMetadata(streamingIdRef.current, {
          rich_content: data.rich_content ?? [],
          ui_commands: data.ui_commands ?? [],
          suggestions: data.suggestions ?? [],
        });
        streamingIdRef.current = null;
      } else {
        addMessage({
          role: 'aria',
          content: data.message ?? '',
          rich_content: data.rich_content ?? [],
          ui_commands: data.ui_commands ?? [],
          suggestions: data.suggestions ?? [],
        });
      }

      // Create toast notifications for video content overlay
      const richItems = data.rich_content ?? [];
      const VIDEO_CONTENT_TYPES = ['lead_card', 'battle_card', 'pipeline_chart', 'research_results', 'email_draft'];
      for (const item of richItems) {
        if (VIDEO_CONTENT_TYPES.includes(item.type)) {
          const toastId = `toast-${item.type}-${Date.now()}`;
          setToasts((prev) => {
            const next = [...prev, { id: toastId, contentType: item.type, title: toastTitleForContent(item.type, item.data) }];
            return next.length > 3 ? next.slice(-3) : next;
          });
        }
      }

      if (data.suggestions?.length) {
        setCurrentSuggestions(data.suggestions);
      }
      if (data.conversation_id && !activeConversationId) {
        setActiveConversation(data.conversation_id);
      }
    };

    const handleThinking = (payload: unknown) => {
      const data = (payload ?? {}) as Partial<AriaThinkingPayload>;
      if (data.is_thinking) setStreaming(true);
    };

    const handleToken = (payload: unknown) => {
      const data = (payload ?? {}) as Partial<{ content: string; full_content: string }>;
      const tokenContent = data.content ?? '';
      if (!streamingIdRef.current) {
        const store = useConversationStore.getState();
        store.addMessage({
          role: 'aria',
          content: tokenContent,
          rich_content: [],
          ui_commands: [],
          suggestions: [],
          isStreaming: true,
        });
        const msgs = useConversationStore.getState().messages;
        streamingIdRef.current = msgs[msgs.length - 1]?.id ?? null;
        setStreaming(true, streamingIdRef.current);
      } else {
        appendToMessage(streamingIdRef.current, tokenContent);
      }
    };

    const handleMetadata = (payload: unknown) => {
      const data = (payload ?? {}) as Partial<{
        message_id: string;
        rich_content: RichContent[];
        ui_commands: UICommand[];
        suggestions: string[];
      }>;
      if (streamingIdRef.current) {
        updateMessageMetadata(streamingIdRef.current, {
          rich_content: data.rich_content ?? [],
          ui_commands: data.ui_commands ?? [],
          suggestions: data.suggestions ?? [],
        });
      }
    };

    const handleSpeaking = (payload: unknown) => {
      const data = (payload ?? {}) as Partial<{ is_speaking: boolean }>;
      setIsSpeaking(data.is_speaking ?? false);
    };

    const handleStreamError = (payload: unknown) => {
      const data = (payload ?? {}) as Partial<StreamErrorPayload>;
      setStreaming(false);
      setIsSpeaking(false);
      streamingIdRef.current = null;

      addMessage({
        role: 'system',
        content: data.error ?? 'An unexpected error occurred.',
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
  }, [addMessage, appendToMessage, updateMessageMetadata, setStreaming, setCurrentSuggestions, activeConversationId, setActiveConversation, setIsSpeaking, toastTitleForContent]);

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

  const handleToastDismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const handleToastClick = useCallback((id: string) => {
    const transcriptEl = document.querySelector('[data-aria-id="transcript-panel"]');
    if (transcriptEl) {
      transcriptEl.scrollTop = transcriptEl.scrollHeight;
    }
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

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

      {isAudioOnly ? (
        /* Audio-only layout: single column */
        <div className="flex-1 flex flex-col overflow-hidden">
          {/* Compact avatar + waveform header */}
          <div className="flex flex-col items-center py-6 shrink-0">
            <AvatarContainer audioOnly />
          </div>

          {/* Full-width transcript */}
          <div className="flex-1 overflow-hidden">
            <TranscriptPanel onSend={handleSend} />
          </div>

          {/* Call controls */}
          <AudioCallControls />

          {/* Toast stack for rich content */}
          <VideoToastStack
            toasts={toasts}
            onDismiss={handleToastDismiss}
            onToastClick={handleToastClick}
          />
        </div>
      ) : (
        /* Video layout: split screen */
        <div className="flex-1 flex overflow-hidden">
          {/* Left: Avatar */}
          <div className="flex-1 flex flex-col items-center justify-center relative">
            <AvatarContainer />
            <VideoToastStack
              toasts={toasts}
              onDismiss={handleToastDismiss}
              onToastClick={handleToastClick}
            />
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
      )}
    </div>
  );
}
