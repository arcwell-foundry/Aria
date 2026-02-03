# US-402: ARIA Chat UI Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create a premium, Apple-inspired chat interface for conversing with ARIA at `/dashboard/aria`

**Architecture:** Full-page chat interface with message history, streaming responses, markdown rendering with syntax highlighting. Uses existing DashboardLayout wrapper. Creates new API client for chat endpoints, React Query hooks for state management, and dedicated components for messages, input, and typing indicator.

**Tech Stack:** React 18, TypeScript, Tailwind CSS 4, React Query, Server-Sent Events (SSE), react-markdown, react-syntax-highlighter

**Design Direction:** Apple-inspired luxury - premium SF Pro typography, sophisticated neutral palette with subtle cyan accents, buttery 60fps animations, tasteful glass morphism, generous whitespace, refined shadows and layering.

---

## Dependencies to Install

```bash
npm install react-markdown react-syntax-highlighter
npm install -D @types/react-syntax-highlighter
```

---

## Task 1: Install Dependencies

**Files:**
- Modify: `frontend/package.json`

**Step 1: Install markdown and syntax highlighting packages**

Run:
```bash
cd frontend && npm install react-markdown react-syntax-highlighter && npm install -D @types/react-syntax-highlighter
```

**Step 2: Verify installation**

Run: `cd frontend && npm ls react-markdown react-syntax-highlighter`
Expected: Both packages listed with versions

**Step 3: Commit**

```bash
git add frontend/package.json frontend/package-lock.json
git commit -m "deps: add react-markdown and react-syntax-highlighter for chat UI"
```

---

## Task 2: Create Chat API Types and Client

**Files:**
- Create: `frontend/src/api/chat.ts`

**Step 1: Create the chat API module**

Create `frontend/src/api/chat.ts`:

```typescript
import { apiClient } from "./client";

// Types
export interface ChatMessage {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
}

export interface Conversation {
  id: string;
  user_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface SendMessageRequest {
  content: string;
  conversation_id?: string;
}

export interface SendMessageResponse {
  message: ChatMessage;
  conversation_id: string;
}

// API functions
export async function sendMessage(data: SendMessageRequest): Promise<SendMessageResponse> {
  const response = await apiClient.post<SendMessageResponse>("/chat/message", data);
  return response.data;
}

export async function getConversation(conversationId: string): Promise<ChatMessage[]> {
  const response = await apiClient.get<ChatMessage[]>(`/chat/conversations/${conversationId}/messages`);
  return response.data;
}

export async function listConversations(): Promise<Conversation[]> {
  const response = await apiClient.get<Conversation[]>("/chat/conversations");
  return response.data;
}

// SSE streaming helper
export function streamMessage(
  data: SendMessageRequest,
  onToken: (token: string) => void,
  onComplete: (message: ChatMessage) => void,
  onError: (error: Error) => void
): () => void {
  const token = localStorage.getItem("access_token");
  const baseUrl = import.meta.env.VITE_API_URL || "http://localhost:8000";

  const controller = new AbortController();

  fetch(`${baseUrl}/api/v1/chat/message/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Authorization": `Bearer ${token}`,
    },
    body: JSON.stringify(data),
    signal: controller.signal,
  })
    .then(async (response) => {
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();
      let buffer = "";
      let fullContent = "";
      let messageId = "";
      let conversationId = data.conversation_id || "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          if (line.startsWith("data: ")) {
            const jsonStr = line.slice(6);
            if (jsonStr === "[DONE]") {
              onComplete({
                id: messageId,
                conversation_id: conversationId,
                role: "assistant",
                content: fullContent,
                created_at: new Date().toISOString(),
              });
              return;
            }

            try {
              const event = JSON.parse(jsonStr);
              if (event.type === "token") {
                fullContent += event.content;
                onToken(event.content);
              } else if (event.type === "metadata") {
                messageId = event.message_id;
                conversationId = event.conversation_id;
              }
            } catch {
              // Ignore parse errors for incomplete chunks
            }
          }
        }
      }
    })
    .catch((error) => {
      if (error.name !== "AbortError") {
        onError(error);
      }
    });

  return () => controller.abort();
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/api/chat.ts
git commit -m "feat(chat): add chat API client with SSE streaming support"
```

---

## Task 3: Create Chat React Query Hooks

**Files:**
- Create: `frontend/src/hooks/useChat.ts`

**Step 1: Create the chat hooks**

Create `frontend/src/hooks/useChat.ts`:

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, useCallback } from "react";
import {
  getConversation,
  listConversations,
  sendMessage,
  streamMessage,
  type ChatMessage,
  type SendMessageRequest,
} from "@/api/chat";

// Query keys
export const chatKeys = {
  all: ["chat"] as const,
  conversations: () => [...chatKeys.all, "conversations"] as const,
  conversation: (id: string) => [...chatKeys.all, "conversation", id] as const,
};

// List conversations
export function useConversations() {
  return useQuery({
    queryKey: chatKeys.conversations(),
    queryFn: listConversations,
  });
}

// Get conversation messages
export function useConversationMessages(conversationId: string | null) {
  return useQuery({
    queryKey: chatKeys.conversation(conversationId || ""),
    queryFn: () => getConversation(conversationId!),
    enabled: !!conversationId,
  });
}

// Send message mutation (non-streaming)
export function useSendMessage() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (data: SendMessageRequest) => sendMessage(data),
    onSuccess: (response) => {
      queryClient.invalidateQueries({
        queryKey: chatKeys.conversation(response.conversation_id),
      });
      queryClient.invalidateQueries({
        queryKey: chatKeys.conversations(),
      });
    },
  });
}

// Streaming message hook
export function useStreamingMessage() {
  const [isStreaming, setIsStreaming] = useState(false);
  const [streamedContent, setStreamedContent] = useState("");
  const [error, setError] = useState<Error | null>(null);
  const queryClient = useQueryClient();

  const startStream = useCallback(
    (
      data: SendMessageRequest,
      onComplete?: (message: ChatMessage) => void
    ): (() => void) => {
      setIsStreaming(true);
      setStreamedContent("");
      setError(null);

      const cancel = streamMessage(
        data,
        (token) => {
          setStreamedContent((prev) => prev + token);
        },
        (message) => {
          setIsStreaming(false);
          queryClient.invalidateQueries({
            queryKey: chatKeys.conversation(message.conversation_id),
          });
          queryClient.invalidateQueries({
            queryKey: chatKeys.conversations(),
          });
          onComplete?.(message);
        },
        (err) => {
          setIsStreaming(false);
          setError(err);
        }
      );

      return cancel;
    },
    [queryClient]
  );

  const reset = useCallback(() => {
    setStreamedContent("");
    setError(null);
  }, []);

  return {
    isStreaming,
    streamedContent,
    error,
    startStream,
    reset,
  };
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/hooks/useChat.ts
git commit -m "feat(chat): add React Query hooks for chat with streaming support"
```

