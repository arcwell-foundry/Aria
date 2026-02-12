/**
 * SortableHeader - Table column header with sort controls
 *
 * Follows ARIA Design System v1.0:
 * - Uses CSS variables for theming
 * - Shows ChevronUp/ChevronDown icons
 * - Active column has full opacity, inactive has 0.3 opacity
 *
 * @example
 * <SortableHeader
 *   label="Company"
 *   sortKey="company"
 *   currentSort="company"
 *   currentDirection="asc"
 *   onSort={(key, dir) => handleSort(key, dir)}
 * />
 */

import { ChevronUp, ChevronDown } from 'lucide-react';

export type SortDirection = 'asc' | 'desc' | null;

export interface SortableHeaderProps {
  /** Display label for the header */
  label: string;
  /** Unique key for this column */
  sortKey: string;
  /** Currently active sort key */
  currentSort: string | null;
  /** Current sort direction */
  currentDirection: SortDirection;
  /** Callback when sort changes */
  onSort: (key: string, direction: 'asc' | 'desc') => void;
  /** Additional CSS classes */
  className?: string;
}

export function SortableHeader({
  label,
  sortKey,
  currentSort,
  currentDirection,
  onSort,
  className = '',
}: SortableHeaderProps) {
  const isActive = currentSort === sortKey;
  const isAsc = isActive && currentDirection === 'asc';
  const isDesc = isActive && currentDirection === 'desc';

  const handleClick = () => {
    if (!isActive || currentDirection === null) {
      // First click: ascending
      onSort(sortKey, 'asc');
    } else if (currentDirection === 'asc') {
      // Second click: descending
      onSort(sortKey, 'desc');
    } else {
      // Third click: back to ascending (cycle)
      onSort(sortKey, 'asc');
    }
  };

  return (
    <button
      onClick={handleClick}
      className={`
        inline-flex items-center gap-1.5
        text-xs font-medium uppercase tracking-wider
        transition-colors duration-150
        hover:text-[var(--text-primary)]
        cursor-pointer select-none
        ${className}
      `.trim()}
      style={{
        color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
      }}
    >
      <span>{label}</span>
      <span className="inline-flex flex-col">
        <ChevronUp
          className="w-3 h-3 -mb-1"
          style={{ opacity: isAsc ? 1 : 0.3 }}
        />
        <ChevronDown
          className="w-3 h-3 -mt-1"
          style={{ opacity: isDesc ? 1 : 0.3 }}
        />
      </span>
    </button>
  );
}
