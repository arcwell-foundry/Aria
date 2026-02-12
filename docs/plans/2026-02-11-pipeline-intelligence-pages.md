# Pipeline & Intelligence Pages Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build Layer 2 content pages (PipelinePage, LeadDetailPage, IntelligencePage, BattleCardDetail) with ARIA-personality empty states and the persistent Intel Panel.

**Architecture:** Pages use existing API hooks (useLeads, useBattleCards) and Intel Panel modules. New components include EmptyState, CopyButton, SortableHeader, and HealthBar. Intel modules updated to use real API data instead of placeholders.

**Tech Stack:** React 18, TypeScript, React Query, Tailwind CSS, Lucide icons, React Router

---

## Prerequisites: Existing Infrastructure

The following already exists and should be reused:
- `frontend/src/hooks/useLeads.ts` — useLeads, useLead, useLeadTimeline, useLeadStakeholders, useLeadInsights
- `frontend/src/hooks/useBattleCards.ts` — useBattleCards, useBattleCard, useBattleCardHistory
- `frontend/src/api/leads.ts` — Lead, Stakeholder, LeadEvent, Insight types and API functions
- `frontend/src/api/battleCards.ts` — BattleCard type and API functions
- `frontend/src/components/shell/IntelPanel.tsx` — Route-based panel configuration
- `frontend/src/components/shell/intel-modules/*.tsx` — Alert, BuyingSignals, etc.
- `frontend/src/components/primitives/` — ProgressBar, Avatar, Badge, Card, etc.
- `frontend/src/app/routes.tsx` — Route definitions (already has lead detail and battle card routes)

---

## Task 1: Create Shared Components

### Task 1a: EmptyState Component

**Files:**
- Create: `frontend/src/components/common/EmptyState.tsx`

**Step 1: Create EmptyState component**

```tsx
// frontend/src/components/common/EmptyState.tsx
import { MessageSquare } from 'lucide-react';

interface EmptyStateProps {
  title: string;
  description: string;
  suggestion: string;
  onSuggestion: () => void;
  icon?: React.ReactNode;
}

export function EmptyState({
  title,
  description,
  suggestion,
  onSuggestion,
  icon,
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full py-16 px-8 text-center">
      <div
        className="w-16 h-16 rounded-full flex items-center justify-center mb-6"
        style={{ backgroundColor: 'var(--bg-subtle)' }}
      >
        {icon || (
          <MessageSquare
            size={28}
            strokeWidth={1.5}
            style={{ color: 'var(--text-secondary)' }}
          />
        )}
      </div>
      <h3
        className="font-display text-xl mb-3"
        style={{ color: 'var(--text-primary)' }}
      >
        {title}
      </h3>
      <p
        className="font-sans text-sm max-w-md mb-6"
        style={{ color: 'var(--text-secondary)' }}
      >
        {description}
      </p>
      <button
        onClick={onSuggestion}
        className="px-4 py-2 rounded-lg font-sans text-sm font-medium transition-all duration-200"
        style={{
          backgroundColor: 'var(--accent-primary)',
          color: 'white',
        }}
        onMouseEnter={(e) => {
          e.currentTarget.style.opacity = '0.9';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.opacity = '1';
        }}
      >
        {suggestion}
      </button>
    </div>
  );
}
```

**Step 2: Create barrel export**

```tsx
// frontend/src/components/common/index.ts
export { EmptyState } from './EmptyState';
```

**Step 3: Commit**

```bash
git add frontend/src/components/common/
git commit -m "feat: add EmptyState component for ARIA-personality empty views"
```

---

### Task 1b: CopyButton Component

**Files:**
- Create: `frontend/src/components/common/CopyButton.tsx`
- Modify: `frontend/src/components/common/index.ts`

**Step 1: Create CopyButton component**

```tsx
// frontend/src/components/common/CopyButton.tsx
import { useState } from 'react';
import { Copy, CheckCheck } from 'lucide-react';

interface CopyButtonProps {
  text: string;
  className?: string;
}

export function CopyButton({ text, className = '' }: CopyButtonProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch (err) {
      console.error('Failed to copy:', err);
    }
  };

  return (
    <button
      onClick={handleCopy}
      className={`flex items-center gap-1.5 px-2 py-1 rounded text-xs font-medium transition-all duration-200 ${className}`}
      style={{
        color: copied ? 'var(--success)' : 'var(--text-secondary)',
        backgroundColor: copied ? 'var(--success-light, rgba(34,197,94,0.1))' : 'var(--bg-subtle)',
      }}
      title={copied ? 'Copied!' : 'Copy to clipboard'}
    >
      {copied ? (
        <>
          <CheckCheck size={14} strokeWidth={2} />
          <span>Copied</span>
        </>
      ) : (
        <>
          <Copy size={14} strokeWidth={1.5} />
        </>
      )}
    </button>
  );
}
```

**Step 2: Update barrel export**

```tsx
// frontend/src/components/common/index.ts
export { EmptyState } from './EmptyState';
export { CopyButton } from './CopyButton';
```

**Step 3: Commit**

```bash
git add frontend/src/components/common/
git commit -m "feat: add CopyButton with clipboard feedback"
```

---

### Task 1c: SortableHeader Component

**Files:**
- Create: `frontend/src/components/common/SortableHeader.tsx`
- Modify: `frontend/src/components/common/index.ts`

**Step 1: Create SortableHeader component**

```tsx
// frontend/src/components/common/SortableHeader.tsx
import { ChevronUp, ChevronDown } from 'lucide-react';

export type SortDirection = 'asc' | 'desc' | null;

interface SortableHeaderProps {
  label: string;
  sortKey: string;
  currentSort: string | null;
  currentDirection: SortDirection;
  onSort: (key: string) => void;
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

  return (
    <button
      onClick={() => onSort(sortKey)}
      className={`flex items-center gap-1 text-left font-sans text-xs font-medium uppercase tracking-wider transition-colors duration-150 cursor-pointer ${className}`}
      style={{
        color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.color = 'var(--text-primary)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.color = isActive ? 'var(--text-primary)' : 'var(--text-secondary)';
      }}
    >
      {label}
      <span className="flex flex-col" style={{ marginLeft: '2px' }}>
        <ChevronUp
          size={10}
          strokeWidth={2}
          style={{
            marginBottom: '-4px',
            opacity: isActive && currentDirection === 'asc' ? 1 : 0.3,
          }}
        />
        <ChevronDown
          size={10}
          strokeWidth={2}
          style={{
            opacity: isActive && currentDirection === 'desc' ? 1 : 0.3,
          }}
        />
      </span>
    </button>
  );
}
```

**Step 2: Update barrel export**

```tsx
// frontend/src/components/common/index.ts
export { EmptyState } from './EmptyState';
export { CopyButton } from './CopyButton';
export { SortableHeader, type SortDirection } from './SortableHeader';
```

**Step 3: Commit**

```bash
git add frontend/src/components/common/
git commit -m "feat: add SortableHeader with visual sort indicators"
```

---

### Task 1d: HealthBar Component

**Files:**
- Create: `frontend/src/components/pipeline/HealthBar.tsx`

**Step 1: Create HealthBar component**