---

## Task 4: Create MarkdownRenderer Component

**Files:**
- Create: `frontend/src/components/chat/MarkdownRenderer.tsx`

**Step 1: Create the markdown renderer with syntax highlighting and copy button**

Create `frontend/src/components/chat/MarkdownRenderer.tsx`:

```typescript
import { useState, useCallback, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { oneDark } from "react-syntax-highlighter/dist/esm/styles/prism";

interface MarkdownRendererProps {
  content: string;
}

interface CodeBlockProps {
  language: string;
  children: string;
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(async () => {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }, [text]);

  return (
    <button
      onClick={handleCopy}
      className="absolute top-3 right-3 p-2 rounded-lg bg-white/5 hover:bg-white/10 border border-white/10 transition-all duration-200 group"
      aria-label={copied ? "Copied" : "Copy code"}
    >
      {copied ? (
        <svg
          className="w-4 h-4 text-emerald-400"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M5 13l4 4L19 7"
          />
        </svg>
      ) : (
        <svg
          className="w-4 h-4 text-slate-400 group-hover:text-white transition-colors"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"
          />
        </svg>
      )}
    </button>
  );
}

function CodeBlock({ language, children }: CodeBlockProps) {
  const code = String(children).replace(/\n$/, "");

  return (
    <div className="relative group my-4 rounded-xl overflow-hidden border border-white/10">
      {/* Language label */}
      {language && (
        <div className="flex items-center justify-between px-4 py-2 bg-slate-800/80 border-b border-white/5">
          <span className="text-xs font-medium text-slate-400 uppercase tracking-wider">
            {language}
          </span>
        </div>
      )}

      <div className="relative">
        <SyntaxHighlighter
          style={oneDark}
          language={language || "text"}
          PreTag="div"
          customStyle={{
            margin: 0,
            padding: "1rem",
            background: "rgba(15, 23, 42, 0.8)",
            fontSize: "0.875rem",
            lineHeight: "1.6",
          }}
          codeTagProps={{
            style: {
              fontFamily: "var(--font-mono)",
            },
          }}
        >
          {code}
        </SyntaxHighlighter>
        <CopyButton text={code} />
      </div>
    </div>
  );
}

export function MarkdownRenderer({ content }: MarkdownRendererProps) {
  return (
    <ReactMarkdown
      components={{
        code({ className, children, ...props }) {
          const match = /language-(\w+)/.exec(className || "");
          const isInline = !match && !String(children).includes("\n");

          if (isInline) {
            return (
              <code
                className="px-1.5 py-0.5 rounded bg-white/10 text-primary-300 font-mono text-sm"
                {...props}
              >
                {children}
              </code>
            );
          }

          return (
            <CodeBlock language={match?.[1] || ""}>
              {String(children)}
            </CodeBlock>
          );
        },
        p({ children }) {
          return <p className="mb-4 last:mb-0 leading-relaxed">{children}</p>;
        },
        ul({ children }) {
          return <ul className="mb-4 pl-6 list-disc space-y-2">{children}</ul>;
        },
        ol({ children }) {
          return <ol className="mb-4 pl-6 list-decimal space-y-2">{children}</ol>;
        },
        li({ children }) {
          return <li className="leading-relaxed">{children}</li>;
        },
        h1({ children }) {
          return <h1 className="text-2xl font-semibold mb-4 mt-6 first:mt-0">{children}</h1>;
        },
        h2({ children }) {
          return <h2 className="text-xl font-semibold mb-3 mt-5 first:mt-0">{children}</h2>;
        },
        h3({ children }) {
          return <h3 className="text-lg font-semibold mb-2 mt-4 first:mt-0">{children}</h3>;
        },
        blockquote({ children }) {
          return (
            <blockquote className="border-l-2 border-primary-500/50 pl-4 my-4 text-slate-300 italic">
              {children}
            </blockquote>
          );
        },
        a({ href, children }) {
          return (
            <a
              href={href}
              target="_blank"
              rel="noopener noreferrer"
              className="text-primary-400 hover:text-primary-300 underline underline-offset-2 transition-colors"
            >
              {children}
            </a>
          );
        },
        hr() {
          return <hr className="my-6 border-white/10" />;
        },
        strong({ children }) {
          return <strong className="font-semibold text-white">{children}</strong>;
        },
        table({ children }) {
          return (
            <div className="my-4 overflow-x-auto">
              <table className="w-full border-collapse">{children}</table>
            </div>
          );
        },
        th({ children }) {
          return (
            <th className="px-4 py-2 text-left font-semibold bg-white/5 border border-white/10">
              {children}
            </th>
          );
        },
        td({ children }) {
          return (
            <td className="px-4 py-2 border border-white/10">{children}</td>
          );
        },
      }}
    >
      {content}
    </ReactMarkdown>
  );
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/chat/MarkdownRenderer.tsx
git commit -m "feat(chat): add MarkdownRenderer with syntax highlighting and copy button"
```

