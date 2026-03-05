import { useEffect, useCallback, useRef, useState } from 'react';
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
import { useAuth } from '@/hooks/useAuth';
import { EmotionIndicator } from '@/components/shell/EmotionIndicator';
import { listConversations, getConversation } from '@/api/chat';
import { useTodayBriefing } from '@/hooks/useBriefing';
import { streamBriefingC1 } from '@/api/briefings';
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
  const lastCompletedMessageIdRef = useRef<string | null>(null); // For C1 post-processing
  const streamingTimeoutRef = useRef<NodeJS.Timeout | null>(null);
  const conversationLoadedRef = useRef(false);
  const briefingInjectedRef = useRef(false);
  const briefingStreamAbortRef = useRef<AbortController | null>(null);
  const { data: briefingFallback } = useTodayBriefing();

  // Get user info for greeting personalization
  const { user } = useAuth();

  // Briefing card state - gate C1 stream behind user action
  const [briefingStreamRequested, setBriefingStreamRequested] = useState(false);
  const [briefingSkipped, setBriefingSkipped] = useState(() => {
    // Check sessionStorage on init for session persistence
    return sessionStorage.getItem('briefingSkipped') === 'true';
  });

  // Video briefing status
  const {
    ready: briefingReady,
    viewed: briefingViewed,
    briefingId,
    duration,
    topics,
    dismissed: briefingDismissed,
    dismiss: dismissBriefing,
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
        if (!conversations.length) return;
        // Load the most recent conversation
        const latest = conversations[0];
        return getConversation(latest.id).then((chatMessages) => {
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
              ui_commands: [] as UICommand[],
              suggestions: [] as string[],
              timestamp: msg.created_at,
            };
          });

          // Prepend historic messages, keep existing messages (like briefing) at the end
          store.setMessages([...historicMessages, ...store.messages]);
        });
      })
      .catch((error) => {
        console.warn('[ARIAWorkspace] Failed to load conversation history:', error);
      });
  }, []);

  // Inject daily briefing as ARIA's first message via streaming C1 pipeline
  // IMPORTANT: Only fires when user clicks "Read Summary" button (briefingStreamRequested = true)
  useEffect(() => {
    // Gate: Only fire if user explicitly requested the stream
    if (!briefingStreamRequested) return;
    if (briefingInjectedRef.current || briefingInjectedForSession) return;

    // Check if a briefing message already exists in the store (dedup guard)
    const store = useConversationStore.getState();
    const hasBriefing = store.messages.some(
      (msg) =>
        msg.role === 'aria' &&
        (msg.rich_content?.some((rc) => rc.type === 'briefing') || msg.render_mode === 'c1'),
    );
    if (hasBriefing) {
      briefingInjectedRef.current = true;
      briefingInjectedForSession = true;
      return;
    }

    briefingInjectedRef.current = true;
    briefingInjectedForSession = true;

    const abortController = new AbortController();
    briefingStreamAbortRef.current = abortController;

    let streamingMsgId: string | null = null;
    // Safety timeout: auto-clear streaming after 60s for briefing stream
    const briefingSafetyTimeout = setTimeout(() => {
      if (streamingMsgId) {
        console.warn('[ARIAWorkspace] Briefing stream safety timeout: force-clearing streaming state');
        const s = useConversationStore.getState();
        s.setStreaming(false);
      }
    }, 60000);

    (async () => {
      try {
        const response = await streamBriefingC1();
        if (abortController.signal.aborted) return;

        const reader = response.body?.getReader();
        if (!reader) throw new Error('No response body');

        const decoder = new TextDecoder();
        let buffer = '';

        // eslint-disable-next-line no-constant-condition
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          if (abortController.signal.aborted) {
            reader.cancel();
            return;
          }

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';

          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            const jsonStr = line.slice(6).trim();
            if (!jsonStr) continue;

            if (jsonStr === '[DONE]') {
              // Stream complete — finalize streaming state and clear safety timeout
              clearTimeout(briefingSafetyTimeout);
              if (streamingMsgId) {
                const s = useConversationStore.getState();
                s.setStreaming(false);
              }
              return;
            }

            try {
              const event = JSON.parse(jsonStr);

              if (event.type === 'token') {
                if (!streamingMsgId) {
                  // Create the initial streaming message
                  const s = useConversationStore.getState();
                  s.addMessage({
                    role: 'aria',
                    content: event.content || '',
                    rich_content: [],
                    ui_commands: [],
                    suggestions: [],
                    isStreaming: true,
                  });
                  const msgs = useConversationStore.getState().messages;
                  streamingMsgId = msgs[msgs.length - 1]?.id ?? null;
                  if (streamingMsgId) {
                    const s2 = useConversationStore.getState();
                    s2.setStreaming(true, streamingMsgId);
                  }
                } else {
                  appendToMessage(streamingMsgId, event.content || '');
                }
              } else if (event.type === 'complete') {
                if (streamingMsgId) {
                  updateMessageMetadata(streamingMsgId, {
                    rich_content: event.rich_content || [],
                    suggestions: event.suggestions || [],
                    render_mode: event.render_mode || 'markdown',
                    c1_response: event.c1_response || null,
                  });
                }
                if (event.suggestions?.length) {
                  setCurrentSuggestions(event.suggestions);
                }
              }
              // metadata events are ignored — we already have the message_id
            } catch {
              // Skip unparseable lines
            }
          }
        }
      } catch {
        // Stream failed — fall back to static briefing injection
        clearTimeout(briefingSafetyTimeout);
        if (abortController.signal.aborted) return;

        // CRITICAL: Reset streaming state on stream failure
        const s = useConversationStore.getState();
        s.setStreaming(false);

        if (briefingFallback) {
          const hour = new Date().getHours();
          const greeting = hour < 12 ? 'Good morning' : hour < 17 ? 'Good afternoon' : 'Good evening';

          s.addMessage({
            role: 'aria',
            content: `${greeting}. Here's your intelligence briefing for today.`,
            rich_content: [
              {
                type: 'briefing',
                data: briefingFallback as unknown as Record<string, unknown>,
              },
            ],
            ui_commands: [],
            suggestions: ['Show me today\'s meetings', 'Any urgent signals?', 'Check pipeline health'],
          });
          s.setCurrentSuggestions(['Show me today\'s meetings', 'Any urgent signals?', 'Check pipeline health']);
        }
      }
    })();

    return () => {
      clearTimeout(briefingSafetyTimeout);
      abortController.abort();
      // CRITICAL: Reset streaming state on cleanup (unmount or dependency change)
      const s = useConversationStore.getState();
      s.setStreaming(false);
    };
  }, [briefingStreamRequested, briefingFallback, appendToMessage, updateMessageMetadata, setCurrentSuggestions]);

  // Wire up event listeners
  useEffect(() => {
    const handleAriaMessage = (payload: unknown) => {
      const data = (payload ?? {}) as Partial<AriaMessagePayload>;
      console.log(
        '[CHAT_STREAM_DEBUG] aria.message received, setting isStreaming=false, streamingIdRef=',
        streamingIdRef.current,
      );
      setStreaming(false);

      if (streamingIdRef.current) {
        updateMessageMetadata(streamingIdRef.current, {
          rich_content: data.rich_content ?? [],
          ui_commands: data.ui_commands ?? [],
          suggestions: data.suggestions ?? [],
          render_mode: data.render_mode ?? 'markdown',
          c1_response: data.c1_response ?? null,
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
        render_mode: data.render_mode ?? 'markdown',
        c1_response: data.c1_response ?? null,
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
      console.log('[CHAT_STREAM_DEBUG] aria.thinking received, is_thinking=', data.is_thinking);
      if (data.is_thinking) {
        setStreaming(true);
        // Safety timeout: auto-clear streaming after 120s in case completion event is lost
        if (streamingTimeoutRef.current) clearTimeout(streamingTimeoutRef.current);
        streamingTimeoutRef.current = setTimeout(() => {
          console.warn('[CHAT_STREAM_DEBUG] Safety timeout: force-clearing streaming state after 120s');
          setStreaming(false);
          streamingIdRef.current = null;
        }, 120000);
      }
    };

    const handleToken = (payload: unknown) => {
      const data = (payload ?? {}) as Partial<{ content: string; full_content: string }>;

      const tokenContent = data.content ?? '';
      console.log(
        '[CHAT_STREAM_DEBUG] aria.token received, content_length=',
        tokenContent.length,
        'streamingIdRef=',
        streamingIdRef.current,
      );
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
        console.log('[CHAT_STREAM_DEBUG] Created streaming message, id=', streamingIdRef.current);
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
        render_mode: 'c1' | 'markdown';
        c1_response: string | null;
      }>;

      if (streamingIdRef.current) {
        updateMessageMetadata(streamingIdRef.current, {
          rich_content: data.rich_content ?? [],
          ui_commands: data.ui_commands ?? [],
          suggestions: data.suggestions ?? [],
          render_mode: data.render_mode,
          c1_response: data.c1_response,
        });
      }
    };

    const handleStreamError = (payload: unknown) => {
      const data = (payload ?? {}) as Partial<StreamErrorPayload>;
      console.log('[CHAT_STREAM_DEBUG] aria.stream_error received, setting isStreaming=false');
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

    const handleStreamComplete = (payload: unknown) => {
      // The backend sends metadata in aria.stream_complete payload:
      // { render_mode, c1_response, rich_content, ui_commands, suggestions }
      const data = (payload ?? {}) as Partial<{
        conversation_id: string;
        rich_content: RichContent[];
        ui_commands: UICommand[];
        suggestions: string[];
        render_mode: 'c1' | 'markdown';
        c1_response: string | null;
      }>;

      console.log(
        '[CHAT_STREAM_DEBUG] aria.stream_complete received:',
        JSON.stringify({
          render_mode: data.render_mode,
          c1_response_length: data.c1_response?.length ?? 0,
          rich_content_count: data.rich_content?.length ?? 0,
          suggestions_count: data.suggestions?.length ?? 0,
          streamingIdRef: streamingIdRef.current,
        }, null, 2),
      );

      // Update message metadata if we have a streaming message
      if (streamingIdRef.current) {
        // Save the message ID for potential C1 post-processing (aria.c1_render comes later)
        lastCompletedMessageIdRef.current = streamingIdRef.current;

        updateMessageMetadata(streamingIdRef.current, {
          rich_content: data.rich_content ?? [],
          ui_commands: data.ui_commands ?? [],
          suggestions: data.suggestions ?? [],
          render_mode: data.render_mode,
          c1_response: data.c1_response,
        });
        console.log('[CHAT_STREAM_DEBUG] Updated message with stream_complete metadata');
      }

      // Clear the safety timeout since we got the completion event
      if (streamingTimeoutRef.current) clearTimeout(streamingTimeoutRef.current);
      setStreaming(false);
      streamingIdRef.current = null;
    };

    const handleC1Render = (payload: unknown) => {
      // C1 post-processing upgrade: backend sends aria.c1_render after streaming
      // completes to upgrade the message from markdown to rich C1 UI
      const data = (payload ?? {}) as Partial<{
        conversation_id: string;
        content: string;
        render_mode: string;
      }>;

      // Use streamingIdRef if available, otherwise fall back to last completed message
      const targetMessageId = streamingIdRef.current || lastCompletedMessageIdRef.current;

      console.log(
        '[CHAT_STREAM_DEBUG] aria.c1_render received:',
        JSON.stringify({
          content_length: data.content?.length ?? 0,
          content_preview: data.content?.slice(0, 300),
          render_mode: data.render_mode,
          conversation_id: data.conversation_id,
          streamingIdRef: streamingIdRef.current,
          lastCompletedMessageId: lastCompletedMessageIdRef.current,
          targetMessageId,
        }, null, 2),
      );

      if (data.content && targetMessageId) {
        // Upgrade the message with C1 content
        console.log('[CHAT_STREAM_DEBUG] Updating message metadata with C1 content');
        updateMessageMetadata(targetMessageId, {
          render_mode: 'c1',
          c1_response: data.content,
        });
        // Verify the update happened
        setTimeout(() => {
          const messages = useConversationStore.getState().messages;
          const updated = messages.find(m => m.id === targetMessageId);
          console.log('[CHAT_STREAM_DEBUG] Post-update verification:', {
            messageId: targetMessageId,
            found: !!updated,
            render_mode: updated?.render_mode,
            c1_response_length: updated?.c1_response?.length ?? 0,
          });
        }, 100);
      } else {
        console.warn('[CHAT_STREAM_DEBUG] C1 render skipped:', {
          hasContent: !!data.content,
          hasTargetMessageId: !!targetMessageId,
        });
      }
    };

    wsManager.on(WS_EVENTS.ARIA_MESSAGE, handleAriaMessage);
    wsManager.on(WS_EVENTS.ARIA_THINKING, handleThinking);
    wsManager.on('aria.token', handleToken);
    wsManager.on('aria.metadata', handleMetadata);
    wsManager.on(WS_EVENTS.ARIA_STREAM_ERROR, handleStreamError);
    wsManager.on(WS_EVENTS.ARIA_STREAM_COMPLETE, handleStreamComplete);
    wsManager.on('aria.c1_render', handleC1Render);

    return () => {
      wsManager.off(WS_EVENTS.ARIA_MESSAGE, handleAriaMessage);
      wsManager.off(WS_EVENTS.ARIA_THINKING, handleThinking);
      wsManager.off('aria.token', handleToken);
      wsManager.off('aria.metadata', handleMetadata);
      wsManager.off(WS_EVENTS.ARIA_STREAM_ERROR, handleStreamError);
      wsManager.off(WS_EVENTS.ARIA_STREAM_COMPLETE, handleStreamComplete);
      wsManager.off('aria.c1_render', handleC1Render);
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

  // Skip - collapse to minimal bar, persist in sessionStorage
  const handleSkipBriefing = useCallback(() => {
    setBriefingSkipped(true);
    sessionStorage.setItem('briefingSkipped', 'true');
  }, []);

  // Expand - show full card again
  const handleExpandBriefing = useCallback(() => {
    setBriefingSkipped(false);
    sessionStorage.removeItem('briefingSkipped');
  }, []);

  // Read Summary - trigger C1 stream instead of text briefing
  const handleReadBriefing = useCallback(() => {
    setBriefingStreamRequested(true);
    dismissBriefing(); // Hide the card, stream will render below
  }, [dismissBriefing]);

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

  // Determine briefing card visibility
  // Show full card if briefing ready, not viewed, not dismissed, and user hasn't requested stream yet
  const showBriefingCard = Boolean(briefingReady && !briefingViewed && !briefingDismissed && !briefingStreamRequested && briefingId);
  // Show collapsed bar if user skipped the briefing
  const showCollapsedBar = Boolean(briefingReady && briefingSkipped && !briefingStreamRequested && briefingId);

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

      {/* Briefing Card - shown when briefing is ready and not yet viewed */}
      {(showBriefingCard || showCollapsedBar) && (
        <div className="px-6 pb-4">
          <VideoBriefingCard
            briefingId={briefingId!}
            duration={duration}
            topics={topics}
            userName={user?.full_name ?? undefined}
            onPlay={handlePlayBriefing}
            onRead={handleReadBriefing}
            onSkip={handleSkipBriefing}
            isCollapsed={showCollapsedBar}
            onExpand={handleExpandBriefing}
          />
        </div>
      )}

      <ConversationThread onStartTyping={handleStartTyping} />
      <SuggestionChips onSelect={handleSend} />
      <InputBar onSend={handleSend} />
    </div>
  );
}
