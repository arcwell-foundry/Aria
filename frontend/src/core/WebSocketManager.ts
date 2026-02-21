import { WS_EVENTS, type WSEnvelope } from '@/types/chat';

type EventHandler = (payload: unknown) => void;

interface ConnectionConfig {
  userId: string;
  sessionId: string;
}

const HEARTBEAT_INTERVAL = 30_000;
const RECONNECT_BASE_DELAY = 1_000;
const RECONNECT_MAX_DELAY = 30_000;
const MAX_RECONNECT_ATTEMPTS = 10;
const WS_UPGRADE_RETRY_INTERVAL = 60_000;

class WebSocketManagerImpl {
  private ws: WebSocket | null = null;
  private listeners = new Map<string, Set<EventHandler>>();
  private heartbeatTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  private wsUpgradeTimer: ReturnType<typeof setInterval> | null = null;
  private reconnectAttempts = 0;
  private config: ConnectionConfig | null = null;
  private _transport: 'websocket' | 'sse' | 'disconnected' = 'disconnected';
  private _isConnected = false;
  private intentionalDisconnect = false;

  get isConnected(): boolean {
    return this._isConnected;
  }

  get transport(): 'websocket' | 'sse' | 'disconnected' {
    return this._transport;
  }

  connect(userId: string, sessionId: string): void {
    this.config = { userId, sessionId };
    this.intentionalDisconnect = false;
    this.reconnectAttempts = 0;
    this.attemptWebSocket();
  }

  disconnect(): void {
    this.intentionalDisconnect = true;
    this.cleanup();
    this._transport = 'disconnected';
    this._isConnected = false;
  }

  send(event: string, payload: unknown): void {
    const envelope: WSEnvelope = { type: event, payload };

    if (this._transport === 'websocket' && this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(envelope));
      return;
    }

