/**
 * StakeholderMapModule - KOL / Stakeholder map in Intel Panel
 *
 * Two contexts:
 * - Lead detail (leadId from route): shows AccountPlan stakeholder_summary
 *   with champion (green), decision maker (blue), key risk (red)
 * - Pipeline overview (no leadId): shows global stakeholders grouped
 *   by relationship_type with count badges
 *
 * Follows JarvisInsightsModule pattern:
 * - Skeleton loading, empty state, data-aria-id
 * - Dark theme (Intel Panel context)
 */

import { useParams } from 'react-router-dom';
import { Users, Crown, Briefcase, AlertTriangle } from 'lucide-react';
import { useAccountPlan } from '@/hooks/useAccounts';
import { useStakeholders } from '@/hooks/useStakeholders';
import type { RelationshipType } from '@/api/stakeholders';

const RELATIONSHIP_LABELS: Record<RelationshipType, string> = {
  champion: 'Champions',
  decision_maker: 'Decision Makers',
  influencer: 'Influencers',
  end_user: 'End Users',
  blocker: 'Blockers',
  other: 'Other',
};

const RELATIONSHIP_COLORS: Record<RelationshipType, string> = {
  champion: 'var(--success)',
  decision_maker: 'var(--accent)',
  influencer: 'var(--text-secondary)',
  end_user: 'var(--text-secondary)',
  blocker: 'var(--critical)',
  other: 'var(--text-secondary)',
};

function StakeholderMapSkeleton() {
  return (
    <div className="space-y-2">
      <div className="h-3 w-32 rounded bg-[var(--border)] animate-pulse" />
      <div className="space-y-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-14 rounded-lg bg-[var(--border)] animate-pulse" />
        ))}
      </div>
    </div>
  );
}

function LeadStakeholderView({ leadId }: { leadId: string }) {
  const { data: plan, isLoading } = useAccountPlan(leadId);

  if (isLoading) return <StakeholderMapSkeleton />;

  const summary = plan?.stakeholder_summary;
  const hasData = summary && (summary.champion || summary.decision_maker || summary.key_risk);

  if (!hasData) {
    return (
      <div data-aria-id="intel-stakeholder-map" className="space-y-2">
        <h3
          className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
          style={{ color: 'var(--text-secondary)' }}
        >
          Stakeholder Map
        </h3>
        <div
          className="rounded-lg border p-4"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <p className="font-sans text-[12px]" style={{ color: 'var(--text-secondary)' }}>
            ARIA is mapping stakeholders for this account.
          </p>
        </div>
      </div>
    );
  }

  const entries: Array<{ label: string; name: string; color: string; icon: typeof Crown }> = [];
  if (summary.champion) {
    entries.push({ label: 'Champion', name: summary.champion, color: 'var(--success)', icon: Crown });
  }
  if (summary.decision_maker) {
    entries.push({ label: 'Decision Maker', name: summary.decision_maker, color: 'var(--accent)', icon: Briefcase });
  }
  if (summary.key_risk) {
    entries.push({ label: 'Key Risk', name: summary.key_risk, color: 'var(--critical)', icon: AlertTriangle });
  }

  return (
    <div data-aria-id="intel-stakeholder-map" className="space-y-2">
      <h3
        className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
        style={{ color: 'var(--text-secondary)' }}
      >
        Stakeholder Map
      </h3>
      <div className="space-y-2">
        {entries.map((entry) => {
          const Icon = entry.icon;
          return (
            <div
              key={entry.label}
              className="rounded-lg border p-2.5"
              style={{
                borderColor: 'var(--border)',
                backgroundColor: 'var(--bg-subtle)',
                borderLeftWidth: '3px',
                borderLeftColor: entry.color,
              }}
            >
              <div className="flex items-center gap-2">
                <Icon size={14} className="flex-shrink-0" style={{ color: entry.color }} />
                <div className="min-w-0 flex-1">
                  <span
                    className="font-mono text-[10px] uppercase font-medium"
                    style={{ color: entry.color }}
                  >
                    {entry.label}
                  </span>
                  <p
                    className="font-sans text-[12px] truncate"
                    style={{ color: 'var(--text-primary)' }}
                  >
                    {entry.name}
                  </p>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function GlobalStakeholderView() {
  const { data: stakeholders, isLoading } = useStakeholders();

  if (isLoading) return <StakeholderMapSkeleton />;

  if (!stakeholders || stakeholders.length === 0) {
    return (
      <div data-aria-id="intel-stakeholder-map" className="space-y-2">
        <h3
          className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
          style={{ color: 'var(--text-secondary)' }}
        >
          Stakeholder Network
        </h3>
        <div
          className="rounded-lg border p-4"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <p className="font-sans text-[12px]" style={{ color: 'var(--text-secondary)' }}>
            ARIA is mapping your stakeholder network.
          </p>
        </div>
      </div>
    );
  }

  // Group by relationship_type
  const grouped: Partial<Record<RelationshipType, number>> = {};
  for (const s of stakeholders) {
    grouped[s.relationship_type] = (grouped[s.relationship_type] ?? 0) + 1;
  }

  return (
    <div data-aria-id="intel-stakeholder-map" className="space-y-2">
      <h3
        className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
        style={{ color: 'var(--text-secondary)' }}
      >
        Stakeholder Network
      </h3>
      <div
        className="rounded-lg border p-3"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
      >
        <div className="flex items-center gap-2 mb-2">
          <Users size={14} style={{ color: 'var(--text-secondary)' }} />
          <span
            className="font-mono text-[11px]"
            style={{ color: 'var(--text-secondary)' }}
          >
            {stakeholders.length} total
          </span>
        </div>
        <div className="space-y-1.5">
          {(Object.entries(grouped) as [RelationshipType, number][]).map(([type, count]) => (
            <div key={type} className="flex items-center justify-between">
              <span
                className="font-sans text-[12px]"
                style={{ color: 'var(--text-primary)' }}
              >
                {RELATIONSHIP_LABELS[type] ?? type}
              </span>
              <span
                className="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full font-mono text-[10px] font-medium"
                style={{
                  backgroundColor: `color-mix(in srgb, ${RELATIONSHIP_COLORS[type] ?? 'var(--text-secondary)'} 15%, transparent)`,
                  color: RELATIONSHIP_COLORS[type] ?? 'var(--text-secondary)',
                }}
              >
                {count}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function StakeholderMapModule() {
  const { leadId } = useParams<{ leadId: string }>();

  if (leadId) {
    return <LeadStakeholderView leadId={leadId} />;
  }

  return <GlobalStakeholderView />;
}
