/**
 * IntegrationsSection - Connected apps and integrations
 */

import { Link2, Check, ExternalLink } from 'lucide-react';
import { ComingSoonIndicator } from './ComingSoonIndicator';

interface Integration {
  id: string;
  name: string;
  description: string;
  icon: string;
  connected: boolean;
}

const INTEGRATIONS: Integration[] = [
  {
    id: 'salesforce',
    name: 'Salesforce',
    description: 'CRM sync for contacts and opportunities',
    icon: 'SF',
    connected: false,
  },
  {
    id: 'hubspot',
    name: 'HubSpot',
    description: 'Marketing automation and CRM',
    icon: 'HS',
    connected: false,
  },
  {
    id: 'google',
    name: 'Google Workspace',
    description: 'Gmail, Calendar, and Drive',
    icon: 'G',
    connected: false,
  },
  {
    id: 'linkedin',
    name: 'LinkedIn',
    description: 'Sales Navigator and messaging',
    icon: 'in',
    connected: false,
  },
];

export function IntegrationsSection() {
  return (
    <div
      className="border rounded-lg p-6"
      style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
    >
      <div className="flex items-center gap-2 mb-6">
        <Link2 className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
        <h3
          className="font-medium"
          style={{ color: 'var(--text-primary)' }}
        >
          Integrations
        </h3>
      </div>

      <div className="space-y-4">
        {/* Available integrations */}
        {INTEGRATIONS.map((integration) => (
          <div
            key={integration.id}
            className="flex items-center justify-between p-3 rounded-lg border"
            style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
          >
            <div className="flex items-center gap-3">
              <div
                className="w-10 h-10 rounded-lg flex items-center justify-center font-medium text-sm"
                style={{
                  backgroundColor: 'var(--bg-elevated)',
                  color: 'var(--text-primary)',
                }}
              >
                {integration.icon}
              </div>
              <div>
                <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                  {integration.name}
                </p>
                <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                  {integration.description}
                </p>
              </div>
            </div>

            {integration.connected ? (
              <div className="flex items-center gap-2">
                <span
                  className="flex items-center gap-1 text-xs"
                  style={{ color: 'var(--success)' }}
                >
                  <Check className="w-3.5 h-3.5" />
                  Connected
                </span>
                <button
                  className="text-xs px-2 py-1 rounded border"
                  style={{
                    borderColor: 'var(--border)',
                    color: 'var(--text-secondary)',
                  }}
                >
                  Manage
                </button>
              </div>
            ) : (
              <button
                className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg"
                style={{
                  backgroundColor: 'var(--accent)',
                  color: 'white',
                }}
              >
                <ExternalLink className="w-3 h-3" />
                Connect
              </button>
            )}
          </div>
        ))}

        {/* Coming Soon: Browser & OS Control */}
        <ComingSoonIndicator
          title="Browser & OS Control"
          description="Let ARIA navigate websites and control your desktop applications autonomously."
          availableDate="Q3 2026"
        />
      </div>
    </div>
  );
}