    if (this._transport === 'sse' && event === WS_EVENTS.USER_MESSAGE) {
      void this.sendViaRest(payload as { message: string; conversation_id?: string });
      return;
    }
  }

  on<T = unknown>(event: string, handler: (payload: T) => void): void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(handler as EventHandler);
  }

  off(event: string, handler: EventHandler): void {
    this.listeners.get(event)?.delete(handler);
  }

  private buildWsUrl(userId: string, sessionId: string): string {
    const apiUrl = new URL(import.meta.env.VITE_API_URL || 'http://localhost:8000');
    const wsProtocol = apiUrl.protocol === 'https:' ? 'wss:' : 'ws:';
    return `${wsProtocol}//${apiUrl.host}/ws/${userId}?session_id=${sessionId}`;
  }

  private attemptWebSocket(): void {
    if (!this.config) return;

    const url = this.buildWsUrl(this.config.userId, this.config.sessionId);
    const token = localStorage.getItem('access_token');

    try {
      this.ws = new WebSocket(token ? `${url}&token=${token}` : url);
    } catch {
      this.fallbackToSSE();
      return;
    }

    const connectTimeout = setTimeout(() => {
      if (this.ws?.readyState !== WebSocket.OPEN) {
        this.ws?.close();
        this.fallbackToSSE();
      }
    }, 5_000);

    this.ws.onopen = () => {
      clearTimeout(connectTimeout);
      this._transport = 'websocket';
      this._isConnected = true;
      this.reconnectAttempts = 0;
      this.startHeartbeat();
      this.stopWSUpgradeRetry();
      this.emit('connection.established', { transport: 'websocket' });
    };

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const envelope = JSON.parse(event.data as string) as WSEnvelope;
        this.emit(envelope.type, envelope.payload);
      } catch {
        // Ignore malformed messages
      }
    };

    this.ws.onclose = (event: CloseEvent) => {
      clearTimeout(connectTimeout);
      this.stopHeartbeat();

      if (this.intentionalDisconnect) return;

      // Auth failures (1008 policy violation) and custom app codes (4xxx)
      // should immediately fall back to SSE — retrying won't help.
      if (event.code === 1008 || (event.code >= 4000 && event.code < 5000)) {
        console.debug(`[WebSocketManager] Auth/policy close (code=${event.code}), falling back to SSE`);
        this.fallbackToSSE();
        return;
      }

      if (this._transport === 'websocket') {
        this._isConnected = false;
        this.scheduleReconnect();
      }
    };

    this.ws.onerror = () => {
      clearTimeout(connectTimeout);
    };
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= MAX_RECONNECT_ATTEMPTS) {
      this.fallbackToSSE();
      return;
    }

    const delay = Math.min(
      RECONNECT_BASE_DELAY * Math.pow(2, this.reconnectAttempts),
      RECONNECT_MAX_DELAY,
    );
    this.reconnectAttempts++;

    this.reconnectTimer = setTimeout(() => {
      this.attemptWebSocket();
    }, delay);
  }

  private fallbackToSSE(): void {
    this.ws?.close();
    this.ws = null;
    this._transport = 'sse';
    this._isConnected = true;
    this.emit('connection.established', { transport: 'sse' });
    this.startWSUpgradeRetry();
  }

  private async sendViaRest(payload: { message: string; conversation_id?: string }): Promise<void> {
    const token = localStorage.getItem('access_token');
    const baseUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';

    this.emit(WS_EVENTS.ARIA_THINKING, { is_thinking: true });

    try {
      const response = await fetch(`${baseUrl}/api/v1/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          message: payload.message,
          conversation_id: payload.conversation_id,
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';
      let fullContent = '';
      let messageId = '';
      let conversationId = payload.conversation_id || '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const jsonStr = line.slice(6);

          if (jsonStr === '[DONE]') {
            this.emit(WS_EVENTS.ARIA_THINKING, { is_thinking: false });
            this.emit(WS_EVENTS.ARIA_MESSAGE, {
              message: fullContent,
              message_id: messageId,
              conversation_id: conversationId,
            });
            return;
          }

          try {
            const event = JSON.parse(jsonStr);
            if (event.type === 'token') {
              fullContent += event.content;
              this.emit('aria.token', { content: event.content, full_content: fullContent });
            } else if (event.type === 'metadata') {
              messageId = event.message_id;
              conversationId = event.conversation_id;
            } else if (event.type === 'complete') {
              if (event.rich_content || event.ui_commands || event.suggestions) {
                this.emit('aria.metadata', {
                  message_id: messageId,
                  rich_content: event.rich_content || [],
                  ui_commands: event.ui_commands || [],
                  suggestions: event.suggestions || [],
                });
              }
            } else if (event.type === 'error') {
              throw new Error(event.content);
            }
          } catch (e) {
            if (e instanceof Error && !e.message.includes('JSON')) throw e;
          }
        }
      }
    } catch (error) {
      this.emit(WS_EVENTS.ARIA_THINKING, { is_thinking: false });
      this.emit('connection.error', { error: String(error) });
    }
  }

  private startWSUpgradeRetry(): void {
    this.stopWSUpgradeRetry();
    this.wsUpgradeTimer = setInterval(() => {
      if (this._transport === 'sse' && !this.intentionalDisconnect) {
        const url = this.buildWsUrl(this.config?.userId || '', this.config?.sessionId || '');
        const probe = new WebSocket(url);
        const timeout = setTimeout(() => probe.close(), 3_000);

        probe.onopen = () => {
          clearTimeout(timeout);
          probe.close();
          this.stopWSUpgradeRetry();
          this.reconnectAttempts = 0;
          this.attemptWebSocket();
        };

        probe.onerror = () => {
          clearTimeout(timeout);
        };
      }
    }, WS_UPGRADE_RETRY_INTERVAL);
  }

  private stopWSUpgradeRetry(): void {
    if (this.wsUpgradeTimer) {
      clearInterval(this.wsUpgradeTimer);
      this.wsUpgradeTimer = null;
    }
  }

  private startHeartbeat(): void {
    this.stopHeartbeat();
    this.heartbeatTimer = setInterval(() => {
      this.send(WS_EVENTS.HEARTBEAT, { timestamp: Date.now() });
    }, HEARTBEAT_INTERVAL);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatTimer) {
      clearInterval(this.heartbeatTimer);
      this.heartbeatTimer = null;
    }
  }

  private emit(event: string, payload: unknown): void {
    const handlers = this.listeners.get(event);
    if (handlers) {
      for (const handler of handlers) {
        try {
          handler(payload);
        } catch (e) {
          console.error(`[WebSocketManager] Handler error for ${event}:`, e);
        }
      }
    }
  }

  private cleanup(): void {
    this.stopHeartbeat();
    this.stopWSUpgradeRetry();
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.onclose = null;
      this.ws.onerror = null;
      this.ws.close();
      this.ws = null;
    }
  }
}

/** Singleton instance */
export const wsManager = new WebSocketManagerImpl();
