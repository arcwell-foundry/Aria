/**
 * SkeletonLoader - Loading state placeholders following ARIA Design System v1.0
 *
 * Design System Colors:
 * - Skeleton base: bg-border
 * - Dark surfaces: bg-elevated, border-border
 * - Animation: animate-pulse (subtle)
 *
 * @example
 * <SkeletonLoader variant="card" count={3} />
 * <SkeletonLoader variant="list" count={5} />
 * <LeadsSkeleton />
 */

export interface SkeletonLoaderProps {
  /** Number of skeleton items to render */
  count?: number;
  /** CSS class name for custom styling */
  className?: string;
}

// Base skeleton element with ARIA Design System colors
const SkeletonBase = ({ className }: { className?: string }) => (
  <div className={`bg-border animate-pulse rounded ${className || ''}`} />
);

/**
 * Card skeleton variant - For card-based layouts (leads, goals, etc.)
 * Matches LeadCard and GoalCard structure
 */
export function CardSkeleton({ className }: { className?: string }) {
  return (
    <div
      className={`bg-elevated border border-border rounded-xl p-5 overflow-hidden ${className || ''}`}
    >
      {/* Header section with icon/avatar and title */}
      <div className="flex items-start gap-4 mb-4">
        <SkeletonBase className="w-12 h-12 rounded-xl flex-shrink-0" />
        <div className="flex-1 min-w-0 space-y-2">
          <SkeletonBase className="h-5 w-3/4" />
          <SkeletonBase className="h-4 w-1/2" />
        </div>
      </div>

      {/* Badge/status area */}
      <div className="mb-4">
        <SkeletonBase className="h-6 w-20 rounded-full" />
      </div>

      {/* Meta info grid */}
      <div className="grid grid-cols-2 gap-3">
        <SkeletonBase className="h-4" />
        <SkeletonBase className="h-4" />
      </div>

      {/* Optional tags section */}
      <div className="flex gap-2 mt-4 pt-4 border-t border-border/50">
        <SkeletonBase className="h-5 w-16 rounded-full" />
        <SkeletonBase className="h-5 w-20 rounded-full" />
      </div>
    </div>
  );
}

/**
 * List skeleton variant - For list items with avatar/content structure
 * Matches contacts/notifications list patterns
 */
export function ListSkeleton({ className }: { className?: string }) {
  return (
    <div
      className={`bg-elevated border border-border rounded-xl p-4 ${className || ''}`}
    >
      <div className="flex items-center gap-3">
        {/* Avatar */}
        <SkeletonBase className="w-10 h-10 rounded-full flex-shrink-0" />

        {/* Content */}
        <div className="flex-1 min-w-0 space-y-2">
          <SkeletonBase className="h-4 w-48" />
          <SkeletonBase className="h-3 w-32" />
        </div>

        {/* Action/status */}
        <SkeletonBase className="w-8 h-8 rounded-lg flex-shrink-0" />
      </div>
    </div>
  );
}

/**
 * Table skeleton variant - For table rows
 * Matches LeadTableRow structure
 */
export function TableSkeleton({
  columns = 8,
  className,
}: {
  columns?: number;
  className?: string;
}) {
  return (
    <tr className={`border-b border-border/30 ${className || ''}`}>
      {/* Checkbox column */}
      <td className="px-4 py-4 w-12">
        <SkeletonBase className="w-5 h-5 rounded" />
      </td>

      {/* Data columns */}
      {Array.from({ length: columns - 2 }).map((_, i) => (
        <td key={i} className="px-4 py-4">
          <SkeletonBase className="h-5 w-full max-w-[160px]" />
        </td>
      ))}

      {/* Actions column */}
      <td className="px-4 py-4 w-20">
        <div className="flex items-center gap-1">
          <SkeletonBase className="w-8 h-8 rounded-lg" />
          <SkeletonBase className="w-8 h-8 rounded-lg" />
        </div>
      </td>
    </tr>
  );
}

/**
 * Text skeleton variant - For simple text lines
 * Useful for paragraphs, descriptions, loading text content
 */
