/**
 * RequestToolCard — In-chat card for requesting admin approval of a toolkit.
 *
 * Rendered when an agent discovers a tool that requires admin approval
 * before the user can connect it. Submits a request and listens for
 * WS `toolkit_request_approved` / `toolkit_request_denied` events.
 *
 * Modeled on ConnectToolCard — same state machine pattern, CSS variables,
 * and WebSocket event listening.
 */

import { useState, useEffect, useCallback } from 'react';
import { requestToolAccess } from '@/api/adminTools';
import { wsManager } from '@/core/WebSocketManager';

export interface RequestToolData {
  toolkit_slug: string;
  display_name: string;
  benefit: string;
  reason_hint?: string;
}

type CardState = 'idle' | 'requesting' | 'submitted' | 'approved' | 'denied' | 'error';

export function RequestToolCard({ data }: { data: RequestToolData }) {
  const [state, setState] = useState<CardState>('idle');
  const [error, setError] = useState('');

  // Listen for WS approval/denial events
  useEffect(() => {
    const handleApproved = (payload: { toolkit_slug?: string }) => {
      if (payload.toolkit_slug?.toUpperCase() === data.toolkit_slug.toUpperCase()) {
        setState('approved');
      }
    };

    const handleDenied = (payload: { toolkit_slug?: string }) => {
      if (payload.toolkit_slug?.toUpperCase() === data.toolkit_slug.toUpperCase()) {
        setState('denied');
      }
    };

    wsManager.on('toolkit_request_approved', handleApproved);
    wsManager.on('toolkit_request_denied', handleDenied);

    return () => {
      wsManager.off('toolkit_request_approved', handleApproved as (p: unknown) => void);
      wsManager.off('toolkit_request_denied', handleDenied as (p: unknown) => void);
    };
  }, [data.toolkit_slug]);

  const handleRequest = useCallback(async () => {
    setState('requesting');
    setError('');
    try {
      const result = await requestToolAccess({
        toolkit_slug: data.toolkit_slug,
        toolkit_display_name: data.display_name,
        reason: data.benefit,
      });
      if (result.status === 'already_approved') {
        setState('approved');
      } else if (result.status === 'already_pending') {
        setState('submitted');
      } else {
        setState('submitted');
      }
    } catch {
      setState('error');
      setError('Failed to submit request');
    }
  }, [data.toolkit_slug, data.display_name, data.benefit]);

  if (state === 'approved') {
    return (
      <div
        className="rounded-xl p-4 border"
        style={{ borderColor: 'var(--success)', background: 'var(--surface)' }}
      >
        <p className="text-sm font-medium" style={{ color: 'var(--success)' }}>
          {data.display_name} approved — you can now connect it.
        </p>
      </div>
    );
  }

  if (state === 'denied') {
    return (
      <div
        className="rounded-xl p-4 border"
        style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
      >
        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
          {data.display_name} request was not approved by your admin.
        </p>
      </div>
    );
  }

  if (state === 'submitted') {
    return (
      <div
        className="rounded-xl p-4 border"
        style={{ borderColor: 'var(--accent)', background: 'var(--surface)' }}
      >
        <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
          Request submitted for {data.display_name}
        </p>
        <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
          Your admin will review this. I'll notify you when it's approved.
        </p>
      </div>
    );
  }

  return (
    <div
      className="rounded-xl p-4 border"
      style={{ borderColor: 'var(--border)', background: 'var(--surface)' }}
    >
      <div className="flex items-start gap-3">
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center text-sm shrink-0"
          style={{ background: 'var(--accent)', color: '#fff', opacity: 0.8 }}
        >
          ?
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
            {data.display_name} — Admin Approval Required
          </p>
          <p className="text-xs mt-1" style={{ color: 'var(--text-secondary)' }}>
            {data.benefit}
          </p>
          {state === 'error' && (
            <p className="text-xs mt-1" style={{ color: 'var(--error)' }}>{error}</p>
          )}
          <button
            onClick={handleRequest}
            disabled={state === 'requesting'}
            className="mt-3 px-3 py-1.5 rounded-lg text-xs font-medium transition-opacity hover:opacity-80"
            style={{
              background: 'var(--accent)',
              color: '#fff',
              opacity: state === 'requesting' ? 0.6 : 1,
            }}
          >
            {state === 'requesting' ? 'Requesting...' : 'Request Access from Admin'}
          </button>
        </div>
      </div>
    </div>
  );
}
