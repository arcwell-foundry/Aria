import { apiClient } from "@/api/client";

export interface UnifiedSession {
  id: string;
  user_id: string;
  started_at: string;
  ended_at: string | null;
  current_route: string;
  active_modality: "text" | "voice" | "avatar";
  conversation_thread: string[];
  metadata: Record<string, unknown>;
}

// Backend response format (session_data is nested)
interface BackendSessionResponse {
  id: string;
  user_id: string;
  session_data: {
    current_route: string;
    active_modality: string;
    conversation_thread: string[];
    metadata: Record<string, unknown>;
  };
  is_active: boolean;
  day_date: string;
  created_at: string;
  updated_at: string;
}

const SYNC_INTERVAL_MS = 30_000;

/**
 * Convert backend session response to frontend UnifiedSession format.
 */
function toUnifiedSession(backend: BackendSessionResponse): UnifiedSession {
  return {
    id: backend.id,
    user_id: backend.user_id,
    started_at: backend.created_at,
    ended_at: null,
    current_route: backend.session_data.current_route,
    active_modality: backend.session_data.active_modality as "text" | "voice" | "avatar",
    conversation_thread: backend.session_data.conversation_thread,
    metadata: backend.session_data.metadata,
  };
}

/**
 * Manages session lifecycle via REST API calls.
 *
 * Resilient by design: if the backend is unreachable or endpoints don't exist,
 * falls back to a local-only session so the app continues to function.
 * All errors are silently swallowed to prevent console noise.
 */
export class SessionManager {
  /**
   * Initialize a session. Attempts to resume an existing same-day session
   * from the backend. Falls back to creating a new session if none exists
   * or the existing one is stale (different day). If the backend is
   * unreachable, returns a local-only session.
   */
  async initialize(): Promise<UnifiedSession> {
    try {
      // First, try to get existing active session
      const activeResponse = await apiClient.get<BackendSessionResponse | null>("/sessions/active");
      if (activeResponse.data) {
        return toUnifiedSession(activeResponse.data);
      }

      // No active session - create a new one
      return await this.createSession();
    } catch {
      // Backend unreachable or endpoint doesn't exist — fall back to local
      return this.createLocalSession();
    }
  }

  /**
   * Create a new session on the backend.
   */
  async createSession(): Promise<UnifiedSession> {
    try {
      const response = await apiClient.post<BackendSessionResponse>("/sessions", {
        current_route: "/",
        active_modality: "text",
        conversation_thread: [],
        metadata: {},
      });
      return toUnifiedSession(response.data);
    } catch {
      // Backend unreachable or endpoint doesn't exist — fall back to local
      return this.createLocalSession();
    }
  }

  /**
   * Archive a session by calling the archive endpoint.
   * Silently ignores errors (endpoint may not exist).
   */
  async archiveSession(sessionId: string): Promise<void> {
    try {
      await apiClient.post(`/sessions/${sessionId}/archive`);
    } catch {
      // Silently ignore — endpoint may not exist
    }
  }

  /**
   * Sync the current session state to the backend.
   * Silently ignores errors (endpoint may not exist).
   */
  async syncSession(session: UnifiedSession): Promise<void> {
    try {
      await apiClient.patch(`/sessions/${session.id}`, {
        current_route: session.current_route,
        active_modality: session.active_modality,
        conversation_thread: session.conversation_thread,
        metadata: session.metadata,
      });
    } catch {
      // Silently ignore — endpoint may not exist
    }
  }

  /**
   * Start a periodic sync interval that pushes the latest session state
   * to the backend every 30 seconds.
   *
   * @param _session - The initial session (used for type context; getLatest provides current state)
   * @param getLatest - Callback that returns the most recent session state
   * @returns Cleanup function that stops the interval
   */
  startSyncInterval(
    _session: UnifiedSession,
    getLatest: () => UnifiedSession,
  ): () => void {
    const intervalId = setInterval(() => {
      const current = getLatest();
      void this.syncSession(current);
    }, SYNC_INTERVAL_MS);

    return () => {
      clearInterval(intervalId);
    };
  }

  /**
   * Check whether the given ISO date string falls on today (local time).
   */
  isSameDay(dateStr: string): boolean {
    const date = new Date(dateStr);
    const today = new Date();

    return (
      date.getFullYear() === today.getFullYear() &&
      date.getMonth() === today.getMonth() &&
      date.getDate() === today.getDate()
    );
  }

  /**
   * Create a local-only session when the backend is unreachable.
   * Uses crypto.randomUUID() for a standards-compliant UUID.
   */
  private createLocalSession(): UnifiedSession {
    return {
      id: crypto.randomUUID(),
      user_id: "local",
      started_at: new Date().toISOString(),
      ended_at: null,
      current_route: "/",
      active_modality: "text",
      conversation_thread: [],
      metadata: { local_only: true },
    };
  }
}
