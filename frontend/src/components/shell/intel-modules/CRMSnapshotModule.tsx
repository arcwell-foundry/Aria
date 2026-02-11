import { Database } from 'lucide-react';

interface CRMSnapshot {
  account: string;
  stage: string;
  amount: string;
  closeDate: string;
  lastActivity: string;
  owner: string;
}

const PLACEHOLDER_SNAPSHOT: CRMSnapshot = {
  account: 'Lonza Group',
  stage: 'Proposal Sent',
  amount: '$450,000',
  closeDate: 'Mar 15, 2026',
  lastActivity: 'Email opened — 2 days ago',
  owner: 'You',
};

export interface CRMSnapshotModuleProps {
  snapshot?: CRMSnapshot;
}

export function CRMSnapshotModule({ snapshot = PLACEHOLDER_SNAPSHOT }: CRMSnapshotModuleProps) {
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
