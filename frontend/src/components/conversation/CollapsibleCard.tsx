import { useState, useRef, useEffect, type ReactNode } from 'react';
import { ChevronDown, ChevronUp } from 'lucide-react';

interface CollapsibleCardProps {
  children: ReactNode;
  collapsible?: boolean;
  approvalSlot?: ReactNode;
}

const COLLAPSE_THRESHOLD = 200;

export function CollapsibleCard({
  children,
  collapsible = true,
  approvalSlot,
}: CollapsibleCardProps) {
  const contentRef = useRef<HTMLDivElement>(null);
  const [isOverflow, setIsOverflow] = useState(false);
  const [isExpanded, setIsExpanded] = useState(false);

  useEffect(() => {
    if (!collapsible || !contentRef.current) return;

    const height = contentRef.current.scrollHeight;
    setIsOverflow(height > COLLAPSE_THRESHOLD);
  }, [children, collapsible]);

  if (!collapsible) {
    return (
      <div>
        {children}
        {approvalSlot}
      </div>
    );
  }

  const shouldCollapse = isOverflow && !isExpanded;

  return (
    <div>
      <div className="relative">
        <div
          ref={contentRef}
          className={
            shouldCollapse
              ? 'max-h-[200px] overflow-hidden'
              : undefined
          }
        >
          {children}
        </div>

        {shouldCollapse && (
          <div className="absolute bottom-0 left-0 right-0 h-16 bg-gradient-to-t from-[var(--bg-primary)] to-transparent pointer-events-none" />
        )}
      </div>

      {isOverflow && (
        <button
          type="button"
          onClick={() => setIsExpanded((prev) => !prev)}
          className="flex items-center gap-1 mt-1 text-xs text-accent hover:text-accent-hover transition-colors"
        >
          {isExpanded ? (
            <>
              <ChevronUp className="w-3.5 h-3.5" />
              Show less
            </>
          ) : (
            <>
              <ChevronDown className="w-3.5 h-3.5" />
              Show more
            </>
          )}
        </button>
      )}

      {approvalSlot}
    </div>
  );
}
