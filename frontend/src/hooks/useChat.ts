import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, useCallback } from "react";
import {
  getConversation,
  listConversations,
  sendMessage,
  streamMessage,
  updateConversationTitle,
  deleteConversation,
  searchConversations,
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

// Update conversation title mutation
export function useUpdateConversationTitle() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ conversationId, title }: { conversationId: string; title: string }) =>
      updateConversationTitle(conversationId, { title }),
    onSuccess: (_, variables) => {
      queryClient.invalidateQueries({
        queryKey: chatKeys.conversations(),
      });
      queryClient.invalidateQueries({
        queryKey: chatKeys.conversation(variables.conversationId),
      });
    },
  });
}

// Delete conversation mutation
export function useDeleteConversation() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deleteConversation,
    onSuccess: () => {
      queryClient.invalidateQueries({
        queryKey: chatKeys.conversations(),
      });
    },
  });
}

// Search conversations hook
export function useSearchConversations(query: string) {
  return useQuery({
    queryKey: [...chatKeys.conversations(), "search", query],
    queryFn: () => searchConversations(query),
    enabled: query.length > 0,
  });
}
