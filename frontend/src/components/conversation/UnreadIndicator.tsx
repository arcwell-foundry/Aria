import { useState, useEffect, useCallback, useRef } from 'react';
import { useLocation } from 'react-router-dom';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';

const ARIA_ROUTES = ['/', '/dialogue', '/briefing'];

export function UnreadIndicator() {
  const [unreadCount, setUnreadCount] = useState(0);
  const [firstUnreadId, setFirstUnreadId] = useState<string | null>(null);
  const isAwayRef = useRef(false);
  const location = useLocation();

  // Determine "away" state based on route and document visibility
  useEffect(() => {
    const onRoute = ARIA_ROUTES.includes(location.pathname);
    isAwayRef.current = !onRoute || document.hidden;

    const handleVisibility = () => {
      const onAriaRoute = ARIA_ROUTES.includes(location.pathname);
      isAwayRef.current = !onAriaRoute || document.hidden;
    };

    document.addEventListener('visibilitychange', handleVisibility);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibility);
    };
  }, [location.pathname]);

  // Listen for ARIA messages when away
  useEffect(() => {
    const handleMessage = (payload: unknown) => {
      if (!isAwayRef.current) return;

      const data = payload as { message_id?: string };
      setUnreadCount((prev) => {
        if (prev === 0 && data.message_id) {
          setFirstUnreadId(data.message_id);
        }
        return prev + 1;
      });
    };

    wsManager.on(WS_EVENTS.ARIA_MESSAGE, handleMessage);
    return () => {
      wsManager.off(WS_EVENTS.ARIA_MESSAGE, handleMessage as (payload: unknown) => void);
    };
  }, []);

  // Dismiss when user scrolls to the unread message via IntersectionObserver
  const observerRef = useRef<IntersectionObserver | null>(null);

  useEffect(() => {
    if (!firstUnreadId || unreadCount === 0) return;

    const el = document.querySelector(`[data-message-id="${firstUnreadId}"]`);
    if (!el) return;

    observerRef.current = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            setUnreadCount(0);
            setFirstUnreadId(null);
            observerRef.current?.disconnect();
          }
        }
      },
      { threshold: 0.5 },
    );

    observerRef.current.observe(el);

    return () => {
      observerRef.current?.disconnect();
    };
  }, [firstUnreadId, unreadCount]);

  const handleClick = useCallback(() => {
    if (!firstUnreadId) return;
    const el = document.querySelector(`[data-message-id="${firstUnreadId}"]`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [firstUnreadId]);

  if (unreadCount === 0) return null;

  return (
    <div className="sticky top-0 z-10 flex justify-center py-2">
      <button
        type="button"
        onClick={handleClick}
        className="px-4 py-1.5 rounded-full bg-accent text-white text-xs font-medium shadow-lg transition-transform hover:scale-105 active:scale-95"
      >
        {unreadCount} new message{unreadCount !== 1 ? 's' : ''} from ARIA
        {' \u2193'}
      </button>
    </div>
  );
}
