/**
 * IntegrationsSection - Connected apps and integrations
 *
 * Wires real connection status from the backend via useAvailableIntegrations,
 * and provides OAuth connect/reconnect/disconnect flows.
 */

import { useState, useEffect, useCallback } from 'react';
import { Link2, Check, ExternalLink, Loader2, AlertTriangle, X } from 'lucide-react';
import { ComingSoonIndicator } from './ComingSoonIndicator';
import {
  useAvailableIntegrations,
  useGetAuthUrl,
  useConnectIntegration,
  useDisconnectIntegration,
} from '@/hooks/useIntegrations';
import type { IntegrationType } from '@/api/integrations';

type IntegrationCardConfig = {
  id: string;
  name: string;
  description: string;
  icon: string;
  comingSoon?: false;
  primaryType: IntegrationType;
} | {
  id: string;
  name: string;
  description: string;
  icon: string;
  comingSoon: true;
  primaryType?: undefined;
};

const INTEGRATION_CARDS: IntegrationCardConfig[] = [
  {
    id: 'microsoft365',
    name: 'Microsoft 365',
    description: 'Email, Calendar, and OneDrive',
    icon: 'M365',
    primaryType: 'outlook',
  },
  {
    id: 'google',
    name: 'Google Workspace',
    description: 'Gmail, Calendar, and Drive',
    icon: 'G',
    primaryType: 'gmail',
  },
  {
    id: 'salesforce',
    name: 'Salesforce',
    description: 'CRM sync for contacts and opportunities',
    icon: 'SF',
    primaryType: 'salesforce',
  },
  {
    id: 'hubspot',
    name: 'HubSpot',
    description: 'Marketing automation and CRM',
    icon: 'HS',
    primaryType: 'hubspot',
  },
  {
    id: 'linkedin',
    name: 'LinkedIn',
    description: 'Sales Navigator and messaging',
    icon: 'in',
    comingSoon: true,
  },
];

const PENDING_INTEGRATION_KEY = 'aria_pending_integration_type';