---

## Task 5: Create ChatMessage Component

**Files:**
- Create: `frontend/src/components/chat/ChatMessage.tsx`

**Step 1: Create the message bubble component**

Create `frontend/src/components/chat/ChatMessage.tsx`:

```typescript
import { MarkdownRenderer } from "./MarkdownRenderer";
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
      <div className="absolute -bottom-0.5 -right-0.5 w-3 h-3 bg-emerald-500 rounded-full border-2 border-slate-900" />
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
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/chat/ChatMessage.tsx
git commit -m "feat(chat): add ChatMessage component with Apple-inspired styling"
```

---

## Task 6: Create ChatInput Component

**Files:**
- Create: `frontend/src/components/chat/ChatInput.tsx`

**Step 1: Create the premium input component**

Create `frontend/src/components/chat/ChatInput.tsx`:

```typescript
import { useState, useRef, useCallback, useEffect, type KeyboardEvent } from "react";

interface ChatInputProps {
  onSend: (content: string) => void;
  disabled?: boolean;
  placeholder?: string;
}

export function ChatInput({
  onSend,
  disabled = false,
  placeholder = "Message ARIA...",
}: ChatInputProps) {
  const [content, setContent] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Auto-resize textarea
  const adjustHeight = useCallback(() => {
    const textarea = textareaRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
    }
  }, []);

  useEffect(() => {
    adjustHeight();
  }, [content, adjustHeight]);

  const handleSubmit = useCallback(() => {
    const trimmed = content.trim();
    if (trimmed && !disabled) {
      onSend(trimmed);
      setContent("");
      // Reset height
      if (textareaRef.current) {
        textareaRef.current.style.height = "auto";
      }
    }
  }, [content, disabled, onSend]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSubmit();
      }
    },
    [handleSubmit]
  );

  return (
    <div className="relative">
      {/* Outer container with glass effect */}
      <div className="relative bg-slate-800/60 backdrop-blur-xl rounded-2xl border border-white/10 shadow-2xl shadow-black/20 overflow-hidden">
        {/* Subtle gradient overlay */}
        <div className="absolute inset-0 bg-gradient-to-b from-white/5 to-transparent pointer-events-none" />

        {/* Input area */}
        <div className="relative flex items-end gap-3 p-4">
          {/* Textarea */}
          <div className="flex-1 relative">
            <textarea
              ref={textareaRef}
              value={content}
              onChange={(e) => setContent(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={placeholder}
              disabled={disabled}
              rows={1}
              className="w-full bg-transparent text-white placeholder-slate-400 resize-none outline-none text-base leading-relaxed disabled:opacity-50 disabled:cursor-not-allowed"
              style={{ fontFamily: "var(--font-sans)" }}
            />
          </div>

          {/* Send button */}
          <button
            onClick={handleSubmit}
            disabled={disabled || !content.trim()}
            className="relative flex-shrink-0 w-11 h-11 rounded-xl bg-gradient-to-br from-primary-500 to-primary-600 text-white flex items-center justify-center transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed hover:from-primary-400 hover:to-primary-500 hover:shadow-lg hover:shadow-primary-500/30 active:scale-95"
          >
            {/* Button glow */}
            {content.trim() && !disabled && (
              <div className="absolute inset-0 rounded-xl bg-primary-400 blur-md opacity-30" />
            )}

            {/* Icon */}
            <svg
              className="relative w-5 h-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 19V5m0 0l-7 7m7-7l7 7"
              />
            </svg>
          </button>
        </div>

        {/* Keyboard hint */}
        <div className="px-4 pb-3 flex items-center justify-between text-xs text-slate-500">
          <span>
            Press <kbd className="px-1.5 py-0.5 rounded bg-slate-700/50 font-mono text-slate-400">Enter</kbd> to send
          </span>
          <span>
            <kbd className="px-1.5 py-0.5 rounded bg-slate-700/50 font-mono text-slate-400">Shift + Enter</kbd> for new line
          </span>
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/chat/ChatInput.tsx
git commit -m "feat(chat): add premium ChatInput with glass morphism"
```

