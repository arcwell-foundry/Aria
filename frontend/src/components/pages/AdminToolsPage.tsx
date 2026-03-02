/** AdminToolsPage - Admin tool governance dashboard.
 *
 * Tabbed interface for managing toolkit catalog, configurations,
 * user requests, and audit trail.
 */

import { useState, useEffect, useCallback } from 'react';
import {
  getToolCatalog,
  getToolConfigs,
  getToolRequests,
  getToolAudit,
  createToolConfig,
  reviewToolRequest,
  type ToolkitCatalogItem,
  type ToolkitConfig,
  type AccessRequest,
  type AuditEntry,
} from '@/api/adminTools';

type Tab = 'catalog' | 'config' | 'requests' | 'audit';

const TAB_LABELS: Record<Tab, string> = {
  catalog: 'Catalog',
  config: 'Configured',
  requests: 'Requests',
  audit: 'Audit Log',
};

/* ------------------------------------------------------------------ */
/* Catalog Section                                                     */
/* ------------------------------------------------------------------ */

function CatalogSection() {
  const [items, setItems] = useState<ToolkitCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setItems(await getToolCatalog());
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const handleApprove = async (item: ToolkitCatalogItem) => {
    try {
      await createToolConfig({
        toolkit_slug: item.composio_app_name,
        display_name: item.composio_app_name.replace(/_/g, ' '),
        status: 'approved',
        category: item.capability_category,
      });
      void load();
    } catch {
      /* ignore */
    }
  };

  if (loading) return <LoadingPlaceholder />;

  if (items.length === 0) {
    return <EmptyState message="No toolkits available in the capability graph." />;
  }

  return (
    <div className="space-y-2">
      {items.map((item) => (
        <div
          key={item.composio_app_name}
          className="flex items-center justify-between rounded-lg p-3 border"
          style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
        >
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
              {item.composio_app_name.replace(/_/g, ' ')}
            </p>
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
              {item.capability_category} &middot; {item.provider_type} &middot; quality: {Math.round(item.quality_score * 100)}%
            </p>
          </div>
          <div className="shrink-0 ml-3">
            {item.org_status === 'approved' ? (
              <span
                className="text-xs px-2 py-1 rounded-full font-medium"
                style={{ background: 'var(--success)', color: '#fff', opacity: 0.9 }}
              >
                Approved
              </span>
            ) : item.org_status === 'denied' ? (
              <span
                className="text-xs px-2 py-1 rounded-full font-medium"
                style={{ background: 'var(--error)', color: '#fff', opacity: 0.9 }}
              >
                Denied
              </span>
            ) : (
              <button
                onClick={() => handleApprove(item)}
                className="text-xs px-3 py-1.5 rounded-lg font-medium transition-opacity hover:opacity-80"
                style={{ background: 'var(--accent)', color: '#fff' }}
              >
                Approve
              </button>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Config Section                                                      */
/* ------------------------------------------------------------------ */

function ConfigSection() {
  const [configs, setConfigs] = useState<ToolkitConfig[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void getToolConfigs()
      .then(setConfigs)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingPlaceholder />;

  if (configs.length === 0) {
    return <EmptyState message="No toolkits configured yet. Approve toolkits from the Catalog tab." />;
  }

  return (
    <div className="space-y-2">
      {configs.map((cfg) => (
        <div
          key={cfg.id}
          className="flex items-center justify-between rounded-lg p-3 border"
          style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
        >
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
              {cfg.display_name || cfg.toolkit_slug}
            </p>
            <p className="text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
              {cfg.category} &middot; seats: {cfg.current_seats ?? 0}
              {cfg.max_seats ? ` / ${cfg.max_seats}` : ''}
              {cfg.notes ? ` &middot; ${cfg.notes}` : ''}
            </p>
          </div>
          <StatusBadge status={cfg.status} />
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Requests Section                                                    */
/* ------------------------------------------------------------------ */

function RequestsSection() {
  const [requests, setRequests] = useState<AccessRequest[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setRequests(await getToolRequests());
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const handleReview = async (id: string, status: 'approved' | 'denied') => {
    try {
      await reviewToolRequest(id, { status });
      void load();
    } catch {
      /* ignore */
    }
  };

  if (loading) return <LoadingPlaceholder />;

  if (requests.length === 0) {
    return <EmptyState message="No tool access requests." />;
  }

  return (
    <div className="space-y-2">
      {requests.map((req) => (
        <div
          key={req.id}
          className="rounded-lg p-3 border"
          style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
        >
          <div className="flex items-start justify-between gap-3">
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                {req.toolkit_display_name || req.toolkit_slug}
              </p>
              {req.reason && (
                <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
                  Reason: {req.reason}
                </p>
              )}
              <p className="text-xs mt-0.5" style={{ color: 'var(--text-tertiary)' }}>
                {new Date(req.created_at).toLocaleDateString()}
              </p>
            </div>
            {req.status === 'pending' ? (
              <div className="flex gap-2 shrink-0">
                <button
                  onClick={() => handleReview(req.id, 'approved')}
                  className="text-xs px-3 py-1.5 rounded-lg font-medium transition-opacity hover:opacity-80"
                  style={{ background: 'var(--success)', color: '#fff' }}
                >
                  Approve
                </button>
                <button
                  onClick={() => handleReview(req.id, 'denied')}
                  className="text-xs px-3 py-1.5 rounded-lg font-medium transition-opacity hover:opacity-80"
                  style={{ background: 'var(--error)', color: '#fff' }}
                >
                  Deny
                </button>
              </div>
            ) : (
              <StatusBadge status={req.status} />
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Audit Section                                                       */
/* ------------------------------------------------------------------ */

function AuditSection() {
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void getToolAudit(100)
      .then(setEntries)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <LoadingPlaceholder />;

  if (entries.length === 0) {
    return <EmptyState message="No audit entries yet." />;
  }

  return (
    <div className="space-y-1">
      {entries.map((entry) => (
        <div
          key={entry.id}
          className="flex items-center gap-3 rounded-lg px-3 py-2"
          style={{ background: 'var(--surface)' }}
        >
          <span className="text-xs font-mono shrink-0" style={{ color: 'var(--text-tertiary)' }}>
            {new Date(entry.created_at).toLocaleString()}
          </span>
          <span className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            {entry.action}
          </span>
          <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
            {entry.toolkit_slug}
          </span>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Shared UI                                                           */
/* ------------------------------------------------------------------ */

function StatusBadge({ status }: { status: string }) {
  const colorVar =
    status === 'approved' ? 'var(--success)' :
    status === 'denied' ? 'var(--error)' :
    'var(--warning)';

  return (
    <span
      className="text-xs px-2 py-1 rounded-full font-medium shrink-0"
      style={{ background: colorVar, color: '#fff', opacity: 0.9 }}
    >
      {status}
    </span>
  );
}

function LoadingPlaceholder() {
  return (
    <div className="flex items-center justify-center py-12">
      <div
        className="h-8 w-8 rounded-full aria-breathe"
        style={{ backgroundColor: 'var(--accent)', opacity: 0.15 }}
      />
    </div>
  );
}

function EmptyState({ message }: { message: string }) {
  return (
    <div className="flex items-center justify-center py-12">
      <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>{message}</p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Page Component                                                      */
/* ------------------------------------------------------------------ */

const SECTIONS: Record<Tab, React.ComponentType> = {
  catalog: CatalogSection,
  config: ConfigSection,
  requests: RequestsSection,
  audit: AuditSection,
};

export function AdminToolsPage() {
  const [activeTab, setActiveTab] = useState<Tab>('catalog');
  const Section = SECTIONS[activeTab];

  return (
    <div
      className="min-h-screen"
      style={{ background: 'var(--background)', color: 'var(--text-primary)' }}
    >
      {/* Header */}
      <div className="border-b" style={{ borderColor: 'var(--border)' }}>
        <div className="max-w-5xl mx-auto px-6 py-5">
          <h1 className="text-lg font-semibold">Tool Governance</h1>
          <p className="text-sm mt-1" style={{ color: 'var(--text-secondary)' }}>
            Manage which integrations are available to your organization.
          </p>
        </div>
      </div>

      {/* Tab bar */}
      <div className="border-b" style={{ borderColor: 'var(--border)' }}>
        <div className="max-w-5xl mx-auto px-6 flex gap-1">
          {(Object.keys(TAB_LABELS) as Tab[]).map((tab) => (
            <button
              key={tab}
              onClick={() => setActiveTab(tab)}
              className="px-4 py-2.5 text-sm font-medium transition-colors relative"
              style={{
                color: activeTab === tab ? 'var(--text-primary)' : 'var(--text-secondary)',
              }}
            >
              {TAB_LABELS[tab]}
              {activeTab === tab && (
                <span
                  className="absolute bottom-0 left-0 right-0 h-0.5"
                  style={{ background: 'var(--accent)' }}
                />
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      <div className="max-w-5xl mx-auto px-6 py-6">
        <Section />
      </div>
    </div>
  );
}
