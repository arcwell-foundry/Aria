import { useState, useEffect, useCallback, useRef } from "react";

const POLL_INTERVAL = 30_000; // 30 seconds
const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

interface HealthResponse {
  status: "healthy" | "degraded" | "unhealthy";
  services: Record<string, "up" | "degraded" | "down">;
  uptime_seconds: number;
  version: string;
}

export interface ServiceHealthState {
  /** True when overall status is "healthy" or when we haven't checked yet. */
  isHealthy: boolean;
  /** Services that are degraded or down, as a name→status map. */
  degradedServices: Record<string, "degraded" | "down">;
  /** ISO timestamp of the last successful health check. */
  lastCheck: string | null;
  /** True while the very first check is in flight. */
  isLoading: boolean;
}

/**
 * Polls GET /api/v1/health every 30 seconds and exposes service health state.
 *
 * The hook only runs while the user is authenticated (pass `enabled` flag)
 * to avoid hammering the endpoint on the login page.
 */
export function useServiceHealth(enabled = true): ServiceHealthState {
  const [state, setState] = useState<ServiceHealthState>({
    isHealthy: true,
    degradedServices: {},
    lastCheck: null,
    isLoading: true,
  });
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const checkHealth = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/api/v1/health`, {
        signal: AbortSignal.timeout(10_000),
      });

      if (!res.ok) {
        setState((prev) => ({
          ...prev,
          isHealthy: false,
          degradedServices: { api: "down" },
          lastCheck: new Date().toISOString(),
          isLoading: false,
        }));
        return;
      }

      const data: HealthResponse = await res.json();

      const degraded: Record<string, "degraded" | "down"> = {};
      for (const [name, status] of Object.entries(data.services)) {
        if (status === "degraded" || status === "down") {
          degraded[name] = status;
        }
      }

      setState({
        isHealthy: data.status === "healthy",
        degradedServices: degraded,
        lastCheck: new Date().toISOString(),
        isLoading: false,
      });
    } catch {
      // Network failure — mark API as down but don't spam the user;
      // the OfflineBanner already handles full-offline scenarios.
      setState((prev) => ({
        ...prev,
        isHealthy: false,
        degradedServices: { api: "down" },
        lastCheck: prev.lastCheck, // keep last successful timestamp
        isLoading: false,
      }));
    }
  }, []);

  useEffect(() => {
    if (!enabled) {
      // Reset when disabled (e.g. user logs out)
      setState({ isHealthy: true, degradedServices: {}, lastCheck: null, isLoading: true });
      return;
    }

    // Initial check
    checkHealth();

    // Poll on interval
    timerRef.current = setInterval(checkHealth, POLL_INTERVAL);

    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [enabled, checkHealth]);

  return state;
}

/**
 * Format degraded service names into a human-readable string.
 * e.g. { neo4j: "degraded", tavus: "down" } → "Neo4j, Tavus"
 */
export function formatDegradedServices(services: Record<string, string>): string {
  return Object.keys(services)
    .map((name) => name.charAt(0).toUpperCase() + name.slice(1))
    .join(", ");
}