---

## Task 7: Create Chat Component Index

**Files:**
- Create: `frontend/src/components/chat/index.ts`

**Step 1: Create the barrel export file**

Create `frontend/src/components/chat/index.ts`:

```typescript
export { ChatInput } from "./ChatInput";
export { ChatMessage, StreamingMessage } from "./ChatMessage";
export { MarkdownRenderer } from "./MarkdownRenderer";
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/chat/index.ts
git commit -m "feat(chat): add component barrel exports"
```

---

## Task 8: Create AriaChat Page

**Files:**
- Create: `frontend/src/pages/AriaChat.tsx`

**Step 1: Create the main chat page**

Create `frontend/src/pages/AriaChat.tsx`:

```typescript
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
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/pages/AriaChat.tsx
git commit -m "feat(chat): add AriaChatPage with streaming support and suggestions"
```

---

## Task 9: Update Pages Index and App Router

**Files:**
- Modify: `frontend/src/pages/index.ts`
- Modify: `frontend/src/App.tsx`

**Step 1: Export AriaChatPage from pages index**

Modify `frontend/src/pages/index.ts` to add the export:

```typescript
export { AriaChatPage } from "./AriaChat";
export { DashboardPage } from "./Dashboard";
export { GoalsPage } from "./Goals";
export { LoginPage } from "./Login";
export { SignupPage } from "./Signup";
```

**Step 2: Add route to App.tsx**

Modify `frontend/src/App.tsx` to add the chat route. Find the imports section and add `AriaChatPage`:

```typescript
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "@/contexts/AuthContext";
import { ProtectedRoute } from "@/components/ProtectedRoute";
import { LoginPage, SignupPage, DashboardPage, GoalsPage, AriaChatPage } from "@/pages";
```

Then add the new route after the `/goals` route:

```typescript
<Route
  path="/dashboard/aria"
  element={
    <ProtectedRoute>
      <AriaChatPage />
    </ProtectedRoute>
  }
/>
```

**Step 3: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 4: Verify build succeeds**

Run: `cd frontend && npm run build`
Expected: Build completes successfully

**Step 5: Commit**

```bash
git add frontend/src/pages/index.ts frontend/src/App.tsx
git commit -m "feat(chat): add /dashboard/aria route to app router"
```

---

## Task 10: Update DashboardLayout Navigation

**Files:**
- Modify: `frontend/src/components/DashboardLayout.tsx`

**Step 1: Update the ARIA Chat link in navigation**

