import { useState, useRef, useEffect, type ReactNode } from 'react';
import { ChevronRight } from 'lucide-react';

interface BriefingSectionProps {
  title: string;
  count: number;
  defaultExpanded: boolean;
  icon?: ReactNode;
  children: ReactNode;
}

export function BriefingSection({
  title,
  count,
  defaultExpanded,
  icon,
  children,
}: BriefingSectionProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const contentRef = useRef<HTMLDivElement>(null);
  const [contentHeight, setContentHeight] = useState<number | undefined>(undefined);

  // Measure content height only when expanding (cache from last expanded state)
  useEffect(() => {
    if (isExpanded && contentRef.current) {
      setContentHeight(contentRef.current.scrollHeight);
    }
  }, [children, isExpanded]);

  return (
    <div className="border-b border-[var(--border)]/40">
      <button
        type="button"
        onClick={() => setIsExpanded((v) => !v)}
        className="group flex w-full items-center gap-2.5 px-1 py-2.5 text-left transition-colors hover:bg-[var(--bg-subtle)]/40"
      >
        <ChevronRight
          size={12}
          className={`shrink-0 text-[var(--text-secondary)] transition-transform duration-200 ease-out ${
            isExpanded ? 'rotate-90' : ''
          }`}
        />
        {icon && (
          <span className="shrink-0 text-[var(--text-secondary)] group-hover:text-[var(--interactive)] transition-colors">
            {icon}
          </span>
        )}
        <span
          className="text-[14px] italic text-[var(--text-secondary)] group-hover:text-[var(--interactive)] transition-colors"
          style={{ fontFamily: "'Instrument Serif', Georgia, serif" }}
        >
          {title}
        </span>
        <span
          className="ml-auto inline-flex items-center justify-center rounded-full bg-[var(--bg-subtle)] px-2 py-0.5 text-[10px] text-[var(--text-secondary)] min-w-[22px]"
          style={{ fontFamily: "var(--font-mono)" }}
        >
          {count}
        </span>
      </button>

      <div
        className="overflow-hidden transition-all duration-200 ease-in-out"
        style={{
          maxHeight: isExpanded ? (contentHeight ?? 2000) : 0,
          opacity: isExpanded ? 1 : 0,
        }}
      >
        <div ref={contentRef} className="pb-3 pl-[22px]">
          {children}
        </div>
      </div>
    </div>
  );
}