```tsx
// frontend/src/components/pipeline/HealthBar.tsx
interface HealthBarProps {
  score: number;
  showLabel?: boolean;
  size?: 'sm' | 'md';
  className?: string;
}

export function HealthBar({
  score,
  showLabel = true,
  size = 'md',
  className = '',
}: HealthBarProps) {
  // Determine color based on score
  const getColor = (value: number): string => {
    if (value >= 70) return 'var(--success)';
    if (value >= 40) return 'var(--warning)';
    return 'var(--critical)';
  };

  const getBgColor = (value: number): string => {
    if (value >= 70) return 'rgba(34, 197, 94, 0.1)';
    if (value >= 40) return 'rgba(245, 158, 11, 0.1)';
    return 'rgba(239, 68, 68, 0.1)';
  };

  const heightClass = size === 'sm' ? 'h-1.5' : 'h-2.5';

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      <div
        className={`w-full rounded-full overflow-hidden ${heightClass}`}
        style={{ backgroundColor: getBgColor(score) }}
      >
        <div
          className={`h-full rounded-full transition-all duration-300`}
          style={{
            width: `${score}%`,
            backgroundColor: getColor(score),
          }}
        />
      </div>
      {showLabel && (
        <span
          className="font-mono text-xs tabular-nums min-w-[2.5rem] text-right"
          style={{ color: getColor(score) }}
        >
          {score}%
        </span>
      )}
    </div>
  );
}
```

**Step 2: Create barrel export**

```tsx
// frontend/src/components/pipeline/index.ts
export { HealthBar } from './HealthBar';
```

**Step 3: Commit**

```bash
git add frontend/src/components/pipeline/
git commit -m "feat: add HealthBar with color-coded health scores"
```

---

## Task 2: Build PipelinePage

### Task 2a: LeadTable Component

**Files:**
- Create: `frontend/src/components/pipeline/LeadTable.tsx`
- Modify: `frontend/src/components/pipeline/index.ts`

**Step 1: Create LeadTable component**

```tsx
// frontend/src/components/pipeline/LeadTable.tsx
import { useState, useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertCircle } from 'lucide-react';
import type { Lead } from '@/api/leads';
import { useLeadStakeholders } from '@/hooks/useLeads';
import { HealthBar } from './HealthBar';
import { SortableHeader, type SortDirection } from '@/components/common';
import { Avatar } from '@/components/primitives/Avatar';

interface LeadTableProps {
  leads: Lead[];
}

const ITEMS_PER_PAGE = 5;

function formatRelativeTime(dateString: string | null): string {
  if (!dateString) return 'Never';
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return 'Today';
  if (diffDays === 1) return 'Yesterday';
  if (diffDays < 14) return `${diffDays} days ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} weeks ago`;
  return `${Math.floor(diffDays / 30)} months ago`;
}

function formatCurrency(value: number | null): string {
  if (value === null) return '—';
  if (value >= 1000000) return `$${(value / 1000000).toFixed(1)}M`;
  if (value >= 1000) return `$${(value / 1000).toFixed(0)}K`;
  return `$${value}`;
}

export function LeadTable({ leads }: LeadTableProps) {
  const navigate = useNavigate();
  const [sortKey, setSortKey] = useState<string>('health');
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');
  const [page, setPage] = useState(0);

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      setSortDirection(key === 'health' ? 'asc' : 'desc');
    }
  };

  const sortedLeads = useMemo(() => {
    const sorted = [...leads].sort((a, b) => {
      let comparison = 0;
      switch (sortKey) {
        case 'company':
          comparison = a.company_name.localeCompare(b.company_name);
          break;
        case 'health':
          comparison = (a.health_score ?? 0) - (b.health_score ?? 0);
          break;
        case 'activity':
          const aTime = a.last_activity_at ? new Date(a.last_activity_at).getTime() : 0;
          const bTime = b.last_activity_at ? new Date(b.last_activity_at).getTime() : 0;
          comparison = aTime - bTime;
          break;
        case 'value':
          comparison = (a.expected_value ?? 0) - (b.expected_value ?? 0);
          break;
        default:
          return 0;
      }
      return sortDirection === 'asc' ? comparison : -comparison;
    });
    return sorted;
  }, [leads, sortKey, sortDirection]);

  const paginatedLeads = sortedLeads.slice(
    page * ITEMS_PER_PAGE,
    (page + 1) * ITEMS_PER_PAGE
  );

  const totalPages = Math.ceil(leads.length / ITEMS_PER_PAGE);
  const startItem = page * ITEMS_PER_PAGE + 1;
  const endItem = Math.min((page + 1) * ITEMS_PER_PAGE, leads.length);

  return (
    <div>
      {/* Table */}
      <div className="rounded-lg border overflow-hidden" style={{ borderColor: 'var(--border)' }}>
        {/* Header */}
        <div
          className="grid grid-cols-[1fr_140px_140px_120px_100px] gap-4 px-4 py-3 border-b"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <SortableHeader
            label="Company"
            sortKey="company"
            currentSort={sortKey}
            currentDirection={sortDirection}
            onSort={handleSort}
          />
          <SortableHeader
            label="Health Score"
            sortKey="health"
            currentSort={sortKey}
            currentDirection={sortDirection}
            onSort={handleSort}
          />
          <SortableHeader
            label="Last Activity"
            sortKey="activity"
            currentSort={sortKey}
            currentDirection={sortDirection}
            onSort={handleSort}
          />
          <SortableHeader
            label="Expected Value"
            sortKey="value"
            currentSort={sortKey}
            currentDirection={sortDirection}
            onSort={handleSort}
          />
          <span
            className="font-sans text-xs font-medium uppercase tracking-wider"
            style={{ color: 'var(--text-secondary)' }}
          >
            Stakeholders
          </span>
        </div>

        {/* Rows */}
        {paginatedLeads.map((lead) => (
          <LeadRow
            key={lead.id}
            lead={lead}
            onClick={() => navigate(`/pipeline/leads/${lead.id}`)}
          />
        ))}
      </div>

      {/* Pagination */}
      <div
        className="flex items-center justify-between mt-4 px-2"
        style={{ color: 'var(--text-secondary)' }}
      >
        <span className="font-sans text-sm">
          Showing {startItem}-{endItem} of {leads.length} leads
        </span>
        <div className="flex gap-2">
          <button
            onClick={() => setPage(Math.max(0, page - 1))}
            disabled={page === 0}
            className="px-3 py-1 rounded text-sm font-sans disabled:opacity-40"
            style={{
              backgroundColor: 'var(--bg-subtle)',
              color: 'var(--text-primary)',
            }}
          >
            Previous
          </button>
          <button
            onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
            disabled={page >= totalPages - 1}
            className="px-3 py-1 rounded text-sm font-sans disabled:opacity-40"
            style={{
              backgroundColor: 'var(--bg-subtle)',
              color: 'var(--text-primary)',
            }}
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}

function LeadRow({ lead, onClick }: { lead: Lead; onClick: () => void }) {
  const { data: stakeholders = [] } = useLeadStakeholders(lead.id);
  const daysSinceActivity = lead.last_activity_at
    ? Math.floor((Date.now() - new Date(lead.last_activity_at).getTime()) / (1000 * 60 * 60 * 24))
    : null;
  const isStale = daysSinceActivity !== null && daysSinceActivity > 14;

  return (
    <div
      data-aria-id={`lead-${lead.id}`}
      onClick={onClick}
      className="grid grid-cols-[1fr_140px_140px_120px_100px] gap-4 px-4 py-3 border-b cursor-pointer transition-colors duration-150"
      style={{ borderColor: 'var(--border)' }}
      onMouseEnter={(e) => {
        e.currentTarget.style.backgroundColor = 'var(--bg-subtle)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.backgroundColor = 'transparent';
      }}
    >
      {/* Company */}
      <div>
        <span className="font-sans text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          {lead.company_name}
        </span>
        {lead.crm_id && (
          <span
            className="ml-2 font-mono text-[10px] px-1.5 py-0.5 rounded"
            style={{ backgroundColor: 'var(--bg-subtle)', color: 'var(--text-muted)' }}
          >
            CRM
          </span>
        )}
      </div>

      {/* Health Score */}
      <HealthBar score={lead.health_score ?? 0} size="sm" />

      {/* Last Activity */}
      <div className="flex items-center gap-1">
        <span className="font-sans text-sm" style={{ color: 'var(--text-secondary)' }}>
          {formatRelativeTime(lead.last_activity_at)}
        </span>
        {isStale && (
          <AlertCircle size={14} style={{ color: 'var(--warning)' }} />
        )}
      </div>

      {/* Expected Value */}
      <span className="font-mono text-sm tabular-nums" style={{ color: 'var(--text-primary)' }}>
        {formatCurrency(lead.expected_value)}
      </span>

      {/* Stakeholders */}
      <div className="flex -space-x-2">
        {stakeholders.slice(0, 3).map((s) => (
          <Avatar
            key={s.id}
            name={s.contact_name || s.contact_email}
            size="xs"
            className="ring-2"
            style={{ '--tw-ring-color': 'var(--bg-elevated)' } as React.CSSProperties}
          />
        ))}
        {stakeholders.length > 3 && (
          <span
            className="w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-medium"
            style={{
              backgroundColor: 'var(--bg-subtle)',
              color: 'var(--text-secondary)',
            }}
          >
            +{stakeholders.length - 3}
          </span>
        )}
      </div>
    </div>
  );
}
```

