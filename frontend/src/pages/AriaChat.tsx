import { useState, useRef, useEffect, useCallback } from "react";
import { DashboardLayout } from "@/components/DashboardLayout";
import { ChatInput, ChatMessage, StreamingMessage } from "@/components/chat";
import { useStreamingMessage } from "@/hooks/useChat";
import type { ChatMessage as ChatMessageType } from "@/api/chat";

export function AriaChatPage() {
  const [messages, setMessages] = useState<ChatMessageType[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const cancelStreamRef = useRef<(() => void) | null>(null);

  const { isStreaming, streamedContent, startStream, reset } = useStreamingMessage();

  // Auto-scroll to bottom when messages change
  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamedContent, scrollToBottom]);

  const handleSend = useCallback(
    (content: string) => {
      // Add user message immediately
      const userMessage: ChatMessageType = {
        id: crypto.randomUUID(),
        conversation_id: conversationId || "",
        role: "user",
        content,
        created_at: new Date().toISOString(),
      };
      setMessages((prev) => [...prev, userMessage]);

      // Reset any previous stream state
      reset();

      // Start streaming
      cancelStreamRef.current = startStream(
        {
          content,
          conversation_id: conversationId || undefined,
        },
        (assistantMessage) => {
          // On complete, add the full message
          setMessages((prev) => [...prev, assistantMessage]);
          setConversationId(assistantMessage.conversation_id);
          reset();
        }
      );
    },
    [conversationId, startStream, reset]
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (cancelStreamRef.current) {
        cancelStreamRef.current();
      }
    };
  }, []);

  const handleNewConversation = useCallback(() => {
    setMessages([]);
    setConversationId(null);
    reset();
  }, [reset]);

  return (
    <DashboardLayout>
      <div className="relative h-[calc(100vh-4rem)] flex flex-col">
        {/* Atmospheric background */}
        <div className="absolute inset-0 bg-gradient-to-b from-slate-900 via-slate-900 to-slate-950 pointer-events-none" />
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top,_var(--tw-gradient-stops))] from-primary-900/20 via-transparent to-transparent pointer-events-none" />

        {/* Header */}
        <div className="relative border-b border-white/5 bg-slate-900/50 backdrop-blur-sm">
          <div className="max-w-4xl mx-auto px-4 lg:px-8 py-4 flex items-center justify-between">
            <div className="flex items-center gap-4">
              {/* ARIA Avatar */}
              <div className="relative">
                <div className="absolute inset-0 bg-gradient-to-br from-primary-400 to-primary-600 rounded-full blur-lg opacity-30" />
                <div className="relative w-12 h-12 rounded-full bg-gradient-to-br from-primary-500 to-primary-700 flex items-center justify-center shadow-lg border border-primary-400/30">
                  <svg
                    className="w-6 h-6 text-white"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  >
                    <path d="M12 2L2 22h20L12 2z" />
                    <path d="M7 16h10" />
                  </svg>
                </div>
                <div className="absolute bottom-0 right-0 w-3.5 h-3.5 bg-emerald-500 rounded-full border-2 border-slate-900" />
              </div>

              <div>
                <h1 className="text-lg font-semibold text-white">ARIA</h1>
                <p className="text-sm text-slate-400">Your AI Department Director</p>
              </div>
            </div>

            {/* New conversation button */}
            <button
              onClick={handleNewConversation}
              className="px-4 py-2 text-sm font-medium text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-all duration-200 flex items-center gap-2"
            >
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 4v16m8-8H4"
                />
              </svg>
              New Chat
            </button>
          </div>
        </div>

        {/* Messages area */}
        <div className="relative flex-1 overflow-y-auto">
          <div className="max-w-4xl mx-auto px-4 lg:px-8 py-6 space-y-6">
            {/* Empty state */}
            {messages.length === 0 && !isStreaming && (
              <div className="flex flex-col items-center justify-center h-full min-h-[400px] text-center">
                {/* Large ARIA icon */}
                <div className="relative mb-6">
                  <div className="absolute inset-0 bg-gradient-to-br from-primary-400 to-primary-600 rounded-full blur-2xl opacity-20 scale-150" />
                  <div className="relative w-20 h-20 rounded-full bg-gradient-to-br from-primary-500 to-primary-700 flex items-center justify-center shadow-2xl border border-primary-400/30">
                    <svg
                      className="w-10 h-10 text-white"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      strokeWidth="2"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                    >
                      <path d="M12 2L2 22h20L12 2z" />
                      <path d="M7 16h10" />
                    </svg>
                  </div>
                </div>

                <h2 className="text-2xl font-semibold text-white mb-2">
                  How can I help you today?
                </h2>
                <p className="text-slate-400 max-w-md mb-8">
                  I'm ARIA, your AI Department Director. Ask me about leads, research,
                  market intelligence, or any strategic questions.
                </p>

                {/* Suggestion chips */}
                <div className="flex flex-wrap justify-center gap-2 max-w-lg">
                  {[
                    "Research Acme Corp for my meeting tomorrow",
                    "What's the latest news on biotech funding?",
                    "Help me draft a follow-up email",
                    "Summarize my top priority leads",
                  ].map((suggestion) => (
                    <button
                      key={suggestion}
                      onClick={() => handleSend(suggestion)}
                      className="px-4 py-2 text-sm text-slate-300 bg-slate-800/50 hover:bg-slate-800 border border-white/5 rounded-full transition-all duration-200 hover:border-primary-500/30"
                    >
                      {suggestion}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {/* Messages */}
            {messages.map((message, index) => (
              <div
                key={message.id}
                className="animate-in fade-in slide-in-from-bottom-2"
                style={{
                  animationDelay: `${Math.min(index * 50, 200)}ms`,
                  animationFillMode: "both",
                  animationDuration: "300ms",
                }}
              >
                <ChatMessage message={message} />
              </div>
            ))}

            {/* Streaming message */}
            {isStreaming && (
              <div className="animate-in fade-in slide-in-from-bottom-2">
                <StreamingMessage content={streamedContent} />
              </div>
            )}

            {/* Scroll anchor */}
            <div ref={messagesEndRef} />
          </div>
        </div>

        {/* Input area */}
        <div className="relative border-t border-white/5 bg-slate-900/80 backdrop-blur-xl">
          <div className="max-w-4xl mx-auto px-4 lg:px-8 py-4">
            <ChatInput
              onSend={handleSend}
              disabled={isStreaming}
              placeholder={
                isStreaming ? "ARIA is thinking..." : "Message ARIA..."
              }
            />
          </div>
        </div>
      </div>
    </DashboardLayout>
  );
}
