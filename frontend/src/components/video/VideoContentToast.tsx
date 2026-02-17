import { useEffect, useRef } from 'react';
import { X, Building2, Swords, BarChart3, BookOpen, Mail } from 'lucide-react';

const CONTENT_ICONS: Record<string, typeof Building2> = {
  lead_card: Building2,
  battle_card: Swords,
  pipeline_chart: BarChart3,
  research_results: BookOpen,
  email_draft: Mail,
};

export interface ToastItem {
  id: string;
  contentType: string;
  title: string;
}

interface VideoContentToastProps {
  toast: ToastItem;
  onDismiss: (id: string) => void;
  onClick: (id: string) => void;
}

export function VideoContentToast({ toast, onDismiss, onClick }: VideoContentToastProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    requestAnimationFrame(() => {
      if (ref.current) {
        ref.current.style.transform = 'translateX(0)';
        ref.current.style.opacity = '1';
      }
    });
  }, []);

  const Icon = CONTENT_ICONS[toast.contentType] || Building2;

  return (
    <div
      ref={ref}
      className="flex items-center gap-2 px-3 py-2 rounded-lg cursor-pointer backdrop-blur-sm transition-all duration-200 ease-out"
      style={{
        backgroundColor: 'rgba(15,17,23,0.85)',
        border: '1px solid rgba(46,102,255,0.2)',
        transform: 'translateX(100%)',
        opacity: '0',
      }}
      onClick={() => onClick(toast.id)}
    >
      <Icon className="w-3.5 h-3.5 shrink-0" style={{ color: 'var(--accent)' }} />
      <span className="text-xs text-white/90 truncate max-w-[180px]">
        {toast.title}
      </span>
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onDismiss(toast.id);
        }}
        className="shrink-0 p-0.5 rounded hover:bg-white/10 transition-colors"
      >
        <X className="w-3 h-3 text-white/50" />
      </button>
    </div>
  );
}
