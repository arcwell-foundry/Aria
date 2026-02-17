/**
 * AutonomySettings - Interactive ARIA trust level configuration
 *
 * Shows current autonomy tier with visual indicator (3-tier scale),
 * explanation of each tier, manual override (lower only),
 * action statistics, and recent action history.
 */

import { useEffect } from 'react';
import { Shield, Zap, Check, Lock, AlertTriangle } from 'lucide-react';
import { useAutonomyStore } from '@/stores/autonomyStore';
import { ComingSoonIndicator } from './ComingSoonIndicator';
import type { AutonomyTier } from '@/api/autonomy';

const TIERS: {
  id: AutonomyTier;
  name: string;
  description: string;
  detail: string;
}[] = [
  {
    id: 'guided',
    name: 'Guided',
    description: 'ARIA suggests actions, you approve everything',
    detail: 'All actions require your explicit approval before execution. Best for getting started.',
  },
  {
    id: 'assisted',
    name: 'Assisted',
    description: 'ARIA auto-executes low-risk actions',
    detail: 'Research, signal detection, and briefings run automatically. Email drafts and above need approval.',
  },
  {
    id: 'autonomous',
    name: 'Autonomous',
    description: 'ARIA manages most tasks independently',
    detail: 'Low and medium-risk actions (including email drafts, meeting prep) run automatically. Only high-risk actions need approval.',
  },
];

const RISK_COLORS: Record<string, string> = {
  low: 'var(--success)',
  medium: 'var(--warning, #F59E0B)',
  high: '#EF4444',
  critical: '#DC2626',
};

const STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  completed: { bg: 'rgba(34,197,94,0.1)', text: 'var(--success)' },
  auto_approved: { bg: 'rgba(34,197,94,0.1)', text: 'var(--success)' },
  approved: { bg: 'rgba(59,130,246,0.1)', text: 'var(--accent)' },
  pending: { bg: 'rgba(245,158,11,0.1)', text: 'var(--warning, #F59E0B)' },
  rejected: { bg: 'rgba(239,68,68,0.1)', text: '#EF4444' },
  failed: { bg: 'rgba(239,68,68,0.1)', text: '#EF4444' },
  executing: { bg: 'rgba(59,130,246,0.1)', text: 'var(--accent)' },
};

function formatTimeAgo(dateStr: string): string {
  const now = new Date();
  const date = new Date(dateStr);
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  return `${diffDays}d ago`;
}

