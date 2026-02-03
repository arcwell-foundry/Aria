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

export interface ConversationListResponse {
  conversations: Conversation[];
  total: number;
}

export interface UpdateConversationTitleRequest {
  title: string;
}

export interface DeleteConversationResponse {
  status: string;
  id: string;
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
  const response = await apiClient.get<Conversation[]>("/chat/conversations", {
    params: { search: query },
  });
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
