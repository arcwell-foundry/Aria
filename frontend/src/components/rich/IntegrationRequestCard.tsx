/**
 * IntegrationRequestCard — Inline integration connection prompt in conversation.
 *
 * Rendered when an agent needs an integration the user hasn't connected.
 * Shows integration name, benefit description, provider badges, and a
 * "Connect Now" CTA that navigates to settings.
 */

import { useState } from 'react';
import { Link2, ExternalLink, X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export interface IntegrationRequestData {
  integration: string;
  display_name: string;
  providers: string[];
  benefit: string;
  route: string;
  agent: string;
}

export function IntegrationRequestCard({ data }: { data: IntegrationRequestData }) {
  const [dismissed, setDismissed] = useState(false);
  const navigate = useNavigate();

  if (dismissed) {
    return (
      <div
        className="rounded-lg border px-3 py-2 text-xs"
        style={{
          borderColor: 'var(--border)',
          backgroundColor: 'var(--bg-subtle)',
          color: 'var(--text-secondary)',
        }}
      >
        Integration request dismissed
      </div>
    );
  }

  return (
    <div
      className="rounded-lg border overflow-hidden"
      style={{
        borderColor: 'var(--border)',
        backgroundColor: 'var(--bg-elevated)',
      }}
      data-aria-id="integration-request-card"
    >
      {/* Header */}
      <div
        className="flex items-center gap-2 px-4 py-2.5"
        style={{
          backgroundColor: 'rgba(46,102,255,0.05)',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <Link2 className="w-3.5 h-3.5" style={{ color: 'var(--accent)' }} />
        <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
          Integration Needed
        </span>
        <span
          className="ml-auto text-[11px] px-1.5 py-0.5 rounded font-mono uppercase tracking-wider"
          style={{ color: 'var(--text-secondary)' }}
        >
          {data.agent}
        </span>
      </div>

      {/* Body */}
      <div className="px-4 py-3">
        <p className="text-sm mb-1.5" style={{ color: 'var(--text-primary)' }}>
          Connect your {data.display_name} to {data.benefit}.
        </p>

        {/* Provider badges */}
        <div className="flex items-center gap-2 mb-3">
          {data.providers.map((provider) => (
            <span
              key={provider}
              className="text-[11px] px-2 py-0.5 rounded-full border"
              style={{
                borderColor: 'var(--border)',
                color: 'var(--text-secondary)',
              }}
            >
              {provider}
            </span>
          ))}
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => navigate(data.route)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white transition-opacity hover:opacity-90"
            style={{ backgroundColor: 'var(--accent)' }}
          >
            <ExternalLink className="w-3 h-3" />
            Connect Now
          </button>
          <button
            type="button"
            onClick={() => setDismissed(true)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium border transition-opacity hover:opacity-90"
            style={{
              borderColor: 'var(--border)',
              color: 'var(--text-secondary)',
              backgroundColor: 'transparent',
            }}
          >
            <X className="w-3 h-3" />
            Not Now
          </button>
        </div>
      </div>
    </div>
  );
}
