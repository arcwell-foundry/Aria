/**
 * PipelinePage - Lead pipeline overview and detail views
 *
 * Follows ARIA Design System v1.0:
 * - LIGHT THEME (content pages use light background)
 * - Header: "Lead Memory // Pipeline Overview" with status dot
 * - Search bar + filter chips
 * - LeadTable with sorting and pagination
 * - Empty state drives to ARIA conversation
 *
 * Routes:
 * - /pipeline -> PipelineOverview
 * - /pipeline/leads/:leadId -> LeadDetailPage
 */

import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { Search, Filter } from 'lucide-react';
import { cn } from '@/utils/cn';
import { useLeads } from '@/hooks/useLeads';
import { LeadTable } from '@/components/pipeline';
import { EmptyState } from '@/components/common/EmptyState';
import { LeadDetailPage } from './LeadDetailPage';
import type { LeadStatus, LifecycleStage } from '@/api/leads';

// Filter chip options
const STATUS_FILTERS: { label: string; value: LeadStatus | 'all' }[] = [
  { label: 'All', value: 'all' },
  { label: 'Active', value: 'active' },
  { label: 'Won', value: 'won' },
  { label: 'Lost', value: 'lost' },
  { label: 'Dormant', value: 'dormant' },
];

const STAGE_FILTERS: { label: string; value: LifecycleStage | 'all' }[] = [
  { label: 'All Stages', value: 'all' },
  { label: 'Lead', value: 'lead' },
  { label: 'Opportunity', value: 'opportunity' },
  { label: 'Account', value: 'account' },
];

const HEALTH_FILTERS: { label: string; value: 'all' | 'critical' | 'at-risk' | 'healthy' }[] = [
  { label: 'All Health', value: 'all' },
  { label: 'Critical <40', value: 'critical' },
  { label: 'At Risk 40-70', value: 'at-risk' },
  { label: 'Healthy >70', value: 'healthy' },
];

// Skeleton for loading state
function PipelineSkeleton() {
  return (
    <div className="space-y-6 animate-pulse">
      {/* Header skeleton */}
      <div className="flex items-center gap-3">
        <div className="w-3 h-3 rounded-full bg-[var(--border)]" />
        <div>
          <div className="h-3 w-24 bg-[var(--border)] rounded mb-2" />
          <div className="h-6 w-40 bg-[var(--border)] rounded" />
        </div>
      </div>

      {/* Search and filters skeleton */}
      <div className="flex items-center gap-4">
        <div className="flex-1 h-10 bg-[var(--border)] rounded-lg" />
        <div className="flex gap-2">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-8 w-20 bg-[var(--border)] rounded-full" />
          ))}
        </div>
      </div>

      {/* Table skeleton */}
      <div className="border border-[var(--border)] rounded-lg overflow-hidden">
        <div className="bg-[var(--bg-subtle)] p-3 border-b border-[var(--border)]">
          <div className="flex gap-4">
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="h-4 w-20 bg-[var(--border)] rounded" />
            ))}
          </div>
        </div>
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="p-4 border-b border-[var(--border)] flex items-center">
            <div className="flex-1 flex items-center gap-2">
              <div className="w-4 h-4 bg-[var(--border)] rounded" />
              <div className="h-4 w-32 bg-[var(--border)] rounded" />
            </div>
            <div className="w-20 h-2 bg-[var(--border)] rounded-full" />
          </div>
        ))}
      </div>
    </div>
  );
}