**Step 2: Update barrel export**

```tsx
// frontend/src/components/pipeline/index.ts
export { HealthBar } from './HealthBar';
export { LeadTable } from './LeadTable';
```

**Step 3: Commit**

```bash
git add frontend/src/components/pipeline/
git commit -m "feat: add LeadTable with sorting, pagination, and health indicators"
```

---

### Task 2b: PipelinePage Implementation

**Files:**
- Modify: `frontend/src/components/pages/PipelinePage.tsx`

**Step 1: Implement PipelinePage**

```tsx
// frontend/src/components/pages/PipelinePage.tsx
import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { Search, Filter } from 'lucide-react';
import { useLeads, type LeadFilters } from '@/hooks/useLeads';
import { LeadTable } from '@/components/pipeline';
import { EmptyState } from '@/components/common';

export function PipelinePage() {
  const { leadId } = useParams();

  // If leadId is present, show detail view
  if (leadId) {
    return <LeadDetailView leadId={leadId} />;
  }

  return <PipelineOverview />;
}

function PipelineOverview() {
  const [search, setSearch] = useState('');
  const [filters, setFilters] = useState<LeadFilters>({
    sortBy: 'health',
    sortOrder: 'asc',
  });

  const { data: leads = [], isLoading } = useLeads({
    ...filters,
    search: search || undefined,
  });

  const handleSendToARIA = (message: string) => {
    // TODO: Integrate with ARIA conversation
    console.log('Send to ARIA:', message);
  };

  if (isLoading) {
    return <PipelineSkeleton />;
  }

  if (leads.length === 0) {
    return (
      <div className="flex-1 overflow-y-auto">
        <EmptyState
          title="ARIA hasn't discovered any leads yet."
          description="Approve a pipeline monitoring goal to start tracking your accounts automatically."
          suggestion="Set up pipeline monitoring"
          onSuggestion={() => handleSendToARIA('Set up pipeline monitoring for my accounts')}
        />
      </div>
    );
  }

  return (
    <div className="flex-1 overflow-y-auto p-8">
      {/* Header */}
      <div className="mb-6">
        <h1
          className="font-display text-2xl italic mb-1"
          style={{ color: 'var(--text-primary)' }}
        >
          Lead Memory // Pipeline Overview
        </h1>
        <div className="flex items-center gap-2">
          <span
            className="w-2 h-2 rounded-full"
            style={{ backgroundColor: 'var(--success)' }}
          />
          <span className="font-sans text-sm" style={{ color: 'var(--text-secondary)' }}>
            Command Mode: Active monitoring of high-velocity leads.
          </span>
        </div>
      </div>

      {/* Controls */}
      <div className="flex items-center gap-4 mb-6">
        <div className="relative flex-1 max-w-md">
          <Search
            size={16}
            className="absolute left-3 top-1/2 -translate-y-1/2"
            style={{ color: 'var(--text-muted)' }}
          />
          <input
            type="text"
            placeholder="Search companies..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 rounded-lg font-sans text-sm"
            style={{
              backgroundColor: 'var(--bg-subtle)',
              border: '1px solid var(--border)',
              color: 'var(--text-primary)',
            }}
          />
        </div>
        <button
          className="flex items-center gap-2 px-3 py-2 rounded-lg font-sans text-sm"
          style={{
            backgroundColor: 'var(--bg-subtle)',
            color: 'var(--text-secondary)',
            border: '1px solid var(--border)',
          }}
        >
          <Filter size={16} />
          Filters
        </button>
      </div>

      {/* Table */}
      <LeadTable leads={leads} />
    </div>
  );
}

function LeadDetailView({ leadId }: { leadId: string }) {
  // TODO: Implement in Task 3
  return (
    <div className="flex-1 overflow-y-auto p-8">
      <p className="font-sans text-sm" style={{ color: 'var(--text-secondary)' }}>
        Lead detail view coming in Task 3. Lead ID: {leadId}
      </p>
    </div>
  );
}

function PipelineSkeleton() {
  return (
    <div className="flex-1 overflow-y-auto p-8 animate-pulse">
      <div className="h-8 w-64 rounded mb-2" style={{ backgroundColor: 'var(--bg-subtle)' }} />
      <div className="h-4 w-96 rounded mb-6" style={{ backgroundColor: 'var(--bg-subtle)' }} />
      <div className="h-96 rounded-lg" style={{ backgroundColor: 'var(--bg-subtle)' }} />
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/pages/PipelinePage.tsx
git commit -m "feat: implement PipelinePage with search, filters, and empty states"
```

---

## Task 3: Build LeadDetailPage

**Files:**
- Create: `frontend/src/components/pages/LeadDetailPage.tsx`
- Modify: `frontend/src/components/pages/PipelinePage.tsx`

**Step 1: Create LeadDetailPage component**