export function IntegrationsSection() {
  const { data: availableIntegrations, isLoading } = useAvailableIntegrations();
  const getAuthUrl = useGetAuthUrl();
  const connectMutation = useConnectIntegration();
  const disconnectMutation = useDisconnectIntegration();

  const [connectingType, setConnectingType] = useState<string | null>(null);
  const [disconnectConfirm, setDisconnectConfirm] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Handle OAuth callback: detect code/connected_account_id in URL params
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('code');
    const connectedAccountId = params.get('connected_account_id');

    if (!code && !connectedAccountId) return;

    const pendingType = sessionStorage.getItem(PENDING_INTEGRATION_KEY);
    if (!pendingType) return;

    sessionStorage.removeItem(PENDING_INTEGRATION_KEY);

    // Clean URL params without triggering navigation
    const url = new URL(window.location.href);
    url.searchParams.delete('code');
    url.searchParams.delete('state');
    url.searchParams.delete('connected_account_id');
    window.history.replaceState({}, '', url.pathname + url.hash);

    // Complete the connection
    connectMutation.mutate(
      {
        integrationType: pendingType as IntegrationType,
        data: { code: code || connectedAccountId || '' },
      },
      {
        onSuccess: () => {
          setFeedback({ type: 'success', message: 'Integration connected successfully.' });
        },
        onError: () => {
          setFeedback({ type: 'error', message: 'Failed to complete integration connection. Please try again.' });
        },
      }
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleConnect = useCallback((primaryType: IntegrationType) => {
    setConnectingType(primaryType);
    setFeedback(null);

    const redirectUri = `${window.location.origin}/settings/integrations`;

    getAuthUrl.mutate(
      { integrationType: primaryType, redirectUri },
      {
        onSuccess: (data) => {
          sessionStorage.setItem(PENDING_INTEGRATION_KEY, primaryType);
          window.location.href = data.authorization_url;
        },
        onError: () => {
          setConnectingType(null);
          setFeedback({ type: 'error', message: 'Failed to get authorization URL. Please try again.' });
        },
      }
    );
  }, [getAuthUrl]);

  const handleDisconnect = useCallback((primaryType: IntegrationType) => {
    setFeedback(null);
    disconnectMutation.mutate(primaryType, {
      onSuccess: () => {
        setDisconnectConfirm(null);
        setFeedback({ type: 'success', message: 'Integration disconnected.' });
      },
      onError: () => {
        setDisconnectConfirm(null);
        setFeedback({ type: 'error', message: 'Failed to disconnect integration.' });
      },
    });
  }, [disconnectMutation]);

  // Build a lookup from available integrations
  const integrationStatusMap = new Map(
    (availableIntegrations ?? []).map((ai) => [ai.integration_type, ai])
  );

  return (
    <div
      className="border rounded-lg p-6"
      style={{ borderColor: 'var(--border)', backgroundColor: 'var(--bg-elevated)' }}
    >
      <div className="flex items-center gap-2 mb-6">
        <Link2 className="w-4 h-4" style={{ color: 'var(--text-secondary)' }} />
        <h3 className="font-medium" style={{ color: 'var(--text-primary)' }}>
          Integrations
        </h3>
      </div>

      {/* Feedback banner */}
      {feedback && (
        <div
          className="flex items-center justify-between gap-2 mb-4 p-3 rounded-lg border text-sm"
          style={{
            borderColor: feedback.type === 'success' ? 'var(--success)' : 'var(--error, #ef4444)',
            backgroundColor: feedback.type === 'success' ? 'var(--success)' : 'var(--error, #ef4444)',
            color: 'white',
            opacity: 0.9,
          }}
        >
          <span>{feedback.message}</span>
          <button onClick={() => setFeedback(null)} className="flex-shrink-0">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="w-5 h-5 animate-spin" style={{ color: 'var(--text-secondary)' }} />
        </div>
      ) : (
        <div className="space-y-4">
          {INTEGRATION_CARDS.map((card) => {
            if (card.comingSoon) {
              return (
                <ComingSoonIndicator
                  key={card.id}
                  title={card.name}
                  description={card.description}
                  availableDate="2026"
                />
              );
            }

            const backendInfo = integrationStatusMap.get(card.primaryType);
            const isConnected = backendInfo?.is_connected ?? false;
            const status = backendInfo?.status;
            const needsReconnection = !isConnected && (status === 'disconnected' || status === 'error');
            const isConnecting = connectingType === card.primaryType && getAuthUrl.isPending;
            const isDisconnecting = disconnectMutation.isPending && disconnectConfirm === card.primaryType;

            return (
              <div
                key={card.id}
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
                    {card.icon}
                  </div>
                  <div>
                    <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                      {card.name}
                    </p>
                    <p className="text-xs" style={{ color: 'var(--text-secondary)' }}>
                      {card.description}
                    </p>
                  </div>
                </div>

                {/* Status + Actions */}
                {isConnected ? (
                  <div className="flex items-center gap-2">
                    <span
                      className="flex items-center gap-1 text-xs"
                      style={{ color: 'var(--success)' }}
                    >
                      <Check className="w-3.5 h-3.5" />
                      Connected
                    </span>
                    {disconnectConfirm === card.primaryType ? (
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => handleDisconnect(card.primaryType)}
                          disabled={isDisconnecting}
                          className="text-xs px-2 py-1 rounded border"
                          style={{
                            borderColor: 'var(--error, #ef4444)',
                            color: 'var(--error, #ef4444)',
                          }}
                        >
                          {isDisconnecting ? 'Disconnecting...' : 'Confirm'}
                        </button>
                        <button
                          onClick={() => setDisconnectConfirm(null)}
                          className="text-xs px-2 py-1 rounded border"
                          style={{
                            borderColor: 'var(--border)',
                            color: 'var(--text-secondary)',
                          }}
                        >
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setDisconnectConfirm(card.primaryType)}
                        className="text-xs px-2 py-1 rounded border"
                        style={{
                          borderColor: 'var(--border)',
                          color: 'var(--text-secondary)',
                        }}
                      >
                        Disconnect
                      </button>
                    )}
                  </div>
                ) : needsReconnection ? (
                  <div className="flex items-center gap-2">
                    <span
                      className="flex items-center gap-1 text-xs"
                      style={{ color: 'var(--warning, #f59e0b)' }}
                    >
                      <AlertTriangle className="w-3.5 h-3.5" />
                      Needs reconnection
                    </span>
                    <button
                      onClick={() => handleConnect(card.primaryType)}
                      disabled={isConnecting}
                      className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg"
                      style={{
                        backgroundColor: 'var(--accent)',
                        color: 'white',
                        opacity: isConnecting ? 0.6 : 1,
                      }}
                    >
                      {isConnecting ? (
                        <Loader2 className="w-3 h-3 animate-spin" />
                      ) : (
                        <ExternalLink className="w-3 h-3" />
                      )}
                      Reconnect
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => handleConnect(card.primaryType)}
                    disabled={isConnecting}
                    className="flex items-center gap-1 text-xs px-3 py-1.5 rounded-lg"
                    style={{
                      backgroundColor: 'var(--accent)',
                      color: 'white',
                      opacity: isConnecting ? 0.6 : 1,
                    }}
                  >
                    {isConnecting ? (
                      <Loader2 className="w-3 h-3 animate-spin" />
                    ) : (
                      <ExternalLink className="w-3 h-3" />
                    )}
                    Connect
                  </button>
                )}
              </div>
            );
          })}

          {/* Coming Soon: Browser & OS Control */}
          <ComingSoonIndicator
            title="Browser & OS Control"
            description="Let ARIA navigate websites and control your desktop applications autonomously."
            availableDate="Q3 2026"
          />
        </div>
      )}
    </div>
  );
}