export function TextSkeleton({
  lines = 3,
  className,
}: {
  lines?: number;
  className?: string;
}) {
  return (
    <div className={`space-y-2 ${className || ''}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <SkeletonBase
          key={i}
          className={`h-4 ${i === lines - 1 ? 'w-2/3' : 'w-full'}`}
        />
      ))}
    </div>
  );
}

/**
 * Generic SkeletonLoader component with variant selection
 */
export function SkeletonLoader({
  variant = "text",
  count = 1,
  className,
}: SkeletonLoaderProps & {
  variant?: "card" | "list" | "table" | "text";
}) {
  const renderSkeleton = () => {
    switch (variant) {
      case "card":
        return <CardSkeleton className={className} />;
      case "list":
        return <ListSkeleton className={className} />;
      case "table":
        return <TableSkeleton className={className} />;
      case "text":
        return <TextSkeleton className={className} />;
      default:
        return <SkeletonBase className={className} />;
    }
  };

  return (
    <>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i}>{renderSkeleton()}</div>
      ))}
    </>
  );
}

/**
 * ============================================================================
 * PRESET SKELETON COMPONENTS
 * ============================================================================
 * Domain-specific skeleton loaders for common ARIA use cases
 */

/**
 * LeadsSkeleton - For leads page loading state
 * Supports both card and table view modes
 */
export function LeadsSkeleton({
  viewMode = "card",
  count = 6,
}: {
  viewMode?: "card" | "table";
  count?: number;
}) {
  if (viewMode === "table") {
    return (
      <div className="bg-elevated border border-border rounded-xl overflow-hidden">
        <table className="w-full">
          <thead>
            <tr className="bg-elevated/60 text-left border-b border-border">
              <th className="w-12 px-4 py-3" />
              <th className="px-4 py-3 text-sm font-medium text-secondary">Company</th>
              <th className="px-4 py-3 text-sm font-medium text-secondary">Health</th>
              <th className="px-4 py-3 text-sm font-medium text-secondary">Stage</th>
              <th className="px-4 py-3 text-sm font-medium text-secondary">Status</th>
              <th className="px-4 py-3 text-sm font-medium text-secondary">Value</th>
              <th className="px-4 py-3 text-sm font-medium text-secondary">Last Activity</th>
              <th className="px-4 py-3 text-sm font-medium text-secondary">Actions</th>
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: count }).map((_, i) => (
              <TableSkeleton key={i} columns={8} />
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
      {Array.from({ length: count }).map((_, i) => (
        <CardSkeleton key={i} />
      ))}
    </div>
  );
}

/**
 * GoalsSkeleton - For goals page loading state
 * Matches GoalCard structure with progress ring placeholder
 */
export function GoalsSkeleton({ count = 6 }: { count?: number }) {
  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="bg-elevated border border-border rounded-xl p-5"
        >
          <div className="flex items-start gap-4">
            {/* Progress ring placeholder */}
            <SkeletonBase className="w-14 h-14 rounded-full flex-shrink-0" />

            {/* Content */}
            <div className="flex-1 min-w-0 space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div className="flex-1 space-y-2">
                  <SkeletonBase className="h-5 w-3/4" />
                  <SkeletonBase className="h-4 w-full" />
                  <SkeletonBase className="h-4 w-2/3" />
                </div>
                <SkeletonBase className="w-8 h-8 rounded-lg flex-shrink-0" />
              </div>

              {/* Badges */}
              <div className="flex items-center gap-2">
                <SkeletonBase className="h-5 w-16 rounded-full" />
                <SkeletonBase className="h-5 w-16 rounded-full" />
              </div>

              {/* Agent count */}
              <SkeletonBase className="h-3 w-32" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * BriefingSkeleton - For meeting briefing page loading state
 * Matches briefing sections structure with greeting, summary, and section cards
 */
export function BriefingSkeleton() {
  return (
    <div className="space-y-6">
      {/* Greeting section */}
      <div className="space-y-3">
        <SkeletonBase className="h-10 w-64 rounded-lg" />
        <SkeletonBase className="h-5 w-96 rounded" />
      </div>

      {/* Executive summary card */}
      <div className="bg-elevated border border-border rounded-xl p-6">
        <TextSkeleton lines={4} />
      </div>

      {/* Section cards (Leads, Signals, Tasks, Calendar) */}
      {Array.from({ length: 4 }).map((_, i) => (
        <div
          key={i}
          className="bg-elevated border border-border rounded-xl overflow-hidden"
        >
          {/* Section header */}
          <div className="p-4 flex items-center justify-between border-b border-border/50">
            <div className="flex items-center gap-3">
              <SkeletonBase className="w-5 h-5 rounded" />
              <SkeletonBase className="h-5 w-32 rounded" />
              <SkeletonBase className="h-5 w-8 rounded-full" />
            </div>
            <SkeletonBase className="w-5 h-5 rounded" />
          </div>

          {/* Section content */}
          <div className="p-4 space-y-3">
            <SkeletonBase className="h-16 rounded-lg w-full" />
            <SkeletonBase className="h-16 rounded-lg w-full" />
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * LeadsTableSkeleton - Dedicated table skeleton for leads
 * Wrapper around LeadsSkeleton with table mode
 */
export function LeadsTableSkeleton({ count = 5 }: { count?: number }) {
  return <LeadsSkeleton viewMode="table" count={count} />;
}

/**
 * ContactsListSkeleton - For contacts/CRM list loading state
 * Uses list variant for contact items
 */
export function ContactsListSkeleton({ count = 8 }: { count?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }).map((_, i) => (
        <ListSkeleton key={i} />
      ))}
    </div>
  );
}

/**
 * ConversationSkeleton - For chat page loading state
 * Renders alternating left/right message bubbles matching ChatMessage layout
 */
export function ConversationSkeleton() {
  const bubbles = [
    { isUser: false, lines: 3, width: "w-3/4" },
    { isUser: true, lines: 1, width: "w-2/5" },
    { isUser: false, lines: 2, width: "w-3/5" },
    { isUser: true, lines: 2, width: "w-1/2" },
    { isUser: false, lines: 4, width: "w-3/4" },
  ];

  return (
    <div className="space-y-6">
      {bubbles.map((bubble, i) => (
        <div
          key={i}
          className={`flex gap-4 ${bubble.isUser ? "flex-row-reverse" : "flex-row"}`}
        >
          {/* Avatar */}
          <SkeletonBase className="w-10 h-10 rounded-full flex-shrink-0" />

          {/* Message bubble */}
          <div
            className={`bg-elevated border border-border rounded-2xl px-5 py-4 space-y-2 ${bubble.width}`}
          >
            {Array.from({ length: bubble.lines }).map((_, j) => (
              <SkeletonBase
                key={j}
                className={`h-4 ${
                  j === bubble.lines - 1 && bubble.lines > 1 ? "w-2/3" : "w-full"
                }`}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

/**
 * TextSkeleton - Available as a named export for direct use
 * Useful for paragraph placeholders, descriptions, etc.
 */
