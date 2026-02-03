import { useState, useCallback } from "react";
import {
  useConversations,
  useUpdateConversationTitle,
  useDeleteConversation,
} from "@/hooks/useChat";
import type { Conversation } from "@/api/chat";

interface ConversationSidebarProps {
  currentConversationId: string | null;
  onNewConversation: () => void;
  onConversationSelect: (conversationId: string) => void;
  isOpen: boolean;
  onClose: () => void;
}

export function ConversationSidebar({
  currentConversationId,
  onNewConversation,
  onConversationSelect,
  isOpen,
  onClose,
}: ConversationSidebarProps) {
  const { data: conversations, isLoading } = useConversations();
  const updateTitle = useUpdateConversationTitle();
  const deleteConversation = useDeleteConversation();

  const [searchQuery, setSearchQuery] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editTitle, setEditTitle] = useState("");

  const filteredConversations = conversations?.filter((conv) => {
    if (!searchQuery) return true;
    const title = conv.title || conv.last_message_preview || "New Conversation";
    return title.toLowerCase().includes(searchQuery.toLowerCase());
  }) || [];

  const handleStartEdit = useCallback((conv: Conversation) => {
    setEditingId(conv.id);
    setEditTitle(conv.title || "");
  }, []);

  const handleSaveTitle = useCallback(
    (conversationId: string) => {
      if (editTitle.trim()) {
        updateTitle.mutate({ conversationId, title: editTitle.trim() });
      }
      setEditingId(null);
      setEditTitle("");
    },
    [editTitle, updateTitle]
  );

  const handleCancelEdit = useCallback(() => {
    setEditingId(null);
    setEditTitle("");
  }, []);

  const handleDelete = useCallback(
    (conversationId: string, e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();

      if (window.confirm("Delete this conversation?")) {
        deleteConversation.mutate(conversationId, {
          onSuccess: () => {
            if (currentConversationId === conversationId) {
              onNewConversation();
            }
          },
        });
      }
    },
    [deleteConversation, currentConversationId, onNewConversation]
  );

  const formatTime = (dateStr: string | null) => {
    if (!dateStr) return "";
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffHours = diffMs / (1000 * 60 * 60);

    if (diffHours < 1) {
      return "Just now";
    } else if (diffHours < 24) {
      return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } else if (diffHours < 24 * 7) {
      return date.toLocaleDateString([], { weekday: "short" });
    } else {
      return date.toLocaleDateString([], { month: "short", day: "numeric" });
    }
  };

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/50 z-40 lg:hidden"
          onClick={onClose}
        />
      )}

      {/* Sidebar */}
      <aside
        className={`fixed top-0 left-0 z-50 h-full w-80 bg-slate-800/95 backdrop-blur-xl border-r border-white/5 transform transition-transform duration-300 ease-out ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        } lg:translate-x-0 lg:static lg:z-0 flex flex-col`}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-4 border-b border-white/5">
          <h2 className="text-sm font-semibold text-white uppercase tracking-wider">
            Conversations
          </h2>
          <button
            onClick={onClose}
            className="lg:hidden text-slate-400 hover:text-white transition-colors p-1"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Search */}
        <div className="p-4 border-b border-white/5">
          <div className="relative">
            <svg
              className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
              />
            </svg>
            <input
              type="text"
              placeholder="Search conversations..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full bg-slate-900/50 text-white placeholder-slate-400 rounded-lg pl-10 pr-4 py-2 text-sm border border-white/10 focus:border-primary-500/50 focus:outline-none focus:ring-1 focus:ring-primary-500/50 transition-all"
            />
          </div>
        </div>

        {/* New conversation button */}
        <div className="p-4">
          <button
            onClick={() => {
              onNewConversation();
              onClose();
            }}
            className="w-full px-4 py-3 bg-gradient-to-r from-primary-600 to-primary-700 hover:from-primary-500 hover:to-primary-600 text-white rounded-xl font-medium transition-all duration-200 flex items-center justify-center gap-2 shadow-lg shadow-primary-500/20 hover:shadow-primary-500/30 active:scale-[0.98]"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            New Conversation
          </button>
        </div>

        {/* Conversations list */}
        <div className="flex-1 overflow-y-auto px-2 pb-4">
          {isLoading ? (
            <div className="flex items-center justify-center h-32">
              <div className="w-6 h-6 border-2 border-primary-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : filteredConversations.length === 0 ? (
            <div className="text-center py-8">
              <p className="text-sm text-slate-400">
                {searchQuery ? "No conversations found" : "No conversations yet"}
              </p>
            </div>
          ) : (
            <div className="space-y-1">
              {filteredConversations.map((conv) => (
                <div
                  key={conv.id}
                  className={`group relative rounded-xl transition-all duration-200 ${
                    currentConversationId === conv.id
                      ? "bg-primary-600/20 border border-primary-500/30"
                      : "hover:bg-slate-700/50 border border-transparent"
                  }`}
                >
                  {editingId === conv.id ? (
                    // Edit mode
                    <div className="px-3 py-3">
                      <input
                        type="text"
                        value={editTitle}
                        onChange={(e) => setEditTitle(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === "Enter") handleSaveTitle(conv.id);
                          if (e.key === "Escape") handleCancelEdit();
                        }}
                        autoFocus
                        className="w-full bg-slate-900 text-white text-sm rounded-lg px-3 py-2 border border-primary-500/50 focus:outline-none focus:ring-1 focus:ring-primary-500/50"
                        onBlur={() => handleSaveTitle(conv.id)}
                      />
                    </div>
                  ) : (
                    // Display mode
                    <button
                      onClick={() => {
                        onConversationSelect(conv.id);
                        onClose();
                      }}
                      className="w-full px-3 py-3 text-left"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex-1 min-w-0">
                          <p className="text-sm font-medium text-white truncate">
                            {conv.title || conv.last_message_preview || "New Conversation"}
                          </p>
                          {(conv.message_count ?? 0) > 0 && (
                            <p className="text-xs text-slate-400 mt-0.5 truncate">
                              {conv.last_message_preview || "No messages"}
                            </p>
                          )}
                        </div>
                        <span className="text-xs text-slate-500 flex-shrink-0">
                          {formatTime(conv.updated_at)}
                        </span>
                      </div>
                    </button>
                  )}

                  {/* Action buttons */}
                  {editingId !== conv.id && (
                    <div className="absolute right-2 top-1/2 -translate-y-1/2 flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          handleStartEdit(conv);
                        }}
                        className="p-1.5 text-slate-400 hover:text-white hover:bg-slate-600/50 rounded-lg transition-colors"
                        title="Rename"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"
                          />
                        </svg>
                      </button>
                      <button
                        onClick={(e) => handleDelete(conv.id, e)}
                        className="p-1.5 text-slate-400 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
                        title="Delete"
                      >
                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            strokeWidth={2}
                            d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
                          />
                        </svg>
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
