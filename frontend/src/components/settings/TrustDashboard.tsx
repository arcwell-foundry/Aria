/**
 * TrustDashboard - Per-category trust visualization with history chart
 *
 * Shows trust scores per action category as progress bars with expandable
 * detail panels containing override controls. Renders a 30-day trust
 * history AreaChart at the bottom using Recharts.
 */

import { useEffect, useState } from 'react';
import { BarChart3, ChevronDown, ChevronRight, Sparkles, TrendingUp } from 'lucide-react';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { ProgressBar } from '@/components/primitives/ProgressBar';
import { useTrustStore } from '@/stores/trustStore';
import type { OverrideMode } from '@/api/trust';

const CATEGORY_LABELS: Record<string, string> = {
  research_analysis: 'Research & Analysis',
  email_drafting: 'Email Drafting',
  email_send: 'Email Sending',
  crm_update: 'CRM Updates',
  meeting_scheduling: 'Meeting Scheduling',
  pricing_proposals: 'Pricing Proposals',
  lead_gen: 'Lead Generation',
  meeting_prep: 'Meeting Preparation',
};

function getCategoryLabel(category: string): string {
  return CATEGORY_LABELS[category] || category.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function getVariant(score: number): 'success' | 'default' | 'warning' | 'error' {
  if (score >= 0.8) return 'success';
  if (score >= 0.6) return 'default';
  if (score >= 0.3) return 'warning';
  return 'error';
}

const OVERRIDE_OPTIONS: { value: OverrideMode; label: string; description: string }[] = [
  { value: 'aria_decides', label: 'Let ARIA decide', description: 'Trust-based autonomy' },
  { value: 'always_approve', label: 'Always approve', description: 'Approve every step' },
  { value: 'plan_approval', label: 'Plan approval', description: 'Approve plan, then auto-execute' },
  { value: 'notify_only', label: 'Notify only', description: 'Auto-execute, notify after' },
  { value: 'full_auto', label: 'Full auto', description: 'No approval needed' },
];

const CHANGE_TYPE_LABELS: Record<string, string> = {
  success: 'Success',
  failure: 'Failure',
  override: 'Override',
  manual: 'Manual',
};

function formatDate(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function formatTooltipDate(dateStr: string): string {
  const d = new Date(dateStr);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

interface CategoryRowProps {
  profile: {
    action_category: string;
    trust_score: number;
    successful_actions: number;
    failed_actions: number;
    override_count: number;
    approval_level_label: string;
    can_request_upgrade: boolean;
    override_mode: OverrideMode | null;
  };
  isExpanded: boolean;
  onToggle: () => void;
  onOverrideChange: (mode: OverrideMode) => void;
}

function CategoryRow({ profile, isExpanded, onToggle, onOverrideChange }: CategoryRowProps) {
  const currentMode = profile.override_mode || 'aria_decides';

  return (
    <div
      className="rounded-lg border transition-colors"
      style={{
        borderColor: isExpanded ? 'var(--accent)' : 'var(--border)',
        backgroundColor: 'var(--bg-subtle)',
      }}
    >
      {/* Clickable header */}
      <button
        type="button"
        onClick={onToggle}
        className="w-full text-left p-3.5 flex items-center gap-3"
      >
        <div className="shrink-0" style={{ color: 'var(--text-secondary)' }}>
          {isExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1.5">
            <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
              {getCategoryLabel(profile.action_category)}
            </span>
            {profile.can_request_upgrade && (
              <span
                className="inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded-full"
                style={{ backgroundColor: 'rgba(46,102,255,0.1)', color: 'var(--accent)' }}
              >
                <Sparkles className="w-2.5 h-2.5" />
                Upgrade available
              </span>
            )}
            <span
              className="ml-auto text-[11px] font-mono shrink-0"
              style={{ color: 'var(--text-secondary)' }}
            >
              {(profile.trust_score * 100).toFixed(0)}%
            </span>
          </div>

          <ProgressBar
            value={profile.trust_score * 100}
            variant={getVariant(profile.trust_score)}
            size="sm"
          />
        </div>
      </button>

      {/* Expanded detail panel */}
      {isExpanded && (
        <div
          className="px-3.5 pb-3.5 pt-0 border-t"
          style={{ borderColor: 'var(--border)' }}
        >
          {/* Stats row */}
          <div className="grid grid-cols-4 gap-3 py-3">
            <div>
              <p className="text-lg font-mono font-medium" style={{ color: 'var(--text-primary)' }}>
                {profile.successful_actions}
              </p>
              <p className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>Successes</p>
            </div>
            <div>
              <p className="text-lg font-mono font-medium" style={{ color: '#EF4444' }}>
                {profile.failed_actions}
              </p>
              <p className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>Failures</p>
            </div>
            <div>
              <p className="text-lg font-mono font-medium" style={{ color: 'var(--warning, #F59E0B)' }}>
                {profile.override_count}
              </p>
              <p className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>Overrides</p>
            </div>
            <div>
              <p className="text-xs font-medium pt-1" style={{ color: 'var(--text-primary)' }}>
                {profile.approval_level_label}
              </p>
              <p className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>Current level</p>
            </div>
          </div>

          {/* Override controls */}
          <div className="pt-2">
            <p className="text-xs font-medium mb-2" style={{ color: 'var(--text-secondary)' }}>
              Override autonomy for this category
            </p>
            <div className="space-y-1">
              {OVERRIDE_OPTIONS.map((opt) => (
                <label
                  key={opt.value}
                  className="flex items-center gap-2.5 px-2.5 py-1.5 rounded-md cursor-pointer transition-colors"
                  style={{
                    backgroundColor: currentMode === opt.value ? 'rgba(46,102,255,0.08)' : 'transparent',
                  }}
                >
                  <input
                    type="radio"
                    name={`override-${profile.action_category}`}
                    value={opt.value}
                    checked={currentMode === opt.value}
                    onChange={() => onOverrideChange(opt.value)}
                    className="accent-[var(--accent)]"
                  />
                  <div className="flex-1 min-w-0">
                    <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
                      {opt.label}
                    </span>
                    <span className="text-[11px] ml-2" style={{ color: 'var(--text-secondary)' }}>
                      {opt.description}
                    </span>
                  </div>
                </label>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

interface ChartTooltipProps {
  active?: boolean;
  payload?: Array<{
    value: number;
    payload: { recorded_at: string; change_type: string; action_category: string };
  }>;
}

function ChartTooltip({ active, payload }: ChartTooltipProps) {
  if (!active || !payload?.length) return null;
  const point = payload[0];
  return (
    <div
      className="px-3 py-2 rounded-lg border text-xs shadow-lg"
      style={{
        backgroundColor: 'var(--bg-elevated)',
        borderColor: 'var(--border)',
      }}
    >
      <p className="font-medium" style={{ color: 'var(--text-primary)' }}>
        Score: {(point.value * 100).toFixed(1)}%
      </p>
      <p style={{ color: 'var(--text-secondary)' }}>
        {CHANGE_TYPE_LABELS[point.payload.change_type] || point.payload.change_type}
        {' — '}
        {getCategoryLabel(point.payload.action_category)}
      </p>
      <p className="font-mono" style={{ color: 'var(--text-secondary)' }}>
        {formatTooltipDate(point.payload.recorded_at)}
      </p>
    </div>
  );
}

export function TrustDashboard() {
  const {
    profiles,
    history,
    selectedCategory,
    loading,
    historyLoading,
    error,
    fetchProfiles,
    fetchHistory,
    setOverride,
    selectCategory,
  } = useTrustStore();

  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);

  useEffect(() => {
    fetchProfiles();
    fetchHistory();
  }, [fetchProfiles, fetchHistory]);

  const toggleExpand = (category: string) => {
    setExpandedCategory((prev) => (prev === category ? null : category));
  };

  // Unique categories from history for filter tabs
  const historyCategories = [...new Set(history.map((h) => h.action_category))];

  if (loading && profiles.length === 0) {
    return (
      <div
        className="border rounded-lg p-6"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
      >
        <div className="flex items-center gap-2">
          <BarChart3 className="w-4 h-4 animate-pulse" style={{ color: 'var(--text-secondary)' }} />
          <span className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            Loading trust profiles...
          </span>
        </div>
      </div>
    );
  }

  if (profiles.length === 0 && !loading) {
    return null;
  }

  return (
    <div
      className="border rounded-lg p-6"
      style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-5">
        <BarChart3 className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
        <h3 className="font-medium" style={{ color: 'var(--text-primary)' }}>
          Per-Category Trust
        </h3>
        <span
          className="ml-auto text-[11px] font-mono px-2 py-0.5 rounded"
          style={{ backgroundColor: 'var(--bg-subtle)', color: 'var(--text-secondary)' }}
        >
          {profiles.length} {profiles.length === 1 ? 'category' : 'categories'}
        </span>
      </div>

      {error && (
        <div
          className="flex items-center gap-2 p-3 rounded-lg mb-4 text-sm"
          style={{ backgroundColor: 'rgba(239,68,68,0.1)', color: '#EF4444' }}
        >
          {error}
        </div>
      )}

      {/* Category rows */}
      <div className="space-y-2 mb-6">
        {profiles.map((profile) => (
          <CategoryRow
            key={profile.action_category}
            profile={profile}
            isExpanded={expandedCategory === profile.action_category}
            onToggle={() => toggleExpand(profile.action_category)}
            onOverrideChange={(mode) => setOverride(profile.action_category, mode)}
          />
        ))}
      </div>

      {/* Trust History Section */}
      {(history.length > 0 || historyLoading) && (
        <div
          className="border rounded-lg p-4"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
            <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
              Trust History
            </span>
            {historyLoading && (
              <span className="text-[11px]" style={{ color: 'var(--text-secondary)' }}>
                Loading...
              </span>
            )}
          </div>

          {/* Category filter tabs */}
          {historyCategories.length > 1 && (
            <div className="flex flex-wrap gap-1 mb-3">
              <button
                type="button"
                onClick={() => selectCategory(null)}
                className="text-[11px] font-medium px-2 py-1 rounded-md transition-colors"
                style={{
                  backgroundColor: selectedCategory === null ? 'rgba(46,102,255,0.15)' : 'transparent',
                  color: selectedCategory === null ? 'var(--accent)' : 'var(--text-secondary)',
                  border: `1px solid ${selectedCategory === null ? 'var(--accent)' : 'var(--border)'}`,
                }}
              >
                All
              </button>
              {historyCategories.map((cat) => (
                <button
                  key={cat}
                  type="button"
                  onClick={() => selectCategory(cat)}
                  className="text-[11px] font-medium px-2 py-1 rounded-md transition-colors"
                  style={{
                    backgroundColor: selectedCategory === cat ? 'rgba(46,102,255,0.15)' : 'transparent',
                    color: selectedCategory === cat ? 'var(--accent)' : 'var(--text-secondary)',
                    border: `1px solid ${selectedCategory === cat ? 'var(--accent)' : 'var(--border)'}`,
                  }}
                >
                  {getCategoryLabel(cat)}
                </button>
              ))}
            </div>
          )}

          {/* Recharts AreaChart */}
          {history.length > 0 ? (
            <div style={{ width: '100%', height: 180 }}>
              <ResponsiveContainer>
                <AreaChart data={history} margin={{ top: 5, right: 5, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="trustGradient" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="var(--accent)" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="var(--accent)" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
                  <XAxis
                    dataKey="recorded_at"
                    tickFormatter={formatDate}
                    tick={{ fontSize: 10, fill: 'var(--text-secondary)' }}
                    stroke="var(--border)"
                  />
                  <YAxis
                    domain={[0, 1]}
                    tickFormatter={(v: number) => `${(v * 100).toFixed(0)}%`}
                    tick={{ fontSize: 10, fill: 'var(--text-secondary)' }}
                    stroke="var(--border)"
                  />
                  <Tooltip content={<ChartTooltip />} />
                  <Area
                    type="monotone"
                    dataKey="trust_score"
                    stroke="var(--accent)"
                    strokeWidth={2}
                    fill="url(#trustGradient)"
                    dot={false}
                    activeDot={{
                      r: 4,
                      stroke: 'var(--accent)',
                      strokeWidth: 2,
                      fill: 'var(--bg-elevated)',
                    }}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            !historyLoading && (
              <p className="text-xs text-center py-6" style={{ color: 'var(--text-secondary)' }}>
                Trust history will appear here as ARIA takes actions.
              </p>
            )
          )}
        </div>
      )}
    </div>
  );
}
