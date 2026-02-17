/**
 * Video session management hook for Tavus avatar integration.
 *
 * Manages the lifecycle of video sessions: creation, connection, and cleanup.
 */

import { useState, useCallback, useRef, useEffect } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  createVideoSession,
  endVideoSession,
  getVideoSession,
  listVideoSessions,
  type VideoSession,
  type VideoSessionCreate,
  type VideoTranscriptEntry,
  type SessionType,
  type VideoSessionStatus,
} from "@/api/video";

// Re-export types for convenience
export type { SessionType, VideoSessionStatus, VideoSession, VideoTranscriptEntry } from "@/api/video";

// Query keys
export const videoKeys = {
  all: ["video"] as const,
  sessions: () => [...videoKeys.all, "sessions"] as const,
  session: (id: string) => [...videoKeys.all, "session", id] as const,
};

// Session state type
export type VideoConnectionState =
  | "idle" // No session
  | "haircheck" // Pre-call device check
  | "connecting" // Joining the call
  | "connected" // In active call
  | "disconnecting" // Leaving the call
  | "error"; // Error state

export interface VideoSessionState {
  session: VideoSession | null;
  connectionState: VideoConnectionState;
  error: string | null;
  transcript: VideoTranscriptEntry[];
  isMuted: boolean;
}

/**
 * Hook for managing video session lifecycle.
 */
export function useVideoSession() {
  const queryClient = useQueryClient();

  // Local state for active session management
  const [state, setState] = useState<VideoSessionState>({
    session: null,
    connectionState: "idle",
    error: null,
    transcript: [],
    isMuted: false,
  });

  // Track the current session ID for cleanup
  const sessionRef = useRef<string | null>(null);
  const pollIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Poll session status every 5s while active
  useEffect(() => {
    if (state.connectionState === "connected" && sessionRef.current) {
      pollIntervalRef.current = setInterval(async () => {
        try {
          const session = await getVideoSession(sessionRef.current!);
          setState((prev) => ({
            ...prev,
            session,
            transcript: session.transcripts ?? prev.transcript,
          }));
        } catch {
          // Silently ignore polling errors - will be caught on next action
        }
      }, 5000);
    }

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    };
  }, [state.connectionState]);

  // Cleanup on unmount - end session if active
  useEffect(() => {
    return () => {
      if (sessionRef.current) {
        endVideoSession(sessionRef.current).catch(() => {
          // Silently ignore cleanup errors
        });
        sessionRef.current = null;
      }
    };
  }, []);

  // Create session mutation
  const createMutation = useMutation({
    mutationFn: (data: VideoSessionCreate) => createVideoSession(data),
    onMutate: () => {
      setState((prev) => ({
        ...prev,
        connectionState: "connecting",
        error: null,
      }));
    },
    onSuccess: (session) => {
      sessionRef.current = session.id;
      setState({
        session,
        connectionState: "connected",
        error: null,
        transcript: session.transcripts ?? [],
        isMuted: false,
      });
      queryClient.invalidateQueries({ queryKey: videoKeys.sessions() });
    },
    onError: (error: Error) => {
      setState({
        session: null,
        connectionState: "error",
        error: error.message || "Failed to create video session",
        transcript: [],
        isMuted: false,
      });
    },
  });

  // End session mutation
  const endMutation = useMutation({
    mutationFn: () => {
      if (!sessionRef.current) {
        throw new Error("No active session to end");
      }
      return endVideoSession(sessionRef.current);
    },
    onMutate: () => {
      setState((prev) => ({
        ...prev,
        connectionState: "disconnecting",
      }));
    },
    onSuccess: () => {
      setState({
        session: null,
        connectionState: "idle",
        error: null,
        transcript: [],
        isMuted: false,
      });
      sessionRef.current = null;
      queryClient.invalidateQueries({ queryKey: videoKeys.sessions() });
    },
    onError: (error: Error) => {
      setState((prev) => ({
        ...prev,
        connectionState: "error",
        error: error.message || "Failed to end video session",
      }));
    },
  });

  // Start haircheck (device test)
  const startHaircheck = useCallback(() => {
    setState({
      session: null,
      connectionState: "haircheck",
      error: null,
      transcript: [],
      isMuted: false,
    });
  }, []);

  // Cancel haircheck
  const cancelHaircheck = useCallback(() => {
    setState({
      session: null,
      connectionState: "idle",
      error: null,
      transcript: [],
      isMuted: false,
    });
  }, []);

  // Join call - creates session and transitions to connected
  const joinCall = useCallback(
    (sessionType: SessionType = "chat", options?: { leadId?: string }) => {
      createMutation.mutate({
        session_type: sessionType,
        lead_id: options?.leadId,
      });
    },
    [createMutation]
  );

  // Leave call - ends session
  const leaveCall = useCallback(() => {
    endMutation.mutate();
  }, [endMutation]);

  // Reset state (for error recovery)
  const reset = useCallback(() => {
    setState({
      session: null,
      connectionState: "idle",
      error: null,
      transcript: [],
      isMuted: false,
    });
    sessionRef.current = null;
  }, []);

  // Toggle mute state
  const toggleMute = useCallback(() => {
    setState((prev) => ({
      ...prev,
      isMuted: !prev.isMuted,
    }));
  }, []);

  return {
    // State
    session: state.session,
    connectionState: state.connectionState,
    error: state.error,
    transcript: state.transcript,
    isMuted: state.isMuted,
    roomUrl: state.session?.room_url ?? null,

    // Derived state
    isConnecting: state.connectionState === "connecting",
    isActive: state.connectionState === "connected",

    // Loading states
    isCreating: createMutation.isPending,
    isEnding: endMutation.isPending,

    // Actions
    startHaircheck,
    cancelHaircheck,
    startSession: joinCall,
    endSession: leaveCall,
    joinCall,
    leaveCall,
    toggleMute,
    reset,
  };
}

/**
 * Hook for listing video sessions.
 */
export function useVideoSessions(params?: {
  limit?: number;
  offset?: number;
  session_type?: SessionType;
  status?: VideoSessionStatus;
}) {
  return useQuery({
    queryKey: [...videoKeys.sessions(), params],
    queryFn: () => listVideoSessions(params),
  });
}

/**
 * Hook for fetching a specific video session.
 */
export function useVideoSessionQuery(sessionId: string | null) {
  return useQuery({
    queryKey: videoKeys.session(sessionId ?? ""),
    queryFn: () => getVideoSession(sessionId!),
    enabled: !!sessionId,
  });
}
