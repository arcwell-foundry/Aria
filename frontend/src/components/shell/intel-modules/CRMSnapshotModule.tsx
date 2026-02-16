import { Database } from 'lucide-react';
import { useIntelLead, useIntelLeads, useIntelSyncStatus, useRouteContext, formatRelativeTime } from '@/hooks/useIntelPanelData';

interface CRMSnapshot {
  account: string;
  stage: string;
  amount: string;
  closeDate: string;
  lastActivity: string;
  owner: string;
}

function CRMSnapshotSkeleton() {
  return (
    <div className="space-y-2">
      <div className="h-3 w-24 rounded bg-[var(--border)] animate-pulse" />
      <div className="h-36 rounded-lg bg-[var(--border)] animate-pulse" />
    </div>
  );
}

function formatCurrency(value: number | null | undefined): string {
  if (value == null) return 'N/A';
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value);
}

export interface CRMSnapshotModuleProps {
  snapshot?: CRMSnapshot;
}

export function CRMSnapshotModule({ snapshot: propSnapshot }: CRMSnapshotModuleProps) {
  const { leadId, isLeadDetail } = useRouteContext();
  const { data: lead, isLoading: leadLoading } = useIntelLead(leadId);
  const { data: leads, isLoading: leadsLoading } = useIntelLeads();
  const { data: syncStatus } = useIntelSyncStatus();

  const isLoading = isLeadDetail ? leadLoading : leadsLoading;

  if (isLoading && !propSnapshot) return <CRMSnapshotSkeleton />;

  let snapshot: CRMSnapshot;
  if (propSnapshot) {
    snapshot = propSnapshot;
  } else if (isLeadDetail && lead) {
    const lastSync = syncStatus?.find((s) => s.integration_type === (lead.crm_provider ?? 'salesforce'));
    snapshot = {
      account: lead.company_name,
      stage: lead.lifecycle_stage.charAt(0).toUpperCase() + lead.lifecycle_stage.slice(1),
      amount: formatCurrency(lead.expected_value),
      closeDate: lead.expected_close_date
        ? new Date(lead.expected_close_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
        : 'Not set',
      lastActivity: lead.last_activity_at ? formatRelativeTime(lead.last_activity_at) : 'No activity',
      owner: lastSync ? `Synced ${lastSync.last_sync_status ?? 'N/A'}` : 'You',
    };
  } else if (leads && leads.length > 0) {
    const topLead = leads[0];
    snapshot = {
      account: topLead.company_name,
      stage: topLead.lifecycle_stage.charAt(0).toUpperCase() + topLead.lifecycle_stage.slice(1),
      amount: formatCurrency(topLead.expected_value),
      closeDate: topLead.expected_close_date
        ? new Date(topLead.expected_close_date).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
        : 'Not set',
      lastActivity: topLead.last_activity_at ? formatRelativeTime(topLead.last_activity_at) : 'No activity',
      owner: 'You',
    };
  } else {
    return (
      <div data-aria-id="intel-crm-snapshot" className="space-y-2">
        <h3
          className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
          style={{ color: 'var(--text-secondary)' }}
        >
          CRM Snapshot
        </h3>
        <div
          className="rounded-lg border p-4"
          style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
        >
          <p className="font-sans text-[12px]" style={{ color: 'var(--text-secondary)' }}>
            No CRM data available. Connect a CRM in Settings to see pipeline snapshots.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div data-aria-id="intel-crm-snapshot" className="space-y-2">
      <h3
        className="font-sans text-[11px] font-medium uppercase tracking-wider mb-3"
        style={{ color: 'var(--text-secondary)' }}
      >
        CRM Snapshot
      </h3>
      <div
        className="rounded-lg border p-3"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
      >
        <div className="flex items-center gap-2 mb-3">
          <Database size={14} style={{ color: 'var(--accent)' }} />
          <span className="font-sans text-[13px] font-medium" style={{ color: 'var(--text-primary)' }}>
            {snapshot.account}
          </span>
        </div>
        <div className="space-y-2">
          {[
            ['Stage', snapshot.stage],
            ['Amount', snapshot.amount],
            ['Close Date', snapshot.closeDate],
            ['Last Activity', snapshot.lastActivity],
            ['Owner', snapshot.owner],
          ].map(([label, value]) => (
            <div key={label} className="flex justify-between items-baseline">
              <span className="font-mono text-[10px] uppercase" style={{ color: 'var(--text-secondary)' }}>
                {label}
              </span>
              <span className="font-sans text-[12px]" style={{ color: 'var(--text-primary)' }}>
                {value}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
