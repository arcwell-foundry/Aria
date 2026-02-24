import { useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Video } from 'lucide-react';
import { ConversationThread } from '@/components/conversation/ConversationThread';
import { InputBar } from '@/components/conversation/InputBar';
import { SuggestionChips } from '@/components/conversation/SuggestionChips';
import { useConversationStore } from '@/stores/conversationStore';
import { wsManager } from '@/core/WebSocketManager';
import { modalityController } from '@/core/ModalityController';
import { WS_EVENTS } from '@/types/chat';
import type { AriaMessagePayload, AriaThinkingPayload, StreamErrorPayload, RichContent, UICommand } from '@/types/chat';
import { useUICommands } from '@/hooks/useUICommands';
import { useEmotionDetection } from '@/hooks/useEmotionDetection';
import { useBriefingStatus } from '@/hooks/useBriefingStatus';
import { EmotionIndicator } from '@/components/shell/EmotionIndicator';
import { listConversations, getConversation } from '@/api/chat';
import { useTodayBriefing, useGenerateBriefing } from '@/hooks/useBriefing';
import { VideoBriefingCard } from '@/components/briefing';

// Module-level flag to prevent re-injecting briefing across remounts within the same session.
// Reset when the page fully reloads (new session), which is the intended behavior.
let briefingInjectedForSession = false;

