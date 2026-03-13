/**
 * ApolloSettingsCard - Apollo.io B2B contact enrichment settings
 *
 * Shows Apollo configuration status, mode (BYOK vs LuminOne-provided),
 * and credit usage with a visual progress bar.
 */

import { useState, useEffect } from 'react';
import { Users, Check, AlertTriangle, Loader2, Settings, ExternalLink } from 'lucide-react';
import { apiClient } from '@/api/client';

type ApolloConfig = {
  is_configured: boolean;
  mode: 'byok' | 'luminone_provided' | 'unconfigured';
  monthly_credit_limit: number;
  credits_used: number;
  credits_remaining: number;
  billing_cycle_start: string | null;
  billing_cycle_end: string | null;
  has_byok_key: boolean;
};

async function fetchApolloConfig(): Promise<ApolloConfig> {
  const { data } = await apiClient.get<ApolloConfig>('/apollo/config');
  return data;
}

export function ApolloSettingsCard() {
  const [config, setConfig] = useState<ApolloConfig | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchApolloConfig()
      .then(setConfig)
      .catch((err) => setError(err.message))
      .finally(() => setIsLoading(false));
  }, []);

  if (isLoading) {
    return (
      <div
        className="flex items-center justify-between p-3 rounded-lg border"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-lg flex items-center justify-center"
            style={{ backgroundColor: 'var(--bg-elevated)' }}
          >
            <Loader2 className="w-5 h-5 animate-spin" style={{ color: 'var(--text-secondary)' }} />
          </div>
          <div>
            <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
              Apollo.io
            </p>
            <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
              Loading...
            </p>
          </div>
        </div>
      </div>
    );
  }

  if (error || !config) {
    return (
      <div
        className="flex items-center justify-between p-3 rounded-lg border"
        style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-subtle)' }}
      >
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-lg flex items-center justify-center"
            style={{ backgroundColor: 'var(--bg-elevated)' }}
          >
            <AlertTriangle className="w-5 h-5" style={{ color: 'var(--error, #ef4444)' }} />
          </div>
          <div>
            <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
              Apollo.io
            </p>
            <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
              Failed to load configuration
            </p>
          </div>
        </div>
      </div>
    );
  }

  const isConfigured = config.is_configured && config.mode !== 'unconfigured';
  const usagePercent = config.monthly_credit_limit > 0
    ? Math.min(100, (config.credits_used / config.monthly_credit_limit) * 100)
    : 0;
  const isLowCredits = usagePercent >= 80;

  return (
    <div
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
          <Users className="w-5 h-5" />
        </div>
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
              Apollo.io
            </p>
            <span
              className="text-xs px-1.5 py-0.5 rounded"
              style={{
                backgroundColor: config.mode === 'byok' ? 'var(--accent)' : 'var(--bg-elevated)',
                color: config.mode === 'byok' ? 'white' : 'var(--text-secondary)',
              }}
            >
              {config.mode === 'byok' ? 'BYOK' : 'LuminOne'}
            </span>
          </div>
          <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
            B2B contact enrichment for lead discovery
          </p>
          {isConfigured && (
            <div className="flex items-center gap-2 mt-1">
              <div
                className="flex-1 h-1.5 rounded-full overflow-hidden"
                style={{ backgroundColor: 'var(--bg-elevated)', maxWidth: '120px' }}
              >
                <div
                  className="h-full rounded-full transition-all duration-300"
                  style={{
                    width: `${usagePercent}%`,
                    backgroundColor: isLowCredits
                      ? 'var(--warning, #f59e0b)'
                      : 'var(--success)',
                  }}
                />
              </div>
              <span
                className="text-xs"
                style={{
                  color: isLowCredits
                    ? 'var(--warning, #f59e0b)'
                    : 'var(--text-secondary)',
                }}
              >
                {config.credits_used}/{config.monthly_credit_limit} credits
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Status + Actions */}
      {isConfigured ? (
        <div className="flex items-center gap-2">
          <span
            className="flex items-center gap-1 text-xs"
            style={{ color: 'var(--success)' }}
          >
            <Check className="w-3.5 h-3.5" />
            {config.has_byok_key ? 'Connected' : 'Active'}
          </span>
          <button
            onClick={() => {
              // TODO: Open Apollo settings modal
              window.open('/settings/integrations#apollo', '_self');
            }}
            className="flex items-center gap-1 text-xs px-2 py-1 rounded border"
            style={{
              borderColor: 'var(--border)',
              color: 'var(--text-secondary)',
            }}
          >
            <Settings className="w-3 h-3" />
            Settings
          </button>
        </div>
      ) : (
        <button
          onClick={() => {
            // TODO: Open Apollo configuration modal
            window.open('/settings/integrations#apollo', '_self');
          }}
          className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg"
          style={{
            backgroundColor: 'var(--accent)',
            color: 'white',
          }}
        >
          <ExternalLink className="w-3 h-3" />
          Configure
        </button>
      )}
    </div>
  );
}
