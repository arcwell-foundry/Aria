import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";
import { SessionManager } from "@/core/SessionManager";
import type { UnifiedSession } from "@/core/SessionManager";

type UpdatableSessionFields = Partial<
  Pick<
    UnifiedSession,
    "current_route" | "active_modality" | "conversation_thread" | "metadata"
  >
>;

export interface SessionContextType {
  session: UnifiedSession | null;
  isSessionReady: boolean;
  updateSession: (updates: UpdatableSessionFields) => void;
}

export const SessionContext = createContext<SessionContextType | null>(null);

interface SessionProviderProps {
  children: ReactNode;
}

export function SessionProvider({ children }: SessionProviderProps) {
  const [session, setSession] = useState<UnifiedSession | null>(null);
  const [isSessionReady, setIsSessionReady] = useState(false);

  const managerRef = useRef<SessionManager>(new SessionManager());
  const sessionRef = useRef<UnifiedSession | null>(null);

  // Keep sessionRef in sync with state so the interval callback reads fresh data
  useEffect(() => {
    sessionRef.current = session;
  }, [session]);

  // Initialize session on mount
  useEffect(() => {
    let cleanupSync: (() => void) | undefined;
    let cancelled = false;

    const init = async () => {
      const manager = managerRef.current;
      const initialSession = await manager.initialize();

      if (cancelled) return;

      setSession(initialSession);
      sessionRef.current = initialSession;
      setIsSessionReady(true);

      // Start the 30-second sync interval
      cleanupSync = manager.startSyncInterval(
        initialSession,
        () => sessionRef.current ?? initialSession,
      );
    };

    void init();

    return () => {
      cancelled = true;
      cleanupSync?.();
    };
  }, []);

  const updateSession = useCallback((updates: UpdatableSessionFields) => {
    setSession((prev) => {
      if (!prev) return prev;

      const next: UnifiedSession = {
        ...prev,
        ...updates,
        metadata: updates.metadata
          ? { ...prev.metadata, ...updates.metadata }
          : prev.metadata,
      };

      return next;
    });
  }, []);

  return (
    <SessionContext.Provider value={{ session, isSessionReady, updateSession }}>
      {children}
    </SessionContext.Provider>
  );
}

/**
 * Access the current session context.
 * Must be called within a <SessionProvider>.
 */
export function useSession(): SessionContextType {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error("useSession must be used within a SessionProvider");
  }
  return context;
}
