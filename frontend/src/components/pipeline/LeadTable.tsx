/**
 * LeadTable - Sortable table for lead pipeline with pagination
 *
 * Follows ARIA Design System v1.0:
 * - Uses CSS variables for theming
 * - Default sort: Health Score ASCENDING (worst first - needs attention)
 * - Warning indicator for >14 days stale leads
 * - 5 items per page with pagination
 * - Row click navigates to lead detail
 *
 * @example
 * <LeadTable
 *   leads={leads}
 *   onRowClick={(lead) => navigate(`/pipeline/leads/${lead.id}`)}
 * />
 */

import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertCircle, ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/utils/cn';
import { SortableHeader } from '@/components/common/SortableHeader';
import { HealthBar } from './HealthBar';
import { Avatar } from '@/components/primitives/Avatar';
import type { Lead, Stakeholder } from '@/api/leads';

// Constants
const STALE_THRESHOLD_DAYS = 14;
const ITEMS_PER_PAGE = 5;

export interface LeadTableProps {
  /** Array of leads to display */
  leads: Lead[];
  /** Optional stakeholders map keyed by lead ID */
  stakeholdersByLead?: Record<string, Stakeholder[]>;
  /** Additional CSS classes */
  className?: string;
}

type SortKey = 'company' | 'health' | 'last_activity' | 'value' | 'stakeholders';

// Helper to check if a lead is stale (>14 days since last activity)
function isStale(lastActivityAt: string | null): boolean {
  if (!lastActivityAt) return true;
  const lastActivity = new Date(lastActivityAt);
  const now = new Date();
  const daysDiff = Math.floor((now.getTime() - lastActivity.getTime()) / (1000 * 60 * 60 * 24));
  return daysDiff > STALE_THRESHOLD_DAYS;
}

// Format relative time for last activity
function formatLastActivity(dateStr: string | null): string {
  if (!dateStr) return 'Never';

  const date = new Date(dateStr);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 7) return `${diffDays} days ago`;
  if (diffDays < 30) {
    const weeks = Math.floor(diffDays / 7);
    return `${weeks} ${weeks === 1 ? 'week' : 'weeks'} ago`;
  }
  if (diffDays < 365) {
    const months = Math.floor(diffDays / 30);
    return `${months} ${months === 1 ? 'month' : 'months'} ago`;
  }
  const years = Math.floor(diffDays / 365);
  return `${years} ${years === 1 ? 'year' : 'years'} ago`;
}

// Format currency for expected value
function formatCurrency(value: number | null): string {
  if (value === null) return '-';
  if (value >= 1000000) {
    return `$${(value / 1000000).toFixed(1)}M`;
  }
  if (value >= 1000) {
    return `$${(value / 1000).toFixed(0)}K`;
  }
  return `$${value.toLocaleString()}`;
}

// Individual row component
interface LeadRowProps {
  lead: Lead;
  stakeholders?: Stakeholder[];
  onClick: () => void;
}

function LeadRow({ lead, stakeholders = [], onClick }: LeadRowProps) {
  const stale = isStale(lead.last_activity_at);
  const displayStakeholders = stakeholders.slice(0, 4); // Max 4 avatars

  return (
    <tr
      onClick={onClick}
      data-aria-id={`lead-${lead.id}`}
      className={cn(
        'cursor-pointer transition-colors duration-150',
        'border-b border-[var(--border)]',
        'hover:bg-[var(--bg-subtle)]'
      )}
      style={{ color: 'var(--text-primary)' }}
    >
      {/* Company Name */}
      <td className="py-3.5 px-4">
        <div className="flex items-center gap-2">
          {stale && (
            <AlertCircle
              className="w-4 h-4 flex-shrink-0"
              style={{ color: 'var(--warning)' }}
              aria-label="Stale lead - no activity in 14+ days"
            />
          )}
          <span className="font-medium truncate">{lead.company_name}</span>
        </div>
      </td>

      {/* Health Score */}
      <td className="py-3.5 px-4">
        <HealthBar score={lead.health_score} size="sm" />
      </td>

      {/* Last Activity */}
      <td className="py-3.5 px-4">
        <span
          className="text-sm font-mono"
          style={{ color: stale ? 'var(--warning)' : 'var(--text-secondary)' }}
        >
          {formatLastActivity(lead.last_activity_at)}
        </span>
      </td>

      {/* Expected Value */}
      <td className="py-3.5 px-4">
        <span className="text-sm font-medium">
          {formatCurrency(lead.expected_value)}
        </span>
      </td>

      {/* Stakeholders */}
      <td className="py-3.5 px-4">
        {displayStakeholders.length > 0 ? (
          <div className="flex items-center -space-x-2">
            {displayStakeholders.map((stakeholder) => (
              <Avatar
                key={stakeholder.id}
                name={stakeholder.contact_name || stakeholder.contact_email}
                size="xs"
                className="ring-2 ring-[var(--bg-elevated)]"
              />
            ))}
            {stakeholders.length > 4 && (
              <span
                className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-medium ring-2 ring-[var(--bg-elevated)]"
                style={{
                  backgroundColor: 'var(--bg-subtle)',
                  color: 'var(--text-secondary)',
                }}
              >
                +{stakeholders.length - 4}
              </span>
            )}
          </div>
        ) : (
          <span
            className="text-sm"
            style={{ color: 'var(--text-secondary)' }}
          >
            -
          </span>
        )}
      </td>
    </tr>
  );
}