export function AutonomySettings() {
  const {
    currentTier,
    recommendedTier,
    canSelectTiers,
    stats,
    recentActions,
    loading,
    error,
    fetchStatus,
    setTier,
  } = useAutonomyStore();

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const activeTierIndex = TIERS.findIndex((t) => t.id === currentTier);

  return (
    <div
      className="border rounded-lg p-6"
      style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
    >
      {/* Header */}
      <div className="flex items-center gap-2 mb-6">
        <Shield className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
        <h3 className="font-medium" style={{ color: 'var(--text-primary)' }}>
          Autonomy Level
        </h3>
        {recommendedTier && currentTier !== recommendedTier && (
          <span
            className="ml-auto text-xs px-2 py-0.5 rounded"
            style={{ backgroundColor: 'rgba(46,102,255,0.1)', color: 'var(--accent)' }}
          >
            ARIA recommends: {TIERS.find((t) => t.id === recommendedTier)?.name}
          </span>
        )}
      </div>

      {error && (
        <div
          className="flex items-center gap-2 p-3 rounded-lg mb-4 text-sm"
          style={{ backgroundColor: 'rgba(239,68,68,0.1)', color: '#EF4444' }}
        >
          <AlertTriangle className="w-4 h-4 shrink-0" />
          {error}
        </div>
      )}

      <div className="space-y-6">
        {/* Visual step indicator */}
        <div className="flex items-center gap-1">
          {TIERS.map((tier, i) => {
            const isActive = i <= activeTierIndex;
            const isCurrent = tier.id === currentTier;
            return (
              <div key={tier.id} className="flex-1 flex flex-col items-center gap-2">
                <div className="w-full flex items-center">
                  {i > 0 && (
                    <div
                      className="flex-1 h-0.5"
                      style={{
                        backgroundColor: isActive ? 'var(--accent)' : 'var(--border)',
                      }}
                    />
                  )}
                  <div
                    className="w-8 h-8 rounded-full flex items-center justify-center shrink-0 transition-colors"
                    style={{
                      backgroundColor: isCurrent ? 'var(--accent)' : isActive ? 'rgba(46,102,255,0.2)' : 'var(--bg-subtle)',
                      border: isCurrent ? 'none' : `1px solid ${isActive ? 'var(--accent)' : 'var(--border)'}`,
                    }}
                  >
                    {isCurrent ? (
                      <Check className="w-4 h-4 text-white" />
                    ) : (
                      <span
                        className="text-xs font-mono"
                        style={{ color: isActive ? 'var(--accent)' : 'var(--text-secondary)' }}
                      >
                        {i + 1}
                      </span>
                    )}
                  </div>
                  {i < TIERS.length - 1 && (
                    <div
                      className="flex-1 h-0.5"
                      style={{
                        backgroundColor: i < activeTierIndex ? 'var(--accent)' : 'var(--border)',
                      }}
                    />
                  )}
                </div>
                <span
                  className="text-xs font-medium"
                  style={{ color: isCurrent ? 'var(--accent)' : 'var(--text-secondary)' }}
                >
                  {tier.name}
                </span>
              </div>
            );
          })}
        </div>

        {/* Tier selection cards */}
        <div className="space-y-2">
          {TIERS.map((tier) => {
            const isCurrent = tier.id === currentTier;
            const canSelect = canSelectTiers.includes(tier.id);
            const isDisabled = !canSelect && !isCurrent;

            return (
              <button
                key={tier.id}
                type="button"
                disabled={isDisabled || loading}
                onClick={() => {
                  if (canSelect && !isCurrent) setTier(tier.id);
                }}
                className="w-full text-left flex items-center justify-between p-4 rounded-lg border transition-colors"
                style={{
                  borderColor: isCurrent ? 'var(--accent)' : 'var(--border)',
                  backgroundColor: isCurrent ? 'rgba(46,102,255,0.05)' : 'var(--bg-subtle)',
                  opacity: isDisabled ? 0.5 : 1,
                  cursor: isDisabled ? 'not-allowed' : isCurrent ? 'default' : 'pointer',
                }}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1">
                    <p
                      className="text-sm font-medium"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      {tier.name}
                    </p>
                    {isCurrent && (
                      <span
                        className="px-1.5 py-0.5 rounded text-xs"
                        style={{ backgroundColor: 'var(--accent)', color: 'white' }}
                      >
                        Current
                      </span>
                    )}
                    {isDisabled && (
                      <Lock className="w-3 h-3" style={{ color: 'var(--text-secondary)' }} />
                    )}
                  </div>
                  <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                    {tier.description}
                  </p>
                  <p className="text-xs mt-1" style={{ color: 'var(--text-tertiary, var(--text-secondary))' }}>
                    {tier.detail}
                  </p>
                </div>
              </button>
            );
          })}
        </div>

        {/* Statistics */}
        {stats && (
          <div
            className="p-4 rounded-lg border"
            style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
          >
            <div className="flex items-center gap-2 mb-3">
              <Zap className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
              <span className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                Action Statistics
              </span>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <p className="text-2xl font-mono font-medium" style={{ color: 'var(--text-primary)' }}>
                  {stats.total_actions}
                </p>
                <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                  Total actions
                </p>
              </div>
              <div>
                <p className="text-2xl font-mono font-medium" style={{ color: 'var(--text-primary)' }}>
                  {Math.round(stats.approval_rate * 100)}%
                </p>
                <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                  Approval rate
                </p>
              </div>
              <div>
                <p className="text-2xl font-mono font-medium" style={{ color: 'var(--success)' }}>
                  {stats.auto_executed}
                </p>
                <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                  Auto-executed
                </p>
              </div>
              <div>
                <p className="text-2xl font-mono font-medium" style={{ color: '#EF4444' }}>
                  {stats.rejected}
                </p>
                <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                  Rejected
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Recent actions */}
        {recentActions.length > 0 && (
          <div>
            <p className="text-sm font-medium mb-3" style={{ color: 'var(--text-primary)' }}>
              Recent Actions
            </p>
            <div className="space-y-1.5">
              {recentActions.map((action) => {
                const statusStyle = STATUS_COLORS[action.status] || STATUS_COLORS.pending;
                return (
                  <div
                    key={action.id}
                    className="flex items-center gap-3 p-2.5 rounded-lg"
                    style={{ backgroundColor: 'var(--bg-subtle)' }}
                  >
                    <div
                      className="w-1.5 h-1.5 rounded-full shrink-0"
                      style={{ backgroundColor: RISK_COLORS[action.risk_level] || 'var(--text-secondary)' }}
                    />
                    <div className="flex-1 min-w-0">
                      <p
                        className="text-xs font-medium truncate"
                        style={{ color: 'var(--text-primary)' }}
                      >
                        {action.title}
                      </p>
                      <p className="text-[11px] font-mono" style={{ color: 'var(--text-secondary)' }}>
                        {action.agent} / {action.risk_level}
                      </p>
                    </div>
                    <span
                      className="text-[11px] px-1.5 py-0.5 rounded shrink-0"
                      style={{ backgroundColor: statusStyle.bg, color: statusStyle.text }}
                    >
                      {action.status.replace('_', ' ')}
                    </span>
                    <span
                      className="text-[11px] font-mono shrink-0"
                      style={{ color: 'var(--text-secondary)' }}
                    >
                      {formatTimeAgo(action.created_at)}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Coming Soon: Full Autonomy */}
        <ComingSoonIndicator
          title="Full Autonomy"
          description="Let ARIA operate independently, managing your entire workflow without approval."
          availableDate="Q3 2026"
        />
      </div>
    </div>
  );
}
