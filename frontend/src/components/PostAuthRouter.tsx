import { Navigate } from "react-router-dom";
import { useRoutingDecision } from "@/hooks/useOnboarding";

const ROUTE_MAP: Record<string, string> = {
  onboarding: "/onboarding",
  resume: "/onboarding",
  dashboard: "/dashboard",
  admin: "/dashboard",
};

export function PostAuthRouter() {
  const { data, isLoading } = useRoutingDecision();

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-primary">
        <div className="flex flex-col items-center gap-4">
          <div className="w-2 h-2 rounded-full bg-interactive animate-pulse" />
        </div>
      </div>
    );
  }

  const destination = data?.route ? ROUTE_MAP[data.route] : "/dashboard";
  return <Navigate to={destination} replace />;
}
