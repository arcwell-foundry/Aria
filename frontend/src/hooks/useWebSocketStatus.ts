/**
 * useWebSocketStatus — Reactive hook for WebSocket connection state
 *
 * Subscribes to connection lifecycle events emitted by the singleton
 * WebSocketManager and exposes a reactive { isConnected } value.
 *
 * The WebSocketManager emits 'connection.established' on successful
 * connect (both WebSocket and SSE fallback) and 'connection.error'
 * on failures. The underlying _isConnected flag is also toggled on
 * close events. This hook captures those transitions by listening
 * for the relevant events and polling the getter as a sync fallback.
 */

import { useState, useEffect, useCallback } from 'react';
import { wsManager } from '@/core/WebSocketManager';

interface WebSocketStatus {
  isConnected: boolean;
}

export function useWebSocketStatus(): WebSocketStatus {
  const [isConnected, setIsConnected] = useState<boolean>(() => wsManager.isConnected);

  const handleEstablished = useCallback(() => setIsConnected(true), []);
  const handleError = useCallback(() => setIsConnected(false), []);

  useEffect(() => {
    wsManager.on('connection.established', handleEstablished);
    wsManager.on('connection.error', handleError);

    // Poll periodically as a safety net — the wsManager mutates _isConnected
    // on close/disconnect without emitting a dedicated event.
    const interval = setInterval(() => {
      setIsConnected(wsManager.isConnected);
    }, 3_000);

    return () => {
      wsManager.off('connection.established', handleEstablished);
      wsManager.off('connection.error', handleError);
      clearInterval(interval);
    };
  }, [handleEstablished, handleError]);

  return { isConnected };
}