```tsx
// frontend/src/components/pages/LeadDetailPage.tsx
import { useNavigate } from 'react-router-dom';
import { ArrowLeft, Check, AlertCircle, Clock, RefreshCw } from 'lucide-react';
import { useLead, useLeadStakeholders, useLeadTimeline, useLeadInsights } from '@/hooks/useLeads';
import { HealthBar } from '@/components/pipeline';
import { Avatar } from '@/components/primitives/Avatar';
import { EmptyState } from '@/components/common';

interface LeadDetailPageProps {
  leadId: string;
}

export function LeadDetailPage({ leadId }: LeadDetailPageProps) {
  const navigate = useNavigate();
  const { data: lead, isLoading: leadLoading } = useLead(leadId);
  const { data: stakeholders = [], isLoading: stakeholdersLoading } = useLeadStakeholders(leadId);
  const { data: timeline = [], isLoading: timelineLoading } = useLeadTimeline(leadId);
  const { data: insights = [], isLoading: insightsLoading } = useLeadInsights(leadId);

  const isLoading = leadLoading || stakeholdersLoading || timelineLoading || insightsLoading;

  if (isLoading) {
    return <LeadDetailSkeleton />;
  }

  if (!lead) {
    return (
      <div className="flex-1 overflow-y-auto">
        <EmptyState
          title="Lead not found"
          description="This lead may have been removed or you don't have access."
          suggestion="Go to Pipeline"
          onSuggestion={() => navigate('/pipeline')}
        />
      </div>
    );
  }

  const buyingSignals = insights.filter((i) => i.insight_type === 'buying_signal');
  const objections = insights.filter((i) => i.insight_type === 'objection');

  return (
    <div className="flex-1 overflow-y-auto p-8">
      {/* Back button */}
      <button
        onClick={() => navigate('/pipeline')}
        className="flex items-center gap-2 mb-6 font-sans text-sm transition-colors duration-150"
        style={{ color: 'var(--text-secondary)' }}
        onMouseEnter={(e) => {
          e.currentTarget.style.color = 'var(--text-primary)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.color = 'var(--text-secondary)';
        }}
      >
        <ArrowLeft size={16} />
        Back to Pipeline
      </button>

      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <h1
            className="font-display text-3xl italic"
            style={{ color: 'var(--text-primary)' }}
          >
            {lead.company_name}
          </h1>
          {lead.crm_id && (
            <span
              className="flex items-center gap-1 px-2 py-1 rounded font-sans text-xs"
              style={{ backgroundColor: 'var(--bg-subtle)', color: 'var(--success)' }}
            >
              <Check size={12} />
              Verified
            </span>
          )}
        </div>
        <div className="flex items-center gap-4">
          <span
            className="px-2 py-1 rounded font-sans text-xs font-medium"
            style={{
              backgroundColor: 'var(--accent-muted)',
              color: 'var(--accent-primary)',
            }}
          >
            {lead.lifecycle_stage?.replace('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase())}
          </span>
          <span className="font-mono text-xs" style={{ color: 'var(--text-muted)' }}>
            Lead ID: {lead.id.slice(0, 8).toUpperCase()}
          </span>
        </div>
      </div>

      {/* Metrics Bar */}
      <div
        className="flex items-center gap-6 p-4 rounded-lg mb-8"
        style={{ backgroundColor: 'var(--bg-subtle)' }}
      >
        <div className="flex-1">
          <span className="font-sans text-xs uppercase tracking-wider block mb-2" style={{ color: 'var(--text-muted)' }}>
            Health Score
          </span>
          <div className="w-48">
            <HealthBar score={lead.health_score ?? 0} />
          </div>
        </div>
        <div className="h-8 w-px" style={{ backgroundColor: 'var(--border)' }} />
        <div className="flex items-center gap-2">
          <RefreshCw size={14} style={{ color: 'var(--text-muted)' }} />
          <span className="font-sans text-sm" style={{ color: 'var(--text-secondary)' }}>
            {lead.crm_provider ? `Synced to ${lead.crm_provider}` : 'Not synced to CRM'}
          </span>
        </div>
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-[280px_1fr] gap-8">
        {/* Stakeholders */}
        <div>
          <h2
            className="font-sans text-xs font-medium uppercase tracking-wider mb-4"
            style={{ color: 'var(--text-secondary)' }}
          >
            Stakeholders ({stakeholders.length})
          </h2>
          <div className="space-y-3">
            {stakeholders.length === 0 ? (
              <p className="font-sans text-sm italic" style={{ color: 'var(--text-muted)' }}>
                No stakeholders identified yet.
              </p>
            ) : (
              stakeholders.map((stakeholder) => (
                <StakeholderCard key={stakeholder.id} stakeholder={stakeholder} />
              ))
            )}
          </div>
        </div>

        {/* Timeline */}
        <div>
          <h2
            className="font-sans text-xs font-medium uppercase tracking-wider mb-4"
            style={{ color: 'var(--text-secondary)' }}
          >
            Relationship Timeline
          </h2>
          {timeline.length === 0 ? (
            <p className="font-sans text-sm italic" style={{ color: 'var(--text-muted)' }}>
              No activity recorded yet.
            </p>
          ) : (
            <div className="space-y-4">
              {timeline.map((event, index) => (
                <TimelineEvent
                  key={event.id}
                  event={event}
                  isLatest={index === 0}
                />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function StakeholderCard({ stakeholder }: { stakeholder: any }) {
  const roleColors: Record<string, string> = {
    champion: 'var(--success)',
    decision_maker: 'var(--accent-primary)',
    influencer: 'var(--info)',
    blocker: 'var(--critical)',
    user: 'var(--text-secondary)',
  };

  const sentimentIcons: Record<string, string> = {
    positive: '😊',
    neutral: '😐',
    negative: '😟',
    unknown: '❓',
  };

  return (
    <div
      data-aria-id={`stakeholder-${stakeholder.id}`}
      className="p-3 rounded-lg border"
      style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
    >
      <div className="flex items-start gap-3">
        <Avatar
          name={stakeholder.contact_name || stakeholder.contact_email}
          size="sm"
        />
        <div className="flex-1 min-w-0">
          <p className="font-sans text-sm font-medium truncate" style={{ color: 'var(--text-primary)' }}>
            {stakeholder.contact_name || stakeholder.contact_email}
          </p>
          <p className="font-sans text-xs truncate" style={{ color: 'var(--text-muted)' }}>
            {stakeholder.title || 'No title'}
          </p>
          <div className="flex items-center gap-2 mt-2">
            {stakeholder.role && (
              <span
                className="px-2 py-0.5 rounded text-[10px] font-medium uppercase"
                style={{
                  backgroundColor: roleColors[stakeholder.role] || 'var(--bg-subtle)',
                  color: stakeholder.role === 'champion' || stakeholder.role === 'decision_maker' ? 'white' : 'var(--text-secondary)',
                }}
              >
                {stakeholder.role.replace('_', ' ')}
              </span>
            )}
            <span className="text-xs">
              {sentimentIcons[stakeholder.sentiment] || sentimentIcons.unknown}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
}

function TimelineEvent({ event, isLatest }: { event: any; isLatest: boolean }) {
  const eventIcons: Record<string, typeof Clock> = {
    email_sent: Clock,
    email_received: Clock,
    meeting: Clock,
    call: Clock,
    note: Clock,
    signal: AlertCircle,
  };

  const Icon = eventIcons[event.event_type] || Clock;
  const occurredAt = new Date(event.occurred_at).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });

  return (
    <div
      data-aria-id={`timeline-${event.id}`}
      className="flex gap-4"
    >
      <div className="flex flex-col items-center">
        <div
          className={`w-3 h-3 rounded-full ${isLatest ? '' : 'opacity-50'}`}
          style={{ backgroundColor: isLatest ? 'var(--accent-primary)' : 'var(--text-muted)' }}
        />
        {isLatest && (
          <div className="w-0.5 flex-1" style={{ backgroundColor: 'var(--border)' }} />
        )}
      </div>
      <div
        className="flex-1 p-3 rounded-lg border"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
      >
        <div className="flex items-center justify-between mb-1">
          <span className="font-sans text-xs font-medium uppercase" style={{ color: 'var(--text-secondary)' }}>
            {event.event_type.replace('_', ' ')}
          </span>
          <span className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>
            {occurredAt}
          </span>
        </div>
        {event.subject && (
          <p className="font-sans text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
            {event.subject}
          </p>
        )}
        {event.content && (
          <p className="font-sans text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
            {event.content.slice(0, 150)}
            {event.content.length > 150 ? '...' : ''}
          </p>
        )}
        {event.participants && event.participants.length > 0 && (
          <p className="font-sans text-xs mt-2" style={{ color: 'var(--text-muted)' }}>
            Participants: {event.participants.join(', ')}
          </p>
        )}
      </div>
    </div>
  );
}

function LeadDetailSkeleton() {
  return (
    <div className="flex-1 overflow-y-auto p-8 animate-pulse">
      <div className="h-4 w-24 rounded mb-6" style={{ backgroundColor: 'var(--bg-subtle)' }} />
      <div className="h-10 w-64 rounded mb-2" style={{ backgroundColor: 'var(--bg-subtle)' }} />
      <div className="h-6 w-48 rounded mb-6" style={{ backgroundColor: 'var(--bg-subtle)' }} />
      <div className="h-20 rounded-lg mb-8" style={{ backgroundColor: 'var(--bg-subtle)' }} />
      <div className="grid grid-cols-[280px_1fr] gap-8">
        <div className="space-y-3">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-24 rounded-lg" style={{ backgroundColor: 'var(--bg-subtle)' }} />
          ))}
        </div>
        <div className="space-y-4">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="h-28 rounded-lg" style={{ backgroundColor: 'var(--bg-subtle)' }} />
          ))}
        </div>
      </div>
    </div>
  );
}
```

