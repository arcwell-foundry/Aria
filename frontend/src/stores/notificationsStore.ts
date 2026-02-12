/**
 * Notifications Store - Toast and notification state management
 *
 * Manages:
 * - Toast notifications
 * - Action alerts
 * - System notifications
 */

import { create } from 'zustand';

export type NotificationType = 'info' | 'success' | 'warning' | 'error';
export type NotificationPosition = 'top-right' | 'top-left' | 'bottom-right' | 'bottom-left';

export interface Notification {
  id: string;
  type: NotificationType;
  title: string;
  message?: string;
  duration?: number; // ms, 0 = persistent
  timestamp: Date;
  action?: {
    label: string;
    onClick: () => void;
  };
}

export interface NotificationsState {
  // State
  notifications: Notification[];
  position: NotificationPosition;
  maxVisible: number;

  // Actions
  addNotification: (notification: Omit<Notification, 'id' | 'timestamp'>) => string;
  removeNotification: (id: string) => void;
  clearNotifications: () => void;
  setPosition: (position: NotificationPosition) => void;
}

// Auto-dismiss timer
const dismissTimers: Map<string, ReturnType<typeof setTimeout>> = new Map();

export const useNotificationsStore = create<NotificationsState>((set, get) => ({
  // Initial state
  notifications: [],
  position: 'top-right',
  maxVisible: 5,

  // Actions
  addNotification: (notification) => {
    const id = `notif-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
    const duration = notification.duration ?? 5000; // Default 5s

    set((state) => {
      const newNotifications = [
        ...state.notifications,
        { ...notification, id, timestamp: new Date() },
      ].slice(-state.maxVisible);

      return { notifications: newNotifications };
    });

    // Auto-dismiss if duration > 0
    if (duration > 0) {
      const timer = setTimeout(() => {
        get().removeNotification(id);
        dismissTimers.delete(id);
      }, duration);
      dismissTimers.set(id, timer);
    }

    return id;
  },

  removeNotification: (id) => {
    // Clear any pending dismiss timer
    const timer = dismissTimers.get(id);
    if (timer) {
      clearTimeout(timer);
      dismissTimers.delete(id);
    }

    set((state) => ({
      notifications: state.notifications.filter((n) => n.id !== id),
    }));
  },

  clearNotifications: () => {
    // Clear all timers
    dismissTimers.forEach((timer) => clearTimeout(timer));
    dismissTimers.clear();
    set({ notifications: [] });
  },

  setPosition: (position) => set({ position }),
}));
