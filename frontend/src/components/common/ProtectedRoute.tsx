import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { useRoutingDecision } from '@/hooks/useOnboarding';

export interface ProtectedRouteProps {
  children: React.ReactNode;
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const { data: routingDecision, isLoading: routingLoading } = useRoutingDecision();
  const location = useLocation();

  // Show loading spinner while checking auth or routing
  if (authLoading || (isAuthenticated && routingLoading)) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[var(--bg-primary)]">
        <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-[var(--accent)]" />
      </div>
    );
  }

  // Not authenticated -> redirect to login
  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Authenticated but onboarding incomplete -> redirect to /onboarding
  // Skip this check if already on /onboarding to avoid redirect loops
  if (routingDecision?.route === 'onboarding' && location.pathname !== '/onboarding') {
    return <Navigate to="/onboarding" replace />;
  }

  return <>{children}</>;
}
