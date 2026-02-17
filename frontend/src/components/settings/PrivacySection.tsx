/**
 * PrivacySection - Compliance Guardian in Settings
 *
 * Three cards:
 * 1. Consent Preferences - toggle switches for 4 consent categories
 * 2. Data Retention - read-only display of retention policies
 * 3. Data Management - export, delete, reset digital twin
 *
 * Follows existing settings section patterns (ProfileSection, BillingSection).
 * LIGHT THEME (content page context).
 */

import { useState } from 'react';
import { Shield, Download, Trash2, RotateCcw } from 'lucide-react';
import {
  useConsentStatus,
  useUpdateConsent,
  useRetentionPolicies,
  useRefreshDataExport,
  useDeleteUserData,
  useDeleteDigitalTwin,
} from '@/hooks/useCompliance';
import type { UpdateConsentRequest } from '@/api/compliance';

const CONSENT_LABELS: Record<string, { label: string; description: string }> = {
  email_analysis: {
    label: 'Email Analysis',
    description: 'Allow ARIA to analyze your email communications for intelligence',
  },
  document_learning: {
    label: 'Document Learning',
    description: 'Allow ARIA to learn from uploaded documents',
  },
  crm_processing: {
    label: 'CRM Processing',
    description: 'Allow ARIA to process CRM data for pipeline intelligence',
  },
  writing_style_learning: {
    label: 'Writing Style Learning',
    description: 'Allow ARIA to learn your writing style for draft generation',
  },
};

function ConsentToggle({
  category,
  granted,
  onToggle,
  isPending,
}: {
  category: string;
  granted: boolean;
  onToggle: (data: UpdateConsentRequest) => void;
  isPending: boolean;
}) {
  const info = CONSENT_LABELS[category];
  if (!info) return null;

  return (
    <div className="flex items-center justify-between py-3 border-b last:border-b-0" style={{ borderColor: 'var(--border)' }}>
      <div className="flex-1 mr-4">
        <p className="font-sans text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          {info.label}
        </p>
        <p className="font-sans text-xs mt-0.5" style={{ color: 'var(--text-secondary)' }}>
          {info.description}
        </p>
      </div>
      <button
        onClick={() => onToggle({ category: category as UpdateConsentRequest['category'], granted: !granted })}
        disabled={isPending}
        className="relative w-10 h-5 rounded-full transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-[var(--accent)]/30 cursor-pointer disabled:opacity-50"
        style={{ backgroundColor: granted ? 'var(--accent)' : 'var(--border)' }}
        role="switch"
        aria-checked={granted}
      >
        <span
          className="absolute top-0.5 w-4 h-4 rounded-full bg-white shadow-sm transition-transform duration-200"
          style={{ transform: granted ? 'translateX(22px)' : 'translateX(2px)' }}
        />
      </button>
    </div>
  );
}

function ConsentPreferencesCard() {
  const { data: consent, isLoading } = useConsentStatus();
  const updateMutation = useUpdateConsent();

  if (isLoading) {
    return (
      <div className="rounded-lg border p-5 animate-pulse" style={{ borderColor: 'var(--border)' }}>
        <div className="h-5 w-40 bg-[var(--border)] rounded mb-4" />
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex items-center justify-between py-3">
            <div className="h-4 w-48 bg-[var(--border)] rounded" />
            <div className="h-5 w-10 bg-[var(--border)] rounded-full" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="rounded-lg border p-5" style={{ borderColor: 'var(--border)' }}>
      <div className="flex items-center gap-2 mb-4">
        <Shield size={18} style={{ color: 'var(--accent)' }} />
        <h3 className="font-sans text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
          Consent Preferences
        </h3>
      </div>
      {consent && Object.entries(CONSENT_LABELS).map(([key]) => (
        <ConsentToggle
          key={key}
          category={key}
          granted={consent[key as keyof typeof consent] ?? false}
          onToggle={(data) => updateMutation.mutate(data)}
          isPending={updateMutation.isPending}
        />
      ))}
    </div>
  );
}

function DataRetentionCard() {
  const { data: policies, isLoading } = useRetentionPolicies();

  if (isLoading) {
    return (
      <div className="rounded-lg border p-5 animate-pulse" style={{ borderColor: 'var(--border)' }}>
        <div className="h-5 w-32 bg-[var(--border)] rounded mb-4" />
        <div className="space-y-3">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-4 w-64 bg-[var(--border)] rounded" />
          ))}
        </div>
      </div>
    );
  }

  if (!policies) return null;

  const policyEntries = [
    { key: 'audit_query_logs', label: 'Audit Query Logs' },
    { key: 'audit_write_logs', label: 'Audit Write Logs' },
    { key: 'email_data', label: 'Email Data' },
    { key: 'conversation_history', label: 'Conversation History' },
  ];

  return (
    <div className="rounded-lg border p-5" style={{ borderColor: 'var(--border)' }}>
      <h3 className="font-sans text-base font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
        Data Retention
      </h3>
      <div className="space-y-3">
        {policyEntries.map(({ key, label }) => {
          const policy = policies[key as keyof typeof policies];
          if (!policy || typeof policy !== 'object') return null;
          const policyObj = policy as Record<string, unknown>;
          return (
            <div key={key} className="flex items-center justify-between">
              <span className="font-sans text-sm" style={{ color: 'var(--text-primary)' }}>
                {label}
              </span>
              <span className="font-mono text-xs" style={{ color: 'var(--text-secondary)' }}>
                {policyObj.retention_days ? `${policyObj.retention_days} days` : 'Permanent'}
              </span>
            </div>
          );
        })}
      </div>
      {policies.note && (
        <p className="font-sans text-xs mt-3 pt-3 border-t" style={{ color: 'var(--text-secondary)', borderColor: 'var(--border)' }}>
          {policies.note}
        </p>
      )}
    </div>
  );
}

