import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/hooks/useAuth';
import { useRoutingDecision } from '@/hooks/useOnboarding';

export interface ProtectedRouteProps {
  children: React.ReactNode;
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const { data: routingDecision, isLoading: routingLoading } = useRoutingDecision(!authLoading && isAuthenticated);
  const location = useLocation();

  // Show ARIA presence pulse while checking auth or routing
  if (authLoading || (isAuthenticated && routingLoading)) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: 'var(--bg-primary)' }}>
        <div
          className="h-12 w-12 rounded-full aria-breathe"
          style={{ backgroundColor: 'var(--accent)', opacity: 0.15 }}
        />
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
