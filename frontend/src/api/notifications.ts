import { apiClient } from "./client";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

// Types
export type NotificationType =
  | "briefing_ready"
  | "signal_detected"
  | "task_due"
  | "meeting_brief_ready"
  | "draft_ready";

export interface Notification {
  id: string;
  user_id: string;
  type: NotificationType;
  title: string;
  message: string | null;
  link: string | null;
  metadata: Record<string, unknown>;
  read_at: string | null;
  created_at: string;
}

export interface NotificationListResponse {
  notifications: Notification[];
  total: number;
  unread_count: number;
}

export interface UnreadCountResponse {
  count: number;
}

// API functions
export async function getNotifications(params: {
  limit?: number;
  offset?: number;
  unreadOnly?: boolean;
}): Promise<NotificationListResponse> {
  const { limit = 20, offset = 0, unreadOnly = false } = params;
  const response = await apiClient.get<NotificationListResponse>("/notifications", {
    params: { limit, offset, unread_only: unreadOnly },
  });
  return response.data;
}

export async function getUnreadCount(): Promise<UnreadCountResponse> {
  const response = await apiClient.get<UnreadCountResponse>("/notifications/unread/count");
  return response.data;
}

export async function markAsRead(notificationId: string): Promise<Notification> {
  const response = await apiClient.put<Notification>(`/notifications/${notificationId}/read`);
  return response.data;
}

export async function markAllAsRead(): Promise<{ message: string; count: number }> {
  const response = await apiClient.put("/notifications/read-all");
  return response.data;
}

export async function deleteNotification(notificationId: string): Promise<void> {
  await apiClient.delete(`/notifications/${notificationId}`);
}

// React Query hooks
export function useNotifications(params: { limit?: number; offset?: number; unreadOnly?: boolean } = {}) {
  return useQuery({
    queryKey: ["notifications", params],
    queryFn: () => getNotifications(params),
    refetchInterval: 30000, // Poll every 30 seconds
    staleTime: 10000, // Consider data fresh for 10 seconds
  });
}

export function useUnreadCount() {
  return useQuery({
    queryKey: ["notifications", "unread-count"],
    queryFn: () => getUnreadCount(),
    refetchInterval: 30000, // Poll every 30 seconds
    staleTime: 5000,
  });
}

export function useMarkAsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: markAsRead,
    onSuccess: () => {
      // Invalidate and refetch notifications and unread count
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

export function useMarkAllAsRead() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: markAllAsRead,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}

export function useDeleteNotification() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: deleteNotification,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["notifications"] });
    },
  });
}