function DataManagementCard() {
  const [deleteConfirm, setDeleteConfirm] = useState(false);
  const [twinConfirm, setTwinConfirm] = useState(false);

  const exportMutation = useRefreshDataExport({
    onSuccess: () => {
      // Data export triggered successfully
    },
  });
  const deleteMutation = useDeleteUserData({
    onSuccess: () => setDeleteConfirm(false),
  });
  const twinMutation = useDeleteDigitalTwin({
    onSuccess: () => setTwinConfirm(false),
  });

  return (
    <div className="rounded-lg border p-5" style={{ borderColor: 'var(--border)' }}>
      <h3 className="font-sans text-base font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
        Data Management
      </h3>
      <div className="space-y-4">
        {/* Export */}
        <div className="flex items-center justify-between">
          <div>
            <p className="font-sans text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
              Export My Data
            </p>
            <p className="font-sans text-xs" style={{ color: 'var(--text-secondary)' }}>
              Download all your data in JSON format
            </p>
          </div>
          <button
            onClick={() => exportMutation.mutate()}
            disabled={exportMutation.isPending}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors border cursor-pointer disabled:opacity-50"
            style={{ borderColor: 'var(--border)', color: 'var(--text-primary)' }}
          >
            <Download size={14} />
            Export
          </button>
        </div>

        {/* Delete Data */}
        <div className="flex items-center justify-between">
          <div>
            <p className="font-sans text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
              Delete My Data
            </p>
            <p className="font-sans text-xs" style={{ color: 'var(--text-secondary)' }}>
              Permanently delete all your data
            </p>
          </div>
          {deleteConfirm ? (
            <div className="flex items-center gap-2">
              <button
                onClick={() => deleteMutation.mutate({ confirmation: 'DELETE_MY_DATA' })}
                disabled={deleteMutation.isPending}
                className="px-3 py-1.5 rounded-md text-sm font-medium cursor-pointer disabled:opacity-50"
                style={{ backgroundColor: 'var(--critical)', color: 'white' }}
              >
                Confirm
              </button>
              <button
                onClick={() => setDeleteConfirm(false)}
                className="px-3 py-1.5 rounded-md text-sm font-medium border cursor-pointer"
                style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setDeleteConfirm(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors border cursor-pointer"
              style={{ borderColor: 'var(--critical)', color: 'var(--critical)' }}
            >
              <Trash2 size={14} />
              Delete
            </button>
          )}
        </div>

        {/* Reset Digital Twin */}
        <div className="flex items-center justify-between">
          <div>
            <p className="font-sans text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
              Reset Digital Twin
            </p>
            <p className="font-sans text-xs" style={{ color: 'var(--text-secondary)' }}>
              Reset ARIA&apos;s learned model of your style and preferences
            </p>
          </div>
          {twinConfirm ? (
            <div className="flex items-center gap-2">
              <button
                onClick={() => twinMutation.mutate()}
                disabled={twinMutation.isPending}
                className="px-3 py-1.5 rounded-md text-sm font-medium cursor-pointer disabled:opacity-50"
                style={{ backgroundColor: 'var(--warning)', color: 'white' }}
              >
                Confirm
              </button>
              <button
                onClick={() => setTwinConfirm(false)}
                className="px-3 py-1.5 rounded-md text-sm font-medium border cursor-pointer"
                style={{ borderColor: 'var(--border)', color: 'var(--text-secondary)' }}
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              onClick={() => setTwinConfirm(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium transition-colors border cursor-pointer"
              style={{ borderColor: 'var(--warning)', color: 'var(--warning)' }}
            >
              <RotateCcw size={14} />
              Reset
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function PrivacySection() {
  return (
    <div className="space-y-6" data-aria-id="settings-privacy">
      <ConsentPreferencesCard />
      <DataRetentionCard />
      <DataManagementCard />
    </div>
  );
}