**Step 2: Update PipelinePage to use LeadDetailPage**

```tsx
// In PipelinePage.tsx, replace LeadDetailView with:
import { LeadDetailPage } from './LeadDetailPage';

// Then in PipelinePage component:
function LeadDetailView({ leadId }: { leadId: string }) {
  return <LeadDetailPage leadId={leadId} />;
}
```

**Step 3: Commit**

```bash
git add frontend/src/components/pages/
git commit -m "feat: implement LeadDetailPage with stakeholders and timeline"
```

---

## Task 4: Build IntelligencePage

### Task 4a: BattleCardPreview Component

**Files:**
- Create: `frontend/src/components/intelligence/BattleCardPreview.tsx`

**Step 1: Create BattleCardPreview component**

```tsx
// frontend/src/components/intelligence/BattleCardPreview.tsx
import { useNavigate } from 'react-router-dom';
import { TrendingUp, TrendingDown, Minus, Clock } from 'lucide-react';
import type { BattleCard } from '@/api/battleCards';

interface BattleCardPreviewProps {
  card: BattleCard;
}

export function BattleCardPreview({ card }: BattleCardPreviewProps) {
  const navigate = useNavigate();

  // Mock data for display (would come from API in real implementation)
  const winRate = Math.floor(Math.random() * 40) + 40; // 40-80%
  const marketCapGap = Math.floor(Math.random() * 3000) - 1500; // -1500 to +1500
  const lastSignalDays = Math.floor(Math.random() * 14) + 1;

  const formatMarketCap = (value: number): string => {
    const absValue = Math.abs(value);
    if (absValue >= 1000) return `$${(absValue / 1000).toFixed(1)}B`;
    return `$${absValue}M`;
  };

  const getWinRateColor = (rate: number): string => {
    if (rate >= 60) return 'var(--success)';
    if (rate >= 40) return 'var(--warning)';
    return 'var(--critical)';
  };

  return (
    <div
      data-aria-id={`battle-card-${card.id}`}
      onClick={() => navigate(`/intelligence/battle-cards/${encodeURIComponent(card.competitor_name)}`)}
      className="p-4 rounded-lg border cursor-pointer transition-all duration-200"
      style={{
        borderColor: 'var(--border)',
        backgroundColor: 'var(--bg-subtle)',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.borderColor = 'var(--accent-primary)';
        e.currentTarget.style.transform = 'translateY(-2px)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.borderColor = 'var(--border)';
        e.currentTarget.style.transform = 'translateY(0)';
      }}
    >
      <h3
        className="font-display text-lg mb-3"
        style={{ color: 'var(--text-primary)' }}
      >
        {card.competitor_name}
      </h3>

      <div className="grid grid-cols-2 gap-4 mb-3">
        {/* Market Cap Gap */}
        <div>
          <span className="font-sans text-[10px] uppercase tracking-wider block mb-1" style={{ color: 'var(--text-muted)' }}>
            Market Cap Gap
          </span>
          <div className="flex items-center gap-1">
            {marketCapGap < 0 ? (
              <TrendingDown size={14} style={{ color: 'var(--success)' }} />
            ) : marketCapGap > 0 ? (
              <TrendingUp size={14} style={{ color: 'var(--critical)' }} />
            ) : (
              <Minus size={14} style={{ color: 'var(--text-muted)' }} />
            )}
            <span
              className="font-mono text-sm"
              style={{ color: marketCapGap <= 0 ? 'var(--success)' : 'var(--critical)' }}
            >
              {marketCapGap >= 0 ? '+' : ''}{formatMarketCap(marketCapGap)}
            </span>
          </div>
        </div>

        {/* Win Rate */}
        <div>
          <span className="font-sans text-[10px] uppercase tracking-wider block mb-1" style={{ color: 'var(--text-muted)' }}>
            Win Rate
          </span>
          <span className="font-mono text-sm" style={{ color: getWinRateColor(winRate) }}>
            {winRate}%
          </span>
        </div>
      </div>

      {/* Last Signal */}
      <div className="flex items-center gap-2">
        <Clock size={12} style={{ color: 'var(--text-muted)' }} />
        <span className="font-mono text-xs" style={{ color: 'var(--text-muted)' }}>
          Last signal: {lastSignalDays}d ago
        </span>
      </div>
    </div>
  );
}
```

**Step 2: Create barrel export**

