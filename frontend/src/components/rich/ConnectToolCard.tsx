/**
 * ConnectToolCard — In-chat OAuth connection card with popup flow.
 *
 * Rendered when an agent needs a tool that requires an integration the
 * user hasn't connected yet. Opens a popup for OAuth, listens for
 * postMessage and WS `integration.connected` events.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import { Link2, Check, Loader2, X, AlertTriangle } from 'lucide-react';
import { getAuthUrlPopup } from '@/api/integrations';
import { wsManager } from '@/core/WebSocketManager';
import { WS_EVENTS } from '@/types/chat';
import type { IntegrationType } from '@/api/integrations';

export interface ConnectToolData {
  toolkit_slug: string;
  display_name: string;
  benefit: string;
  providers: string[];
  agent: string;
}

type CardState = 'idle' | 'connecting' | 'connected' | 'error';

export function ConnectToolCard({ data }: { data: ConnectToolData }) {
  const [state, setState] = useState<CardState>('idle');
  const [dismissed, setDismissed] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');
  const popupRef = useRef<Window | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Clean up poll on unmount
  useEffect(() => {
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, []);

  // Listen for postMessage from the popup
  useEffect(() => {
    if (state !== 'connecting') return;

    const handleMessage = (event: MessageEvent) => {
      const msg = event.data;
      if (!msg || typeof msg !== 'object') return;

      if (msg.type === 'aria_oauth_success' && msg.toolkit_slug === data.toolkit_slug) {
        setState('connected');
        if (pollRef.current) clearInterval(pollRef.current);
      } else if (msg.type === 'aria_oauth_error') {
        setState('error');
        setErrorMsg(msg.error || 'OAuth failed');
        if (pollRef.current) clearInterval(pollRef.current);
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [state, data.toolkit_slug]);

  // Listen for WS integration.connected event
  useEffect(() => {
    if (state !== 'connecting') return;

    const handleWsEvent = (payload: { toolkit_slug?: string; status?: string }) => {
      if (payload.toolkit_slug === data.toolkit_slug && payload.status === 'active') {
        setState('connected');
        if (pollRef.current) clearInterval(pollRef.current);
      }
    };

    wsManager.on(WS_EVENTS.INTEGRATION_CONNECTED, handleWsEvent);
    return () => wsManager.off(WS_EVENTS.INTEGRATION_CONNECTED, handleWsEvent as (p: unknown) => void);
  }, [state, data.toolkit_slug]);

  const handleConnect = useCallback(async () => {
    setState('connecting');
    setErrorMsg('');

    try {
      const response = await getAuthUrlPopup(data.toolkit_slug as IntegrationType);

      // Open the popup
      const popup = window.open(
        response.authorization_url,
        'aria_connect',
        'width=600,height=700,scrollbars=yes,resizable=yes,status=yes'
      );

      if (!popup) {
        // Popup blocked — show fallback
        setState('error');
        setErrorMsg('Popup blocked. Please allow popups for this site and try again.');
        return;
      }

      popupRef.current = popup;

      // Poll for popup close with 2s grace period
      pollRef.current = setInterval(() => {
        if (popup.closed) {
          if (pollRef.current) clearInterval(pollRef.current);
          // Give 2s for late WS/postMessage events
          setTimeout(() => {
            setState((prev) => {
              if (prev === 'connecting') return 'idle'; // User closed popup without completing
              return prev;
            });
          }, 2000);
        }
      }, 500);
    } catch {
      setState('error');
      setErrorMsg('Failed to get authorization URL.');
    }
  }, [data.toolkit_slug]);

  if (!data) return null;

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
        Connection request dismissed
      </div>
    );
  }

  return (
    <div
      className="rounded-lg border overflow-hidden"
      style={{
        borderColor: state === 'connected' ? 'var(--success, #22c55e)' : 'var(--border)',
        backgroundColor: 'var(--bg-elevated)',
      }}
      data-aria-id="connect-tool-card"
    >
      {/* Header */}
      <div
        className="flex items-center gap-2 px-4 py-2.5"
        style={{
          backgroundColor: state === 'connected'
            ? 'rgba(34,197,94,0.05)'
            : 'rgba(46,102,255,0.05)',
          borderBottom: '1px solid var(--border)',
        }}
      >
        <Link2 className="w-3.5 h-3.5" style={{ color: state === 'connected' ? 'var(--success, #22c55e)' : 'var(--accent)' }} />
        <span className="text-xs font-medium" style={{ color: 'var(--text-primary)' }}>
          {state === 'connected' ? 'Connected' : 'Connect Integration'}
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
          {state === 'connected'
            ? `${data.display_name} is now connected.`
            : `Connect your ${data.display_name} to ${data.benefit}.`}
        </p>

        {/* Provider badges */}
        {state !== 'connected' && (
          <div className="flex items-center gap-2 mb-3">
            {(data.providers ?? []).map((provider) => (
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
        )}

        {/* Error message */}
        {state === 'error' && errorMsg && (
          <div className="flex items-center gap-2 mb-3 text-xs" style={{ color: 'var(--error, #ef4444)' }}>
            <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {/* Actions */}
        <div className="flex items-center gap-2">
          {state === 'connected' ? (
            <span className="flex items-center gap-1.5 text-xs font-medium" style={{ color: 'var(--success, #22c55e)' }}>
              <Check className="w-3.5 h-3.5" />
              Ready to use
            </span>
          ) : (
            <>
              <button
                type="button"
                onClick={handleConnect}
                disabled={state === 'connecting'}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-medium text-white transition-opacity hover:opacity-90"
                style={{
                  backgroundColor: 'var(--accent)',
                  opacity: state === 'connecting' ? 0.6 : 1,
                }}
              >
                {state === 'connecting' ? (
                  <Loader2 className="w-3 h-3 animate-spin" />
                ) : (
                  <Link2 className="w-3 h-3" />
                )}
                {state === 'connecting' ? 'Connecting...' : state === 'error' ? 'Try Again' : 'Connect'}
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
            </>
          )}
        </div>
      </div>
    </div>
  );
}