export function ARIAWorkspace() {
  const navigate = useNavigate();
  const addMessage = useConversationStore((s) => s.addMessage);
  const appendToMessage = useConversationStore((s) => s.appendToMessage);
  const updateMessageMetadata = useConversationStore((s) => s.updateMessageMetadata);
  const setStreaming = useConversationStore((s) => s.setStreaming);
  const setCurrentSuggestions = useConversationStore((s) => s.setCurrentSuggestions);
  const activeConversationId = useConversationStore((s) => s.activeConversationId);
  const setActiveConversation = useConversationStore((s) => s.setActiveConversation);

  useUICommands();
  useEmotionDetection();

  const streamingIdRef = useRef<string | null>(null);
  const conversationLoadedRef = useRef(false);
  const briefingInjectedRef = useRef(false);
  const briefingGenerateCalledRef = useRef(false);
  const { data: briefing, isLoading: briefingLoading } = useTodayBriefing();
  const generateBriefing = useGenerateBriefing();

  // Video briefing status
  const {
    ready: briefingReady,
    viewed: briefingViewed,
    briefingId,
    duration,
    topics,
    dismissed: briefingDismissed,
    dismiss: dismissBriefing,
    fetchTextBriefing,
    summaryData,
    clearSummaryData,
  } = useBriefingStatus();

  // Load most recent conversation on mount (hydrates first conversation after onboarding)
  // IMPORTANT: Load BEFORE briefing injection to avoid race condition
  useEffect(() => {
    if (conversationLoadedRef.current) return;
    // Don't skip if messages exist - briefing may have loaded while we fetch
    conversationLoadedRef.current = true;

    listConversations()
      .then((conversations) => {
        console.log('[ARIAWorkspace] Loaded conversations:', conversations.length);
        if (!conversations.length) return;
        // Load the most recent conversation
        const latest = conversations[0];
        console.log('[ARIAWorkspace] Loading latest conversation:', latest.id);
        return getConversation(latest.id).then((chatMessages) => {
          console.log('[ARIAWorkspace] Loaded messages:', chatMessages.length);
          if (!chatMessages.length) return;

          const store = useConversationStore.getState();

          // Set active conversation
          store.setActiveConversation(latest.id);

          // Check if we already have these messages (avoid duplicates)
          const existingIds = new Set(store.messages.map(m => m.id));
          const messagesToAdd = chatMessages.filter(msg => !existingIds.has(msg.id));

          // Prepend conversation messages BEFORE any briefing
          // Use setMessages to replace the entire array with proper ordering
          const historicMessages = messagesToAdd.map(msg => {
            // Reconstruct rich_content from persisted metadata
            const richContent = msg.metadata && (msg.metadata as Record<string, unknown>).type
              ? [{ type: (msg.metadata as Record<string, unknown>).type as string, data: ((msg.metadata as Record<string, unknown>).data ?? msg.metadata) as Record<string, unknown> }]
              : [];

            return {
              id: msg.id,
              role: msg.role === 'assistant' ? 'aria' as const : 'user' as const,
              content: msg.content,
              rich_content: richContent,
              ui_commands: [] as const,
              suggestions: [] as const,
              timestamp: msg.created_at,
            };
          });

          // Prepend historic messages, keep existing messages (like briefing) at the end
          store.setMessages([...historicMessages, ...store.messages]);
          console.log('[ARIAWorkspace] Conversation restored:', historicMessages.length, 'messages');
        });
      })
      .catch((error) => {
        console.warn('[ARIAWorkspace] Failed to load conversation history:', error);
      });
  }, []);

  // Inject daily briefing as ARIA's first message when available
  useEffect(() => {
    if (briefingInjectedRef.current || briefingInjectedForSession) return;
    if (briefingLoading) return;

    // If no briefing exists yet, generate one (only once per session)
    if (!briefing && !briefingGenerateCalledRef.current && !generateBriefing.isPending) {
      briefingGenerateCalledRef.current = true;
      generateBriefing.mutate(undefined);
      return;
    }

    if (!briefing) return;

    // Check if a briefing message already exists in the store (dedup guard)
    const store = useConversationStore.getState();
    const hasBriefing = store.messages.some(
      (msg) => msg.role === 'aria' && msg.rich_content?.some((rc) => rc.type === 'briefing'),
    );
    if (hasBriefing) {
      briefingInjectedRef.current = true;
      briefingInjectedForSession = true;
      return;
    }

    briefingInjectedRef.current = true;
    briefingInjectedForSession = true;

    // Time-appropriate greeting
    const hour = new Date().getHours();
    const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';

    store.addMessage({
      role: 'aria',
      content: `${greeting}. Here's your intelligence briefing for today.`,
      rich_content: [
        {
          type: 'briefing',
          data: briefing as unknown as Record<string, unknown>,
        },
      ],
      ui_commands: [],
      suggestions: ['Show me today\'s meetings', 'Any urgent signals?', 'Check pipeline health'],
    });

    store.setCurrentSuggestions(['Show me today\'s meetings', 'Any urgent signals?', 'Check pipeline health']);
  }, [briefing, briefingLoading, generateBriefing]);

  // Wire up event listeners
  useEffect(() => {
    const handleAriaMessage = (payload: unknown) => {
      const data = (payload ?? {}) as Partial<AriaMessagePayload>;
      setStreaming(false);

      if (streamingIdRef.current) {
        updateMessageMetadata(streamingIdRef.current, {
          rich_content: data.rich_content ?? [],
          ui_commands: data.ui_commands ?? [],
          suggestions: data.suggestions ?? [],
        });
        streamingIdRef.current = null;
        return;
      }

      addMessage({
        role: 'aria',
        content: data.message ?? '',
        rich_content: data.rich_content ?? [],
        ui_commands: data.ui_commands ?? [],
        suggestions: data.suggestions ?? [],
      });

      if (data.suggestions?.length) {
        setCurrentSuggestions(data.suggestions);
      }

      if (data.conversation_id && !activeConversationId) {
        setActiveConversation(data.conversation_id);
      }
    };

    const handleThinking = (payload: unknown) => {
      const data = (payload ?? {}) as Partial<AriaThinkingPayload>;
      if (data.is_thinking) {
        setStreaming(true);
      }
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

    const handleStreamError = (payload: unknown) => {
      const data = (payload ?? {}) as Partial<StreamErrorPayload>;
      setStreaming(false);
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

  const handleStartTyping = useCallback(() => {
    const textarea = document.querySelector('[data-aria-id="message-input"]') as HTMLTextAreaElement | null;
    textarea?.focus();
  }, []);

  // Video briefing handlers
  const handlePlayBriefing = useCallback(() => {
    navigate('/briefing');
  }, [navigate]);

  const handleDismissBriefing = useCallback(() => {
    dismissBriefing();
    // Add a message to conversation indicating briefing was dismissed
    addMessage({
      role: 'system',
      content: 'Briefing saved for later. You can access it anytime from the Briefing section.',
      rich_content: [],
      ui_commands: [],
      suggestions: ['Show briefing now', 'Open Briefing'],
    });
  }, [dismissBriefing, addMessage]);

  const handleReadInstead = useCallback(async () => {
    try {
      const textBriefing = await fetchTextBriefing();
      dismissBriefing();
      addMessage({
        role: 'aria',
        content: textBriefing,
        rich_content: [],
        ui_commands: [],
        suggestions: ['Show me today\'s meetings', 'Any urgent signals?', 'Check pipeline health'],
      });
    } catch {
      addMessage({
        role: 'system',
        content: 'Unable to load text briefing. Please try again.',
        rich_content: [],
        ui_commands: [],
        suggestions: ['Try again'],
      });
    }
  }, [fetchTextBriefing, dismissBriefing, addMessage]);

  // Show summary card after briefing ends
  useEffect(() => {
    if (summaryData) {
      addMessage({
        role: 'aria',
        content: 'Your briefing is complete. Here\'s a summary:',
        rich_content: [
          {
            type: 'briefing_summary',
            data: {
              key_points: summaryData.key_points,
              action_items: summaryData.action_items,
              completed_at: summaryData.completed_at,
            },
          },
        ],
        ui_commands: [],
        suggestions: ['Review action items', 'Schedule follow-ups'],
      });
      clearSummaryData();
    }
  }, [summaryData, addMessage, clearSummaryData]);

  // Determine if video briefing card should be shown
  const showVideoBriefingCard = briefingReady && !briefingViewed && !briefingDismissed && briefingId;

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

      {/* Video Briefing Card - shown when briefing is ready and not yet viewed */}
      {showVideoBriefingCard && (
        <div className="px-6 pb-4">
          <VideoBriefingCard
            briefingId={briefingId!}
            duration={duration}
            topics={topics}
            onPlay={handlePlayBriefing}
            onDismiss={handleDismissBriefing}
            onReadInstead={handleReadInstead}
          />
        </div>
      )}

      <ConversationThread onStartTyping={handleStartTyping} />
      <SuggestionChips onSelect={handleSend} />
      <InputBar onSend={handleSend} />
    </div>
  );
}
