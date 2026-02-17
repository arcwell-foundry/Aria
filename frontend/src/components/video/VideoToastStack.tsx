import { useEffect, useRef, useCallback } from 'react';
import { VideoContentToast, type ToastItem } from './VideoContentToast';

interface VideoToastStackProps {
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
  onToastClick: (id: string) => void;
}

const MAX_VISIBLE = 3;
const AUTO_DISMISS_MS = 8000;

export function VideoToastStack({ toasts, onDismiss, onToastClick }: VideoToastStackProps) {
  const timersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const scheduleAutoDismiss = useCallback(
    (id: string) => {
      if (timersRef.current.has(id)) return;
      const timer = setTimeout(() => {
        timersRef.current.delete(id);
        onDismiss(id);
      }, AUTO_DISMISS_MS);
      timersRef.current.set(id, timer);
    },
    [onDismiss],
  );

  useEffect(() => {
    for (const toast of toasts) {
      scheduleAutoDismiss(toast.id);
    }
  }, [toasts, scheduleAutoDismiss]);

  useEffect(() => {
    const timers = timersRef.current;
    return () => {
      for (const timer of timers.values()) clearTimeout(timer);
      timers.clear();
    };
  }, []);

  const visible = toasts.slice(-MAX_VISIBLE);

  if (visible.length === 0) return null;

  return (
    <div className="absolute bottom-4 right-4 z-20 flex flex-col gap-2">
      {visible.map((toast) => (
        <VideoContentToast
          key={toast.id}
          toast={toast}
          onDismiss={onDismiss}
          onClick={onToastClick}
        />
      ))}
    </div>
  );
}
