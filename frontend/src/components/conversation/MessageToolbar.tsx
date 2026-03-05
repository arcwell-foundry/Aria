import { useState, useCallback, useRef, useEffect } from 'react';
import { Copy, ThumbsUp, ThumbsDown, MoreHorizontal, Check, BookmarkPlus, ListTodo, Share2 } from 'lucide-react';

interface MessageToolbarProps {
  messageContent: string;
  messageId: string;
  inline?: boolean; // For mobile: show below message instead of hover
}

interface FeedbackState {
  [key: string]: 'positive' | 'negative' | null;
}

// In-memory feedback store (could be replaced with API persistence)
const feedbackStore: FeedbackState = {};

export function MessageToolbar({ messageContent, messageId, inline = false }: MessageToolbarProps) {
  const [copied, setCopied] = useState(false);
  const [feedback, setFeedback] = useState<'positive' | 'negative' | null>(
    feedbackStore[messageId] || null
  );
  const [showMoreMenu, setShowMoreMenu] = useState(false);
  const moreMenuRef = useRef<HTMLDivElement>(null);

  // Close more menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (moreMenuRef.current && !moreMenuRef.current.contains(event.target as Node)) {
        setShowMoreMenu(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(messageContent);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch (err) {
      console.error('Failed to copy message:', err);
    }
  }, [messageContent]);

  const handleThumbsUp = useCallback(() => {
    const newFeedback = feedback === 'positive' ? null : 'positive';
    setFeedback(newFeedback);
    feedbackStore[messageId] = newFeedback;
    // TODO: POST to feedback endpoint when available
    console.log('[MessageToolbar] Positive feedback:', { messageId, feedback: newFeedback });
  }, [feedback, messageId]);

  const handleThumbsDown = useCallback(() => {
    const newFeedback = feedback === 'negative' ? null : 'negative';
    setFeedback(newFeedback);
    feedbackStore[messageId] = newFeedback;
    // TODO: POST to feedback endpoint when available
    console.log('[MessageToolbar] Negative feedback:', { messageId, feedback: newFeedback });
  }, [feedback, messageId]);

  const handleMoreAction = useCallback((action: string) => {
    console.log('[MessageToolbar] More action:', { messageId, action });
    setShowMoreMenu(false);
  }, [messageId]);

  // Inline mode for mobile - shows below message, always visible
  if (inline) {
    return (
      <div className="flex items-center justify-end gap-0.5 mt-2">
        <div className="flex items-center gap-0.5 bg-[#1E2436] border border-[#2A2F42] rounded-lg shadow-lg">
          {/* Copy button */}
          <button
            onClick={handleCopy}
            className="relative p-1.5 text-[#666] hover:text-white transition-colors"
            title="Copy message"
          >
            {copied ? (
              <Check className="w-4 h-4 text-green-400" />
            ) : (
              <Copy className="w-4 h-4" />
            )}
          </button>

          {/* Thumbs up */}
          <button
            onClick={handleThumbsUp}
            className={`p-1.5 transition-colors ${
              feedback === 'positive'
                ? 'text-green-400'
                : 'text-[#666] hover:text-white'
            }`}
            title="Good response"
          >
            <ThumbsUp className={`w-4 h-4 ${feedback === 'positive' ? 'fill-current' : ''}`} />
          </button>

          {/* Thumbs down */}
          <button
            onClick={handleThumbsDown}
            className={`p-1.5 transition-colors ${
              feedback === 'negative'
                ? 'text-red-400'
                : 'text-[#666] hover:text-white'
            }`}
            title="Bad response"
          >
            <ThumbsDown className={`w-4 h-4 ${feedback === 'negative' ? 'fill-current' : ''}`} />
          </button>

          {/* More actions */}
          <div className="relative" ref={moreMenuRef}>
            <button
              onClick={() => setShowMoreMenu(!showMoreMenu)}
              className={`p-1.5 transition-colors ${
                showMoreMenu ? 'text-white' : 'text-[#666] hover:text-white'
              }`}
              title="More actions"
            >
              <MoreHorizontal className="w-4 h-4" />
            </button>

            {/* Dropdown menu */}
            {showMoreMenu && (
              <div className="absolute top-full right-0 mt-1 bg-[#1E2436] border border-[#2A2F42] rounded-lg shadow-lg py-1 min-w-[160px] z-30">
                <button
                  onClick={() => handleMoreAction('add_to_briefing')}
                  className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-[#666] hover:text-white hover:bg-[#2A2F42] transition-colors"
                >
                  <BookmarkPlus className="w-4 h-4" />
                  Add to briefing
                </button>
                <button
                  onClick={() => handleMoreAction('create_task')}
                  className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-[#666] hover:text-white hover:bg-[#2A2F42] transition-colors"
                >
                  <ListTodo className="w-4 h-4" />
                  Create task from this
                </button>
                <button
                  onClick={() => handleMoreAction('share')}
                  className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-[#666] hover:text-white hover:bg-[#2A2F42] transition-colors"
                >
                  <Share2 className="w-4 h-4" />
                  Share
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  // Hover mode for desktop - appears on hover, top-right corner
  return (
    <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity duration-150 z-20">
      <div className="flex items-center gap-0.5 bg-[#1E2436] border border-[#2A2F42] rounded-lg shadow-lg">
        {/* Copy button */}
        <button
          onClick={handleCopy}
          className="relative p-1.5 text-[#666] hover:text-white transition-colors"
          title="Copy message"
        >
          {copied ? (
            <Check className="w-4 h-4 text-green-400" />
          ) : (
            <Copy className="w-4 h-4" />
          )}
          {/* Copied tooltip */}
          {copied && (
            <span className="absolute -bottom-7 left-1/2 -translate-x-1/2 text-[10px] text-white bg-[#1E2436] px-1.5 py-0.5 rounded whitespace-nowrap">
              Copied!
            </span>
          )}
        </button>

        {/* Thumbs up */}
        <button
          onClick={handleThumbsUp}
          className={`p-1.5 transition-colors ${
            feedback === 'positive'
              ? 'text-green-400'
              : 'text-[#666] hover:text-white'
          }`}
          title="Good response"
        >
          <ThumbsUp className={`w-4 h-4 ${feedback === 'positive' ? 'fill-current' : ''}`} />
        </button>

        {/* Thumbs down */}
        <button
          onClick={handleThumbsDown}
          className={`p-1.5 transition-colors ${
            feedback === 'negative'
              ? 'text-red-400'
              : 'text-[#666] hover:text-white'
          }`}
          title="Bad response"
        >
          <ThumbsDown className={`w-4 h-4 ${feedback === 'negative' ? 'fill-current' : ''}`} />
        </button>

        {/* More actions */}
        <div className="relative" ref={moreMenuRef}>
          <button
            onClick={() => setShowMoreMenu(!showMoreMenu)}
            className={`p-1.5 transition-colors ${
              showMoreMenu ? 'text-white' : 'text-[#666] hover:text-white'
            }`}
            title="More actions"
          >
            <MoreHorizontal className="w-4 h-4" />
          </button>

          {/* Dropdown menu */}
          {showMoreMenu && (
            <div className="absolute top-full right-0 mt-1 bg-[#1E2436] border border-[#2A2F42] rounded-lg shadow-lg py-1 min-w-[160px]">
              <button
                onClick={() => handleMoreAction('add_to_briefing')}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-[#666] hover:text-white hover:bg-[#2A2F42] transition-colors"
              >
                <BookmarkPlus className="w-4 h-4" />
                Add to briefing
              </button>
              <button
                onClick={() => handleMoreAction('create_task')}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-[#666] hover:text-white hover:bg-[#2A2F42] transition-colors"
              >
                <ListTodo className="w-4 h-4" />
                Create task from this
              </button>
              <button
                onClick={() => handleMoreAction('share')}
                className="w-full flex items-center gap-2 px-3 py-1.5 text-sm text-[#666] hover:text-white hover:bg-[#2A2F42] transition-colors"
              >
                <Share2 className="w-4 h-4" />
                Share
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