// Pipeline Overview Component
function PipelineOverview() {
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState<LeadStatus | 'all'>('all');
  const [stageFilter, setStageFilter] = useState<LifecycleStage | 'all'>('all');
  const [healthFilter, setHealthFilter] = useState<'all' | 'critical' | 'at-risk' | 'healthy'>('all');

  // Build filter object for API
  const leadFilters: Parameters<typeof useLeads>[0] = {
    search: searchQuery || undefined,
    status: statusFilter !== 'all' ? statusFilter : undefined,
    stage: stageFilter !== 'all' ? stageFilter : undefined,
  };

  // Apply health filter
  if (healthFilter === 'critical') {
    leadFilters.minHealth = 0;
    leadFilters.maxHealth = 39;
  } else if (healthFilter === 'at-risk') {
    leadFilters.minHealth = 40;
    leadFilters.maxHealth = 70;
  } else if (healthFilter === 'healthy') {
    leadFilters.minHealth = 71;
    leadFilters.maxHealth = 100;
  }

  // Fetch leads with filters
  const { data: leads, isLoading, error } = useLeads(leadFilters);

  // Determine if any leads match current filters
  const hasLeads = leads && leads.length > 0;

  return (
    <div className="flex-1 overflow-y-auto p-8">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-1">
          {/* Status dot */}
          <div
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: 'var(--success)' }}
          />
          <h1
            className="font-display text-2xl italic"
            style={{ color: 'var(--text-primary)' }}
          >
            Lead Memory // Pipeline Overview
          </h1>
        </div>
        <p
          className="text-sm ml-5"
          style={{ color: 'var(--text-secondary)' }}
        >
          Command Mode: Active monitoring of high-velocity leads.
        </p>
      </div>

      {/* Search and Filters */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4 mb-6">
        {/* Search bar */}
        <div className="relative flex-1 w-full sm:max-w-xs">
          <Search
            className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4"
            style={{ color: 'var(--text-secondary)' }}
          />
          <input
            type="text"
            placeholder="Search leads..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className={cn(
              'w-full pl-9 pr-4 py-2 rounded-lg',
              'border border-[var(--border)] bg-[var(--bg-elevated)]',
              'text-sm placeholder:text-[var(--text-secondary)]',
              'focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/30 focus:border-[var(--accent)]'
            )}
            style={{ color: 'var(--text-primary)' }}
          />
        </div>

        {/* Filter chips */}
        <div className="flex items-center gap-2 flex-wrap">
          <Filter
            className="w-4 h-4 mr-1"
            style={{ color: 'var(--text-secondary)' }}
          />
          {STATUS_FILTERS.map((filter) => (
            <button
              key={filter.value}
              onClick={() => setStatusFilter(filter.value)}
              className={cn(
                'px-3 py-1.5 rounded-full text-xs font-medium transition-colors',
                statusFilter === filter.value
                  ? 'bg-[var(--accent)] text-white'
                  : 'bg-[var(--bg-subtle)] hover:bg-[var(--border)]'
              )}
              style={{
                color: statusFilter === filter.value ? 'white' : 'var(--text-secondary)',
              }}
            >
              {filter.label}
            </button>
          ))}
        </div>
      </div>

      {/* Stage filter row */}
      <div className="flex items-center gap-2 mb-4">
        {STAGE_FILTERS.map((filter) => (
          <button
            key={filter.value}
            onClick={() => setStageFilter(filter.value)}
            className={cn(
              'px-3 py-1 rounded-md text-xs font-medium transition-colors',
              stageFilter === filter.value
                ? 'bg-[var(--accent)]/10 text-[var(--accent)] border border-[var(--accent)]/30'
                : 'border border-[var(--border)] hover:bg-[var(--bg-subtle)]'
            )}
            style={{
              color: stageFilter === filter.value ? 'var(--accent)' : 'var(--text-secondary)',
            }}
          >
            {filter.label}
          </button>
        ))}
      </div>

      {/* Health filter row */}
      <div className="flex items-center gap-2 mb-6">
        {HEALTH_FILTERS.map((filter) => (
          <button
            key={filter.value}
            onClick={() => setHealthFilter(filter.value)}
            className={cn(
              'px-3 py-1 rounded-md text-xs font-medium transition-colors',
              healthFilter === filter.value
                ? 'bg-[var(--accent)]/10 text-[var(--accent)] border border-[var(--accent)]/30'
                : 'border border-[var(--border)] hover:bg-[var(--bg-subtle)]'
            )}
            style={{
              color: healthFilter === filter.value ? 'var(--accent)' : 'var(--text-secondary)',
            }}
          >
            {filter.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {isLoading ? (
        <PipelineSkeleton />
      ) : error ? (
        <div
          className="text-center py-8"
          style={{ color: 'var(--text-secondary)' }}
        >
          Error loading leads. Please try again.
        </div>
      ) : !hasLeads ? (
        <EmptyState
          title="ARIA hasn't discovered any leads yet."
          description={
            searchQuery || statusFilter !== 'all' || stageFilter !== 'all' || healthFilter !== 'all'
              ? 'No leads match your current filters. Try adjusting your search criteria.'
              : 'Approve a pipeline monitoring goal to start tracking your accounts automatically.'
          }
          suggestion="Set up pipeline monitoring"
          onSuggestion={() => window.location.href = '/'}
        />
      ) : (
        <LeadTable leads={leads} />
      )}
    </div>
  );
}

// Main PipelinePage component
export function PipelinePage() {
  const { leadId } = useParams<{ leadId: string }>();

  // Show detail view if leadId is present
  if (leadId) {
    return <LeadDetailPage leadId={leadId} />;
  }

  // Show overview
  return (
    <div
      className="flex-1 flex flex-col h-full"
      style={{ backgroundColor: 'var(--bg-primary)' }}
    >
      <PipelineOverview />
    </div>
  );
}
