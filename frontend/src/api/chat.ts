import { apiClient } from "./client";

// Types
export interface ChatMessage {
  id: string;
  conversation_id: string;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  metadata?: Record<string, unknown>;
  /** Skill execution data attached to this message (Enhancement 5) */
  skill_execution?: {
    type: "simple" | "plan";
    skill_name?: string;
    status?: "pending" | "running" | "completed" | "failed" | "skipped";
    result_summary?: string | null;
    execution_time_ms?: number | null;
    plan_id?: string;
  } | null;
}

export interface Citation {
  id: string;
  type: string;
  content: string;
  confidence: number | null;
}

export interface Conversation {
  id: string;
  user_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  last_message_preview?: string | null;
  message_count?: number;
}

export interface ConversationListResponse {
  conversations: Conversation[];
  total: number;
}

export interface UpdateConversationTitleRequest {
  title: string;
}

export type UICommandAction =
  | 'navigate'
  | 'highlight'
  | 'update_intel_panel'
  | 'scroll_to'
  | 'switch_mode'
  | 'show_notification'
  | 'update_sidebar_badge'
  | 'open_modal';

export type HighlightEffect = 'glow' | 'pulse' | 'outline';

export interface UICommand {
  action: UICommandAction;
  route?: string;
  element?: string;
  effect?: HighlightEffect;
  duration?: number;
  content?: Record<string, unknown>;
  mode?: 'workspace' | 'dialogue' | 'compact_avatar';
  badge_count?: number;
  sidebar_item?: string;
  notification_type?: 'signal' | 'alert' | 'success' | 'info';
  notification_message?: string;
  modal_id?: string;
  modal_data?: Record<string, unknown>;
}

export interface RichContent {
  type: string;
  data: Record<string, unknown>;
}

export interface SendMessageRequest {
  message: string;
  conversation_id?: string;
}

export interface SendMessageResponse {
  message: string;
  citations: Citation[];
  conversation_id: string;
  rich_content: RichContent[];
  ui_commands: UICommand[];
  suggestions: string[];
}

// API functions
export async function sendMessage(data: SendMessageRequest): Promise<SendMessageResponse> {
  const response = await apiClient.post<SendMessageResponse>("/chat", data);
  return response.data;
}

export async function getConversation(conversationId: string): Promise<ChatMessage[]> {
  const response = await apiClient.get<ChatMessage[]>(
    `/chat/conversations/${conversationId}/messages`
  );
  return response.data;
}

export async function listConversations(): Promise<Conversation[]> {
  const response = await apiClient.get<ConversationListResponse>("/chat/conversations");
  return response.data.conversations;
}

export async function updateConversationTitle(
  conversationId: string,
  data: UpdateConversationTitleRequest
): Promise<Conversation> {
  const response = await apiClient.put<Conversation>(
    `/chat/conversations/${conversationId}/title`,
    data
  );
  return response.data;
}

export async function deleteConversation(conversationId: string): Promise<void> {
  await apiClient.delete(`/chat/conversations/${conversationId}`);
}

export async function searchConversations(query: string): Promise<Conversation[]> {
  const response = await apiClient.get<ConversationListResponse>("/chat/conversations", {
    params: { search: query },
  });
  return response.data.conversations;
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

  // 120-second timeout for streaming chat (longer than default 30s)
  const streamTimeout = setTimeout(() => controller.abort(), 120_000);

  fetch(`${baseUrl}/api/v1/chat/stream`, {
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
              clearTimeout(streamTimeout);
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
              } else if (event.type === "error") {
                clearTimeout(streamTimeout);
                onError(new Error(event.content));
                return;
              } else if (event.type === "complete") {
                // Envelope data available for future UI command processing
              }
            } catch {
              // Ignore parse errors for incomplete chunks
            }
          }
        }
      }
    })
    .catch((error) => {
      clearTimeout(streamTimeout);
      if (error.name !== "AbortError") {
        onError(error);
      }
    });

  return () => {
    clearTimeout(streamTimeout);
    controller.abort();
  };
}
