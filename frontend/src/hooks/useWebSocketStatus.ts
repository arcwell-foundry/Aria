/**
 * useWebSocketStatus — Reactive hook for WebSocket connection state
 *
 * Subscribes to connection lifecycle events emitted by the singleton
 * WebSocketManager and exposes reactive connection state values.
 *
 * The WebSocketManager emits:
 * - 'connection.established' on successful connect (both WebSocket and SSE fallback)
 * - 'connection.error' on failures
 * - 'connection.state_changed' on state transitions
 * - 'connection.failed' when max retries are exceeded
 */

import { useState, useEffect, useCallback } from 'react';
import { wsManager, type ConnectionState, type TransportType } from '@/core/WebSocketManager';
import { useIsMounted } from '@/hooks/useIsMounted';

interface WebSocketStatus {
  isConnected: boolean;
  connectionState: ConnectionState;
  transport: TransportType;
  isReconnecting: boolean;
  isFailed: boolean;
}

interface StateChangedPayload {
  state: ConnectionState;
  transport?: TransportType;
  reason?: string;
}

interface EstablishedPayload {
  transport: TransportType;
}

export function useWebSocketStatus(): WebSocketStatus {
  const [connectionState, setConnectionState] = useState<ConnectionState>(
    () => wsManager.connectionState,
  );
  const [transport, setTransport] = useState<TransportType>(() => wsManager.transport);
  const isMounted = useIsMounted();

  const handleStateChanged = useCallback((payload: unknown) => {
    const p = payload as StateChangedPayload;
    if (!isMounted()) return;
    setConnectionState(p.state);
    if (p.transport) {
      setTransport(p.transport);
    }
  }, [isMounted]);

  const handleEstablished = useCallback((payload: unknown) => {
    const p = payload as EstablishedPayload;
    if (!isMounted()) return;
    setConnectionState('connected');
    setTransport(p.transport);
  }, [isMounted]);

  const handleError = useCallback(() => {
    // Don't immediately set to disconnected - let state_changed handle it
  }, []);

  useEffect(() => {
    wsManager.on('connection.established', handleEstablished);
    wsManager.on('connection.error', handleError);
    wsManager.on('connection.state_changed', handleStateChanged);

    // Poll periodically as a safety net — the wsManager may update state
    // without emitting an event in some edge cases.
    const interval = setInterval(() => {
      // Guard against setState on unmounted component (React error #300)
      if (!isMounted()) return;
      setConnectionState(wsManager.connectionState);
      setTransport(wsManager.transport);
    }, 5_000);

    return () => {
      wsManager.off('connection.established', handleEstablished);
      wsManager.off('connection.error', handleError);
      wsManager.off('connection.state_changed', handleStateChanged);
      clearInterval(interval);
    };
  }, [handleEstablished, handleError, handleStateChanged, isMounted]);

  const isConnected = connectionState === 'connected';
  const isReconnecting = connectionState === 'reconnecting';
  const isFailed = connectionState === 'failed';

  return {
    isConnected,
    connectionState,
    transport,
    isReconnecting,
    isFailed,
  };
}