In `frontend/src/components/DashboardLayout.tsx`, update the `navItems` array. Change the ARIA Chat href from `/chat` to `/dashboard/aria`:

```typescript
const navItems = [
  { name: "Dashboard", href: "/dashboard", icon: "home" },
  { name: "ARIA Chat", href: "/dashboard/aria", icon: "chat" },
  { name: "Goals", href: "/goals", icon: "target" },
  { name: "Lead Memory", href: "/leads", icon: "users" },
  { name: "Daily Briefing", href: "/briefing", icon: "calendar" },
  { name: "Settings", href: "/settings", icon: "settings" },
];
```

**Step 2: Verify TypeScript compiles**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 3: Commit**

```bash
git add frontend/src/components/DashboardLayout.tsx
git commit -m "fix(nav): update ARIA Chat link to /dashboard/aria"
```

---

## Task 11: Add Animation Keyframes to CSS

**Files:**
- Modify: `frontend/src/index.css`

**Step 1: Add bounce animation for typing indicator**

Add to `frontend/src/index.css` after the existing animation rules:

```css
@keyframes bounce {
  0%, 100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-4px);
  }
}

.animate-bounce {
  animation: bounce 0.6s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}

.animate-pulse {
  animation: pulse 1s ease-in-out infinite;
}

.slide-in-from-bottom-2 {
  --tw-enter-translate-y: 0.5rem;
}
```

**Step 2: Verify build succeeds**

Run: `cd frontend && npm run build`
Expected: Build completes successfully

**Step 3: Commit**

```bash
git add frontend/src/index.css
git commit -m "feat(css): add bounce and pulse animations for chat UI"
```

---

## Task 12: Final Verification and Quality Gates

**Files:**
- All modified/created files

**Step 1: Run full TypeScript check**

Run: `cd frontend && npm run typecheck`
Expected: No errors

**Step 2: Run ESLint**

Run: `cd frontend && npm run lint`
Expected: No errors or warnings

**Step 3: Run build**

Run: `cd frontend && npm run build`
Expected: Build completes successfully

**Step 4: Manual verification (if dev server available)**

Start dev server: `cd frontend && npm run dev`
Navigate to: `http://localhost:3000/dashboard/aria`

Verify:
- [ ] Page loads with ARIA header and avatar
- [ ] Empty state shows suggestions
- [ ] Input field is visible and functional
- [ ] Navigation sidebar shows "ARIA Chat" as active
- [ ] Mobile responsive (resize browser)

**Step 5: Final commit with summary**

If any lint/type fixes were needed, commit them:

```bash
git add -A
git commit -m "feat(US-402): implement ARIA Chat UI with streaming and markdown support

- Add chat API client with SSE streaming
- Add React Query hooks for chat state
- Add MarkdownRenderer with syntax highlighting and copy button
- Add ChatMessage component with Apple-inspired styling
- Add ChatInput with glass morphism effect
- Add AriaChatPage with empty state and suggestions
- Add /dashboard/aria route
- Mobile responsive

Closes US-402"
```

---

## Summary of Files Created/Modified

### Created (7 files):
- `frontend/src/api/chat.ts` - Chat API client with SSE streaming
- `frontend/src/hooks/useChat.ts` - React Query hooks for chat
- `frontend/src/components/chat/MarkdownRenderer.tsx` - Markdown with syntax highlighting
- `frontend/src/components/chat/ChatMessage.tsx` - Message bubbles with avatars
- `frontend/src/components/chat/ChatInput.tsx` - Premium input component
- `frontend/src/components/chat/index.ts` - Barrel exports
- `frontend/src/pages/AriaChat.tsx` - Main chat page

### Modified (4 files):
- `frontend/package.json` - Added react-markdown, react-syntax-highlighter
- `frontend/src/pages/index.ts` - Export AriaChatPage
- `frontend/src/App.tsx` - Add /dashboard/aria route
- `frontend/src/components/DashboardLayout.tsx` - Update nav link
- `frontend/src/index.css` - Add animations

---

## Notes for Implementation

1. **Backend Dependency**: This UI assumes the chat backend (US-401) is complete with streaming support. If not available, the chat will fail gracefully but won't show responses.

2. **Mock Mode**: For development without backend, you could temporarily modify `useStreamingMessage` to return mock data.

3. **Fonts**: The design uses the existing `DM Sans` font from the project. For a more Apple-like feel, consider adding SF Pro if licensed.

4. **Color System**: Uses existing `primary-*` colors which are cyan-based. The design works within the established dark theme.

5. **Mobile First**: All components are responsive and work on mobile viewports.