// Skeleton row for loading state
function LeadRowSkeleton() {
  return (
    <tr className="border-b border-[var(--border)]">
      <td className="py-3.5 px-4">
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 bg-[var(--border)] rounded animate-pulse" />
          <div className="h-4 w-32 bg-[var(--border)] rounded animate-pulse" />
        </div>
      </td>
      <td className="py-3.5 px-4">
        <div className="h-2 w-20 bg-[var(--border)] rounded-full animate-pulse" />
      </td>
      <td className="py-3.5 px-4">
        <div className="h-4 w-20 bg-[var(--border)] rounded animate-pulse" />
      </td>
      <td className="py-3.5 px-4">
        <div className="h-4 w-16 bg-[var(--border)] rounded animate-pulse" />
      </td>
      <td className="py-3.5 px-4">
        <div className="flex -space-x-2">
          {[0, 1, 2].map((i) => (
            <div
              key={i}
              className="w-6 h-6 rounded-full bg-[var(--border)] animate-pulse ring-2 ring-[var(--bg-elevated)]"
            />
          ))}
        </div>
      </td>
    </tr>
  );
}

export function LeadTable({
  leads,
  stakeholdersByLead = {},
  className = '',
}: LeadTableProps) {
  const navigate = useNavigate();
  const [sortKey, setSortKey] = useState<SortKey>('health');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc'); // Default ASC for health (worst first)
  const [currentPage, setCurrentPage] = useState(1);

  // Sort leads based on current sort key and direction
  const sortedLeads = useMemo(() => {
    const sorted = [...leads].sort((a, b) => {
      let comparison = 0;

      switch (sortKey) {
        case 'company':
          comparison = a.company_name.localeCompare(b.company_name);
          break;
        case 'health':
          comparison = a.health_score - b.health_score;
          break;
        case 'last_activity': {
          const aDate = a.last_activity_at ? new Date(a.last_activity_at).getTime() : 0;
          const bDate = b.last_activity_at ? new Date(b.last_activity_at).getTime() : 0;
          comparison = aDate - bDate;
          break;
        }
        case 'value':
          comparison = (a.expected_value ?? 0) - (b.expected_value ?? 0);
          break;
        case 'stakeholders': {
          const aCount = stakeholdersByLead[a.id]?.length ?? 0;
          const bCount = stakeholdersByLead[b.id]?.length ?? 0;
          comparison = aCount - bCount;
          break;
        }
      }

      return sortDirection === 'asc' ? comparison : -comparison;
    });

    return sorted;
  }, [leads, sortKey, sortDirection, stakeholdersByLead]);

  // Paginate sorted leads
  const totalPages = Math.ceil(sortedLeads.length / ITEMS_PER_PAGE);
  const paginatedLeads = sortedLeads.slice(
    (currentPage - 1) * ITEMS_PER_PAGE,
    currentPage * ITEMS_PER_PAGE
  );

  // Handle sort change
  const handleSort = (key: string, direction: 'asc' | 'desc') => {
    setSortKey(key as SortKey);
    setSortDirection(direction);
    setCurrentPage(1); // Reset to first page on sort change
  };

  // Handle row click
  const handleRowClick = (lead: Lead) => {
    navigate(`/pipeline/leads/${lead.id}`);
  };

  // Pagination controls
  const goToPage = (page: number) => {
    setCurrentPage(Math.max(1, Math.min(page, totalPages)));
  };

  return (
    <div className={cn('flex flex-col', className)}>
      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-[var(--border)] bg-[var(--bg-elevated)]">
        <table className="w-full">
          <thead>
            <tr
              className="border-b border-[var(--border)]"
              style={{ backgroundColor: 'var(--bg-subtle)' }}
            >
              <th className="py-3 px-4 text-left">
                <SortableHeader
                  label="Company"
                  sortKey="company"
                  currentSort={sortKey}
                  currentDirection={sortDirection}
                  onSort={handleSort}
                />
              </th>
              <th className="py-3 px-4 text-left">
                <SortableHeader
                  label="Health"
                  sortKey="health"
                  currentSort={sortKey}
                  currentDirection={sortDirection}
                  onSort={handleSort}
                />
              </th>
              <th className="py-3 px-4 text-left">
                <SortableHeader
                  label="Last Activity"
                  sortKey="last_activity"
                  currentSort={sortKey}
                  currentDirection={sortDirection}
                  onSort={handleSort}
                />
              </th>
              <th className="py-3 px-4 text-left">
                <SortableHeader
                  label="Expected Value"
                  sortKey="value"
                  currentSort={sortKey}
                  currentDirection={sortDirection}
                  onSort={handleSort}
                />
              </th>
              <th className="py-3 px-4 text-left">
                <SortableHeader
                  label="Stakeholders"
                  sortKey="stakeholders"
                  currentSort={sortKey}
                  currentDirection={sortDirection}
                  onSort={handleSort}
                />
              </th>
            </tr>
          </thead>
          <tbody>
            {leads.length === 0 ? (
              // Empty state within table
              <tr>
                <td colSpan={5} className="py-8 text-center">
                  <span style={{ color: 'var(--text-secondary)' }}>
                    No leads in pipeline
                  </span>
                </td>
              </tr>
            ) : (
              paginatedLeads.map((lead) => (
                <LeadRow
                  key={lead.id}
                  lead={lead}
                  stakeholders={stakeholdersByLead[lead.id] || []}
                  onClick={() => handleRowClick(lead)}
                />
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div
          className="flex items-center justify-between mt-4 px-2"
          style={{ color: 'var(--text-secondary)' }}
        >
          <span className="text-sm">
            Showing {((currentPage - 1) * ITEMS_PER_PAGE) + 1} - {Math.min(currentPage * ITEMS_PER_PAGE, sortedLeads.length)} of {sortedLeads.length} leads
          </span>
          <div className="flex items-center gap-1">
            <button
              onClick={() => goToPage(currentPage - 1)}
              disabled={currentPage === 1}
              className={cn(
                'p-1.5 rounded transition-colors',
                currentPage === 1
                  ? 'opacity-40 cursor-not-allowed'
                  : 'hover:bg-[var(--bg-subtle)] cursor-pointer'
              )}
              aria-label="Previous page"
            >
              <ChevronLeft className="w-4 h-4" />
            </button>
            {Array.from({ length: totalPages }, (_, i) => i + 1).map((page) => (
              <button
                key={page}
                onClick={() => goToPage(page)}
                className={cn(
                  'w-8 h-8 rounded text-sm font-medium transition-colors',
                  page === currentPage
                    ? 'bg-[var(--accent)] text-white'
                    : 'hover:bg-[var(--bg-subtle)] cursor-pointer'
                )}
              >
                {page}
              </button>
            ))}
            <button
              onClick={() => goToPage(currentPage + 1)}
              disabled={currentPage === totalPages}
              className={cn(
                'p-1.5 rounded transition-colors',
                currentPage === totalPages
                  ? 'opacity-40 cursor-not-allowed'
                  : 'hover:bg-[var(--bg-subtle)] cursor-pointer'
              )}
              aria-label="Next page"
            >
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

// Export skeleton for use in loading states
export { LeadRowSkeleton };