```tsx
// frontend/src/components/intelligence/index.ts
export { BattleCardPreview } from './BattleCardPreview';
```

**Step 3: Commit**

```bash
git add frontend/src/components/intelligence/
git commit -m "feat: add BattleCardPreview with market cap and win rate"
```

---

### Task 4b: IntelligencePage Implementation

**Files:**
- Modify: `frontend/src/components/pages/IntelligencePage.tsx`

**Step 1: Implement IntelligencePage**

```tsx
// frontend/src/components/pages/IntelligencePage.tsx
import { useParams } from 'react-router-dom';
import { Newspaper } from 'lucide-react';
import { useBattleCards } from '@/hooks/useBattleCards';
import { BattleCardPreview } from '@/components/intelligence';
import { EmptyState } from '@/components/common';
import { BattleCardDetail } from './BattleCardDetail';

export function IntelligencePage() {
  const { competitorId } = useParams();

  // If competitorId is present, show battle card detail
  if (competitorId) {
    return <BattleCardDetail competitorName={decodeURIComponent(competitorId)} />;
  }

  return <IntelligenceOverview />;
}

function IntelligenceOverview() {
  const { data: battleCards = [], isLoading } = useBattleCards();

  const handleSendToARIA = (message: string) => {
    // TODO: Integrate with ARIA conversation
    console.log('Send to ARIA:', message);
  };

  if (isLoading) {
    return <IntelligenceSkeleton />;
  }

  return (
    <div className="flex-1 overflow-y-auto p-8">
      {/* Header */}
      <div className="mb-6">
        <h1
          className="font-display text-2xl italic mb-1"
          style={{ color: 'var(--text-primary)' }}
        >
          Competitive Intelligence
        </h1>
        <p className="font-sans text-sm" style={{ color: 'var(--text-secondary)' }}>
          ARIA monitors competitor movements, news, and market signals.
        </p>
      </div>

      {/* Battle Cards Section */}
      <section className="mb-8">
        <h2
          className="font-sans text-xs font-medium uppercase tracking-wider mb-4"
          style={{ color: 'var(--text-secondary)' }}
        >
          Battle Cards
        </h2>

        {battleCards.length === 0 ? (
          <EmptyState
            title="ARIA hasn't researched any competitors yet."
            description="Ask ARIA to analyze a competitor to generate a battle card with talking points and objection handlers."
            suggestion="Research a competitor"
            onSuggestion={() => handleSendToARIA('Research a competitor and create a battle card')}
          />
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {battleCards.map((card) => (
              <BattleCardPreview key={card.id} card={card} />
            ))}
          </div>
        )}
      </section>

      {/* Market Signals Section */}
      <section>
        <h2
          className="font-sans text-xs font-medium uppercase tracking-wider mb-4"
          style={{ color: 'var(--text-secondary)' }}
        >
          Market Signals
        </h2>

        <MarketSignalsEmpty onSendToARIA={handleSendToARIA} />
      </section>
    </div>
  );
}

function MarketSignalsEmpty({ onSendToARIA }: { onSendToARIA: (msg: string) => void }) {
  return (
    <div
      className="p-8 rounded-lg border text-center"
      style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
    >
      <Newspaper size={32} strokeWidth={1} style={{ color: 'var(--text-muted)', margin: '0 auto 12px' }} />
      <p className="font-sans text-sm mb-3" style={{ color: 'var(--text-secondary)' }}>
        No market signals detected yet.
      </p>
      <p className="font-sans text-xs" style={{ color: 'var(--text-muted)' }}>
        ARIA will surface competitor news, earnings, and industry signals here.
      </p>
    </div>
  );
}

function IntelligenceSkeleton() {
  return (
    <div className="flex-1 overflow-y-auto p-8 animate-pulse">
      <div className="h-8 w-64 rounded mb-2" style={{ backgroundColor: 'var(--bg-subtle)' }} />
      <div className="h-4 w-96 rounded mb-8" style={{ backgroundColor: 'var(--bg-subtle)' }} />
      <div className="h-4 w-24 rounded mb-4" style={{ backgroundColor: 'var(--bg-subtle)' }} />
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-36 rounded-lg" style={{ backgroundColor: 'var(--bg-subtle)' }} />
        ))}
      </div>
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/pages/IntelligencePage.tsx frontend/src/components/intelligence/
git commit -m "feat: implement IntelligencePage with battle cards grid"
```

---

## Task 5: Build BattleCardDetail

**Files:**
- Create: `frontend/src/components/pages/BattleCardDetail.tsx`

**Step 1: Create BattleCardDetail component**

