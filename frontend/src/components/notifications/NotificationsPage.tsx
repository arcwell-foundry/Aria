import { useNavigate } from "react-router-dom";
import { useNotifications, useDeleteNotification, useMarkAsRead } from "@/api/notifications";
import { Trash2, Check } from "lucide-react";

// Shared time formatter and icons from NotificationBell
function timeAgo(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days === 1) return "Yesterday";
  if (days < 7) return `${days}d ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

const NotificationIcons: Record<string, React.ReactNode> = {
  briefing_ready: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M14.5 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V7.5L14.5 2z" />
      <path d="M14 2v6h6" />
    </svg>
  ),
  signal_detected: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M12 20V10" />
      <path d="M18 20V4" />
      <path d="M6 20v-4" />
    </svg>
  ),
  task_due: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M9 11l3 3L22 4" />
      <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
    </svg>
  ),
  meeting_brief_ready: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M17 21v-2a2 2 0 00-2-2H5a2 2 0 00-2 2v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M23 21v-2a2 2 0 00-2-2-2 2 0 01-2-2" />
      <path d="M16 3.13a4 4 0 010 7.75" />
    </svg>
  ),
  draft_ready: (
    <svg className="w-6 h-6" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
      <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z" />
      <polyline points="22,6 12 13 2,6" />
    </svg>
  ),
};

const TypeColors: Record<string, string> = {
  briefing_ready: "text-blue-400 bg-blue-400/10",
  signal_detected: "text-amber-400 bg-amber-400/10",
  task_due: "text-rose-400 bg-rose-400/10",
  meeting_brief_ready: "text-emerald-400 bg-emerald-400/10",
  draft_ready: "text-violet-400 bg-violet-400/10",
};

export function NotificationsPageContent() {
  const navigate = useNavigate();
  const { data: notificationsData, isLoading } = useNotifications({ limit: 100 });
  const deleteNotification = useDeleteNotification();
  const markAsRead = useMarkAsRead();

  const notifications = notificationsData?.notifications ?? [];

  const handleNotificationClick = async (notification: any) => {
    if (!notification.read_at) {
      await markAsRead.mutateAsync(notification.id);
    }
    if (notification.link) {
      navigate(notification.link);
    }
  };

  const handleDelete = async (e: React.MouseEvent, notificationId: string) => {
    e.stopPropagation();
    if (confirm("Delete this notification?")) {
      await deleteNotification.mutateAsync(notificationId);
    }
  };

  const handleMarkRead = async (e: React.MouseEvent, notification: any) => {
    e.stopPropagation();
    if (!notification.read_at) {
      await markAsRead.mutateAsync(notification.id);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="text-center">
          <div className="inline-block w-8 h-8 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
          <p className="mt-4 text-slate-400">Loading notifications...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-white">Notifications</h1>
        <p className="mt-2 text-slate-400">
          {notificationsData?.unread_count ?? 0} unread notification
          {notificationsData?.unread_count !== 1 ? "s" : ""}
        </p>
      </div>

      {/* Notifications list */}
      {notifications.length === 0 ? (
        <div className="text-center py-16">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-full bg-slate-800 mb-4">
            <svg className="w-8 h-8 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
            </svg>
          </div>
          <h3 className="text-lg font-semibold text-white">No notifications yet</h3>
          <p className="mt-2 text-slate-400">
            We'll notify you when something important happens
          </p>
        </div>
      ) : (
        <div className="space-y-2">
          {notifications.map((notification) => {
            const isUnread = !notification.read_at;
            return (
              <div
                key={notification.id}
                className={`group relative p-4 rounded-xl border transition-all ${
                  isUnread
                    ? "bg-slate-800 border-slate-700 shadow-sm"
                    : "bg-slate-800/50 border-slate-700/50"
                }`}
              >
                <div
                  onClick={() => notification.link && handleNotificationClick(notification)}
                  className={`flex gap-4 ${notification.link ? "cursor-pointer" : ""}`}
                >
                  {/* Type icon */}
                  <div
                    className={`flex-shrink-0 flex items-center justify-center w-12 h-12 rounded-xl ${
                      TypeColors[notification.type] || "text-slate-400 bg-slate-700"
                    }`}
                  >
                    {NotificationIcons[notification.type] || NotificationIcons.briefing_ready}
                  </div>

                  {/* Content */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex-1">
                        <p
                          className={`text-sm font-medium ${
                            isUnread ? "text-white" : "text-slate-300"
                          }`}
                        >
                          {notification.title}
                        </p>
                        {notification.message && (
                          <p className="text-sm text-slate-400 mt-1">{notification.message}</p>
                        )}
                        <p className="text-xs text-slate-500 mt-2">{timeAgo(notification.created_at)}</p>
                      </div>

                      {/* Actions */}
                      <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                        {isUnread && (
                          <button
                            onClick={(e) => handleMarkRead(e, notification)}
                            className="p-2 text-slate-400 hover:text-primary-400 hover:bg-slate-700 rounded-lg transition-colors"
                            title="Mark as read"
                          >
                            <Check className="w-4 h-4" />
                          </button>
                        )}
                        <button
                          onClick={(e) => handleDelete(e, notification.id)}
                          className="p-2 text-slate-400 hover:text-rose-400 hover:bg-slate-700 rounded-lg transition-colors"
                          title="Delete"
                        >
                          <Trash2 className="w-4 h-4" />
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                {/* Unread indicator */}
                {isUnread && (
                  <div className="absolute left-0 top-4 bottom-4 w-1 bg-primary-500 rounded-r-full" />
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
