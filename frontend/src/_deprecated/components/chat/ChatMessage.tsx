import { MarkdownRenderer } from "./MarkdownRenderer";
import { FeedbackWidget } from "@/components/FeedbackWidget";
import { SkillExecutionInline } from "@/components/skills";
import type { SkillExecutionData } from "@/components/skills";
import type { ChatMessage as ChatMessageType } from "@/api/chat";

interface ChatMessageProps {
  message: ChatMessageType;
  isStreaming?: boolean;
}

function AriaAvatar() {
  return (
    <div className="relative flex-shrink-0">
      {/* Outer glow */}
      <div className="absolute inset-0 bg-gradient-to-br from-primary-400 to-primary-600 rounded-full blur-md opacity-40" />

      {/* Avatar container */}
      <div className="relative w-10 h-10 rounded-full bg-gradient-to-br from-primary-500 to-primary-700 flex items-center justify-center shadow-lg shadow-primary-500/20 border border-primary-400/30">
        {/* ARIA icon - stylized A */}
        <svg
          className="w-5 h-5 text-white"
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

      {/* Status indicator */}
      <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-success rounded-full border-2 border-slate-900" />
    </div>
  );
}

function UserAvatar() {
  return (
    <div className="w-10 h-10 rounded-full bg-gradient-to-br from-slate-600 to-slate-700 flex items-center justify-center flex-shrink-0 border border-slate-500/30">
      <svg
        className="w-5 h-5 text-slate-300"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth={2}
          d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
        />
      </svg>
    </div>
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-center gap-1.5 py-2">
      <div
        className="w-2 h-2 bg-primary-400 rounded-full animate-bounce"
        style={{ animationDelay: "0ms", animationDuration: "600ms" }}
      />
      <div
        className="w-2 h-2 bg-primary-400 rounded-full animate-bounce"
        style={{ animationDelay: "150ms", animationDuration: "600ms" }}
      />
      <div
        className="w-2 h-2 bg-primary-400 rounded-full animate-bounce"
        style={{ animationDelay: "300ms", animationDuration: "600ms" }}
      />
    </div>
  );
}

export function ChatMessage({ message, isStreaming }: ChatMessageProps) {
  const isUser = message.role === "user";

  return (
    <div
      className={`flex gap-4 ${isUser ? "flex-row-reverse" : "flex-row"}`}
    >
      {/* Avatar */}
      {isUser ? <UserAvatar /> : <AriaAvatar />}

      {/* Message bubble */}
      <div
        className={`relative max-w-[80%] md:max-w-[70%] ${
          isUser ? "items-end" : "items-start"
        }`}
      >
        {/* Role label */}
        <div
          className={`text-xs font-medium mb-1.5 ${
            isUser ? "text-right text-slate-500" : "text-left text-primary-400"
          }`}
        >
          {isUser ? "You" : "ARIA"}
        </div>

        {/* Bubble */}
        <div
          className={`relative rounded-2xl px-5 py-4 ${
            isUser
              ? "bg-gradient-to-br from-primary-600 to-primary-700 text-white shadow-lg shadow-primary-600/20"
              : "bg-slate-800/80 text-slate-100 border border-white/5 backdrop-blur-sm"
          }`}
        >
          {/* Glass effect for ARIA messages */}
          {!isUser && (
            <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-white/5 to-transparent pointer-events-none" />
          )}

          {/* Content */}
          <div className="relative">
            {message.content ? (
              isUser ? (
                <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>
              ) : (
                <MarkdownRenderer content={message.content} />
              )
            ) : isStreaming ? (
              <TypingIndicator />
            ) : null}
          </div>

          {/* Skill execution inline (Enhancement 5) */}
          {!isUser && message.skill_execution && (
            <SkillExecutionInline
              execution={{
                type: message.skill_execution.type,
                skillName: message.skill_execution.skill_name,
                status: message.skill_execution.status,
                resultSummary: message.skill_execution.result_summary,
                executionTimeMs: message.skill_execution.execution_time_ms,
                planId: message.skill_execution.plan_id,
              } as SkillExecutionData}
            />
          )}

          {/* Streaming cursor */}
          {isStreaming && message.content && (
            <span className="inline-block w-0.5 h-5 bg-primary-400 animate-pulse ml-0.5 align-middle" />
          )}
        </div>

        {/* Timestamp */}
        <div
          className={`text-xs text-slate-500 mt-1.5 ${
            isUser ? "text-right" : "text-left"
          }`}
        >
          {new Date(message.created_at).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </div>

        {/* Feedback widget for ARIA messages */}
        {!isUser && !isStreaming && message.content && (
          <div className="mt-1">
            <FeedbackWidget messageId={message.id} />
          </div>
        )}
      </div>
    </div>
  );
}

// Export for use in streaming scenarios
export function StreamingMessage({ content }: { content: string }) {
  return (
    <ChatMessage
      message={{
        id: "streaming",
        conversation_id: "",
        role: "assistant",
        content,
        created_at: new Date().toISOString(),
      }}
      isStreaming={true}
    />
  );
}