```tsx
// frontend/src/components/pages/BattleCardDetail.tsx
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  ChevronDown,
  ChevronRight,
  Zap,
  Target,
  Clock,
  Shield,
  CheckCircle2,
  XCircle,
  CircleCheck,
  AlertCircle,
  Newspaper,
  Radio,
  MessageSquare,
} from 'lucide-react';
import { useBattleCard } from '@/hooks/useBattleCards';
import { CopyButton, EmptyState } from '@/components/common';

interface BattleCardDetailProps {
  competitorName: string;
}

export function BattleCardDetail({ competitorName }: BattleCardDetailProps) {
  const navigate = useNavigate();
  const { data: battleCard, isLoading } = useBattleCard(competitorName);

  if (isLoading) {
    return <BattleCardDetailSkeleton />;
  }

  if (!battleCard) {
    return (
      <div className="flex-1 overflow-y-auto">
        <EmptyState
          title="Battle card not found"
          description={`ARIA hasn't created a battle card for ${competitorName} yet.`}
          suggestion="Research this competitor"
          onSuggestion={() => {
            // TODO: Send to ARIA
            console.log('Research:', competitorName);
          }}
        />
      </div>
    );
  }

  // Mock data for display (would come from enhanced API)
  const metrics = {
    marketCapGap: -890,
    winRate: 62,
    pricingDelta: 18,
    lastSignalDays: 2,
  };

  const howToWin = [
    {
      icon: Zap,
      title: 'Strength',
      content: `Lead with our fill-finish speed — 40% faster than ${competitorName}'s operations.`,
    },
    {
      icon: Target,
      title: 'Positioning',
      content: `When they mention scale, emphasize flexibility and responsiveness.`,
    },
    {
      icon: Clock,
      title: 'Quick Win',
      content: 'Offer pilot program for first 90 days to reduce risk.',
    },
    {
      icon: Shield,
      title: 'Defense',
      content: 'Counter their pricing argument with TCO analysis.',
    },
  ];

  const featureGaps = [
    { feature: 'Sterile Manufacturing', aria: 92, competitor: 100 },
    { feature: 'Fill-Finish Speed', aria: 100, competitor: 75 },
    { feature: 'Cold Chain Capacity', aria: 60, competitor: 90 },
    { feature: 'Regulatory Expertise', aria: 85, competitor: 90 },
  ];

  const criticalGaps = {
    advantages: [
      'Faster fill-finish turnaround (40% improvement)',
      'More flexible batch sizes',
      'Dedicated project managers',
    ],
    gaps: [
      'Larger cold chain capacity',
      'Longer FDA track record',
    ],
  };

  return (
    <div className="flex-1 overflow-y-auto p-8">
      {/* Back button */}
      <button
        onClick={() => navigate('/intelligence')}
        className="flex items-center gap-2 mb-6 font-sans text-sm transition-colors duration-150"
        style={{ color: 'var(--text-secondary)' }}
        onMouseEnter={(e) => {
          e.currentTarget.style.color = 'var(--text-primary)';
        }}
        onMouseLeave={(e) => {
          e.currentTarget.style.color = 'var(--text-secondary)';
        }}
      >
        <ArrowLeft size={16} />
        Back to Intelligence
      </button>

      {/* Header */}
      <div className="flex items-center justify-between mb-6">
        <h1
          className="font-display text-2xl italic"
          style={{ color: 'var(--text-primary)' }}
        >
          Battle Cards: Competitor Analysis
        </h1>
        <CompetitorDropdown current={competitorName} />
      </div>

      {/* Metrics Bar */}
      <div
        className="grid grid-cols-4 gap-4 p-4 rounded-lg mb-8"
        style={{ backgroundColor: 'var(--bg-subtle)' }}
      >
        <MetricCard
          label="Market Cap Gap"
          value={`$${Math.abs(metrics.marketCapGap)}M`}
          delta={metrics.marketCapGap < 0 ? 'Competitor smaller' : 'Competitor larger'}
          isPositive={metrics.marketCapGap < 0}
        />
        <MetricCard
          label="Win Rate"
          value={`${metrics.winRate}%`}
          delta="+5%"
          isPositive={true}
        />
        <MetricCard
          label="Pricing Delta"
          value={`+${metrics.pricingDelta}%`}
          delta="(higher)"
          isPositive={false}
        />
        <MetricCard
          label="Last Signal"
          value={`${metrics.lastSignalDays} days`}
          delta="ago"
          isPositive={null}
        />
      </div>

      {/* How to Win */}
      <Section
        title="How to Win"
        updatedBy="Strategist"
        updatedAt="1d ago"
      >
        <div className="grid grid-cols-2 gap-4">
          {howToWin.map((item, index) => (
            <div
              key={index}
              className="p-4 rounded-lg border"
              style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
            >
              <div className="flex items-center gap-2 mb-2">
                <item.icon size={16} style={{ color: 'var(--accent-primary)' }} />
                <span className="font-sans text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                  {item.title}
                </span>
              </div>
              <p className="font-sans text-sm" style={{ color: 'var(--text-secondary)' }}>
                "{item.content}"
              </p>
            </div>
          ))}
        </div>
      </Section>

      {/* Feature Gap Analysis */}
      <Section
        title="Feature Gap Analysis"
        updatedBy="Analyst"
        updatedAt="6h ago"
      >
        <div className="space-y-4">
          {featureGaps.map((gap, index) => {
            const ariaLeads = gap.aria > gap.competitor;
            return (
              <div key={index} data-aria-id={`feature-gap-${gap.feature.toLowerCase().replace(/\s+/g, '-')}`}>
                <div className="flex items-center justify-between mb-1">
                  <span className="font-sans text-sm" style={{ color: 'var(--text-primary)' }}>
                    {gap.feature}
                  </span>
                  {ariaLeads ? (
                    <CircleCheck size={14} style={{ color: 'var(--success)' }} />
                  ) : (
                    <AlertCircle size={14} style={{ color: 'var(--warning)' }} />
                  )}
                </div>
                <div className="flex items-center gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-sans text-[10px]" style={{ color: 'var(--text-muted)' }}>ARIA</span>
                      <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ backgroundColor: 'rgba(46, 102, 255, 0.1)' }}>
                        <div
                          className="h-full rounded-full"
                          style={{ width: `${gap.aria}%`, backgroundColor: '#2E66FF' }}
                        />
                      </div>
                      <span className="font-mono text-[10px] tabular-nums w-8" style={{ color: 'var(--text-secondary)' }}>
                        {gap.aria}%
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="font-sans text-[10px]" style={{ color: 'var(--text-muted)' }}>{competitorName}</span>
                      <div className="flex-1 h-2 rounded-full overflow-hidden" style={{ backgroundColor: 'rgba(100, 116, 139, 0.1)' }}>
                        <div
                          className="h-full rounded-full"
                          style={{ width: `${gap.competitor}%`, backgroundColor: '#64748B' }}
                        />
                      </div>
                      <span className="font-mono text-[10px] tabular-nums w-8" style={{ color: 'var(--text-secondary)' }}>
                        {gap.competitor}%
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </Section>

      {/* Critical Gaps */}
      <Section
        title="Critical Gaps"
        updatedBy="Scout"
        updatedAt="3h ago"
      >
        <div className="space-y-6">
          {/* Advantages */}
          <div>
            <h4 className="font-sans text-xs font-medium uppercase tracking-wider mb-3" style={{ color: 'var(--success)' }}>
              ARIA Advantages
            </h4>
            <div className="space-y-2">
              {criticalGaps.advantages.map((advantage, index) => (
                <div key={index} data-aria-id={`critical-gap-${index}`} className="flex items-start gap-2">
                  <CheckCircle2 size={16} className="mt-0.5 flex-shrink-0" style={{ color: 'var(--success)' }} />
                  <span className="font-sans text-sm" style={{ color: 'var(--text-primary)' }}>
                    {advantage}
                  </span>
                </div>
              ))}
            </div>
          </div>

          {/* Gaps */}
          <div>
            <h4 className="font-sans text-xs font-medium uppercase tracking-wider mb-3" style={{ color: 'var(--warning)' }}>
              Competitor Advantages
            </h4>
            <div className="space-y-2">
              {criticalGaps.gaps.map((gap, index) => (
                <div key={index} className="flex items-start gap-2">
                  <XCircle size={16} className="mt-0.5 flex-shrink-0" style={{ color: 'var(--warning)' }} />
                  <span className="font-sans text-sm" style={{ color: 'var(--text-primary)' }}>
                    {gap}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </Section>

      {/* Objection Handling */}
      <Section
        title="Objection Handling"
        updatedBy="Strategist"
        updatedAt="1d ago"
      >
        <div className="space-y-2">
          {battleCard.objection_handlers?.map((handler, index) => (
            <ObjectionAccordion
              key={index}
              data-aria-id={`objection-${index}`}
              objection={handler.objection}
              response={handler.response}
            />
          ))}
          {(!battleCard.objection_handlers || battleCard.objection_handlers.length === 0) && (
            <p className="font-sans text-sm italic" style={{ color: 'var(--text-muted)' }}>
              No objection handlers defined yet.
            </p>
          )}
        </div>
      </Section>
    </div>
  );
}

function MetricCard({
  label,
  value,
  delta,
  isPositive,
}: {
  label: string;
  value: string;
  delta: string;
  isPositive: boolean | null;
}) {
  return (
    <div className="text-center">
      <span className="font-sans text-[10px] uppercase tracking-wider block mb-1" style={{ color: 'var(--text-muted)' }}>
        {label}
      </span>
      <span className="font-mono text-lg font-medium block" style={{ color: 'var(--text-primary)' }}>
        {value}
      </span>
      <span
        className="font-sans text-[10px]"
        style={{
          color: isPositive === null
            ? 'var(--text-muted)'
            : isPositive
              ? 'var(--success)'
              : 'var(--critical)',
        }}
      >
        {delta}
      </span>
    </div>
  );
}

function Section({
  title,
  updatedBy,
  updatedAt,
  children,
}: {
  title: string;
  updatedBy: string;
  updatedAt: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-8">
      <div className="flex items-center justify-between mb-4">
        <h2
          className="font-sans text-sm font-medium uppercase tracking-wider"
          style={{ color: 'var(--text-primary)' }}
        >
          {title}
        </h2>
        <span className="font-mono text-[10px]" style={{ color: 'var(--text-muted)' }}>
          Updated by {updatedBy}, {updatedAt}
        </span>
      </div>
      {children}
    </section>
  );
}

function ObjectionAccordion({
  objection,
  response,
  ...props
}: {
  objection: string;
  response: string;
} & React.HTMLAttributes<HTMLDivElement>) {
  const [isOpen, setIsOpen] = useState(false);

  return (
    <div
      {...props}
      className="border rounded-lg overflow-hidden"
      style={{ borderColor: 'var(--border)' }}
    >
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full flex items-center justify-between p-4 text-left transition-colors duration-150"
        style={{ backgroundColor: isOpen ? 'var(--bg-subtle)' : 'transparent' }}
      >
        <span className="font-sans text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          "{objection}"
        </span>
        {isOpen ? (
          <ChevronDown size={16} style={{ color: 'var(--text-muted)' }} />
        ) : (
          <ChevronRight size={16} style={{ color: 'var(--text-muted)' }} />
        )}
      </button>
      {isOpen && (
        <div
          className="px-4 pb-4 pt-0"
          style={{ backgroundColor: 'var(--bg-subtle)' }}
        >
          <div className="flex items-start justify-between gap-4">
            <p
              className="font-sans text-sm italic flex-1"
              style={{ color: 'var(--text-secondary)' }}
            >
              "{response}"
            </p>
            <CopyButton text={response} />
          </div>
        </div>
      )}
    </div>
  );
}

function CompetitorDropdown({ current }: { current: string }) {
  // Mock competitors list (would come from useBattleCards)
  const competitors = [
    { name: 'Lonza', winRate: 62 },
    { name: 'Catalent', winRate: 48 },
    { name: 'WuXi Biologics', winRate: 71 },
    { name: 'Samsung Biologics', winRate: 35 },
  ];

  const getWinRateColor = (rate: number): string => {
    if (rate >= 60) return 'var(--success)';
    if (rate >= 40) return 'var(--warning)';
    return 'var(--critical)';
  };

  return (
    <select
      value={current}
      onChange={(e) => {
        window.location.href = `/intelligence/battle-cards/${encodeURIComponent(e.target.value)}`;
      }}
      className="px-3 py-2 rounded-lg font-sans text-sm"
      style={{
        backgroundColor: 'var(--bg-subtle)',
        border: '1px solid var(--border)',
        color: 'var(--text-primary)',
      }}
    >
      {competitors.map((c) => (
        <option key={c.name} value={c.name}>
          {c.name} ({c.winRate}%)
        </option>
      ))}
    </select>
  );
}

function BattleCardDetailSkeleton() {
  return (
    <div className="flex-1 overflow-y-auto p-8 animate-pulse">
      <div className="h-4 w-24 rounded mb-6" style={{ backgroundColor: 'var(--bg-subtle)' }} />
      <div className="h-8 w-64 rounded mb-6" style={{ backgroundColor: 'var(--bg-subtle)' }} />
      <div className="h-24 rounded-lg mb-8" style={{ backgroundColor: 'var(--bg-subtle)' }} />
      {[1, 2, 3, 4].map((i) => (
        <div key={i} className="mb-8">
          <div className="h-4 w-32 rounded mb-4" style={{ backgroundColor: 'var(--bg-subtle)' }} />
          <div className="h-32 rounded-lg" style={{ backgroundColor: 'var(--bg-subtle)' }} />
        </div>
      ))}
    </div>
  );
}
```

**Step 2: Commit**

```bash
git add frontend/src/components/pages/BattleCardDetail.tsx
git commit -m "feat: implement BattleCardDetail with feature gaps and objection handling"
```

---

## Task 6: Update Routes

**Files:**
- Modify: `frontend/src/app/routes.tsx`

**Step 1: Update routes to use new detail pages**

The routes are already configured, but we need to ensure LeadDetailPage and BattleCardDetail are used correctly.

Current routes already map:
- `/pipeline/leads/:leadId` → PipelinePage (which now delegates to LeadDetailPage)
- `/intelligence/battle-cards/:competitorId` → IntelligencePage (which now delegates to BattleCardDetail)

No route changes needed — the components handle the delegation internally.

**Step 2: Commit (if any changes)**

```bash
git status
# If routes.tsx was modified:
git add frontend/src/app/routes.tsx
git commit -m "refactor: routes already configured for detail pages"
```

---

## Task 7: Update Exports

**Files:**
- Modify: `frontend/src/components/pages/index.ts`

**Step 1: Export new pages**

```tsx
// frontend/src/components/pages/index.ts
export { PipelinePage } from './PipelinePage';
export { LeadDetailPage } from './LeadDetailPage';
export { IntelligencePage } from './IntelligencePage';
export { BattleCardDetail } from './BattleCardDetail';
export { CommunicationsPage } from './CommunicationsPage';
export { ActionsPage } from './ActionsPage';
export { SettingsPage } from './SettingsPage';
export { ARIAWorkspace } from './ARIAWorkspace';
```

**Step 2: Commit**

```bash
git add frontend/src/components/pages/index.ts
git commit -m "feat: export new page components"
```

---

## Task 8: Final Verification

**Step 1: Run type check**

```bash
cd frontend && npm run typecheck
```

Expected: No TypeScript errors

**Step 2: Run lint**

```bash
cd frontend && npm run lint
```

Expected: No lint errors

**Step 3: Build**

```bash
cd frontend && npm run build
```

Expected: Build succeeds

**Step 4: Final commit (if any fixes)**

```bash
git add -A
git commit -m "fix: resolve type and lint errors in new pages"
```

---

## Summary

**Files Created:**
- `frontend/src/components/common/EmptyState.tsx`
- `frontend/src/components/common/CopyButton.tsx`
- `frontend/src/components/common/SortableHeader.tsx`
- `frontend/src/components/common/index.ts`
- `frontend/src/components/pipeline/HealthBar.tsx`
- `frontend/src/components/pipeline/LeadTable.tsx`
- `frontend/src/components/pipeline/index.ts`
- `frontend/src/components/intelligence/BattleCardPreview.tsx`
- `frontend/src/components/intelligence/index.ts`
- `frontend/src/components/pages/LeadDetailPage.tsx`
- `frontend/src/components/pages/BattleCardDetail.tsx`

**Files Modified:**
- `frontend/src/components/pages/PipelinePage.tsx`
- `frontend/src/components/pages/IntelligencePage.tsx`
- `frontend/src/components/pages/index.ts`

**Commits:** 12 commits (one per task step)
