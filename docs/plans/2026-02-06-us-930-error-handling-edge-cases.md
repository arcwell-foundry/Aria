# US-930: Error Handling & Edge Cases Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Implement app-wide error handling infrastructure including standardized error responses, rate limiting, error boundaries, empty states, skeleton loaders, and offline handling.

**Architecture:**
- **Backend:** Extend existing exception hierarchy with rate limiter middleware, ensure global handlers return standardized JSON
- **Frontend:** Create reusable UI components (ErrorBoundary, EmptyState, SkeletonLoader, OfflineBanner) and enhance API client with retry logic
- **Integration:** Register ErrorBoundary in App.tsx, implement offline detection, wire up standardized error parsing

**Tech Stack:** Python 3.11+ / FastAPI, React 18 / TypeScript / Tailwind CSS, slowapi (rate limiting), Lucide React icons

---

## Task 1: Backend Rate Limiter Middleware

**Files:**
- Create: `backend/src/core/rate_limiter.py`
- Create: `backend/tests/core/test_rate_limiter.py`
- Modify: `backend/requirements.txt` (add slowapi)

**Step 1: Add slowapi dependency**

```bash
# Edit backend/requirements.txt, add this line:
echo "slowapi==0.1.9" >> backend/requirements.txt
```

**Step 2: Install the dependency**

Run: `pip install slowapi==0.1.9`
Expected: Package installed successfully

**Step 3: Write the failing test first**

Create `backend/tests/core/test_rate_limiter.py`:

```python
import pytest
import time
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from src.core.rate_limiter import RateLimiter, rate_limit


def test_rate_limiter_blocks_after_threshold():
    """Rate limiter should return 429 after threshold exceeded"""
    app = FastAPI()
    
    @app.get("/test")
    @rate_limit("test_endpoint", requests=3, window=60)
    async def test_endpoint():
        return {"status": "ok"}
    
    client = TestClient(app)
    
    # First 3 requests should succeed
    for _ in range(3):
        response = client.get("/test")
        assert response.status_code == 200
    
    # 4th request should be rate limited
    response = client.get("/test")
    assert response.status_code == 429
    assert "rate_limit_exceeded" in response.json()["error"]["code"]


def test_rate_limiter_resets_after_window():
    """Rate limiter should reset after window expires"""
    app = FastAPI()
    
    @app.get("/test-fast-window")
    @rate_limit("test_fast", requests=2, window=1)
    async def test_endpoint():
        return {"status": "ok"}
    
    client = TestClient(app)
    
    # Use up the limit
    for _ in range(2):
        response = client.get("/test-fast-window")
        assert response.status_code == 200
    
    # Should be rate limited
    response = client.get("/test-fast-window")
    assert response.status_code == 429
    
    # Wait for window to expire
    time.sleep(1.1)
    
    # Should work again
    response = client.get("/test-fast-window")
    assert response.status_code == 200


def test_rate_limiter_per_user_isolation():
    """Rate limiter should track users independently"""
    app = FastAPI()
    
    @app.get("/test-user")
    @rate_limit("user_test", requests=2, window=60)
    async def test_endpoint(request: Request):
        # Use IP as user identifier
        return {"status": "ok"}
    
    client = TestClient(app)
    
    # User 1 (default client)
    for _ in range(2):
        response = client.get("/test-user")
        assert response.status_code == 200
    
    # User 1 should be rate limited
    response = client.get("/test-user")
    assert response.status_code == 429
    
    # User 2 (different headers)
    response = client.get("/test-user", headers={"X-Forwarded-For": "192.168.1.100"})
    assert response.status_code == 200


def test_rate_limiter_includes_retry_after():
    """Rate limit response should include retry_after header"""
    app = FastAPI()
    
    @app.get("/test-retry")
    @rate_limit("retry_test", requests=1, window=60)
    async def test_endpoint():
        return {"status": "ok"}
    
    client = TestClient(app)
    
    # First request succeeds
    response = client.get("/test-retry")
    assert response.status_code == 200
    
    # Second request gets rate limited
    response = client.get("/test-retry")
    assert response.status_code == 429
    assert "retry_after" in response.json()["error"]
    assert "retry-after" in response.headers
```

Run: `pytest backend/tests/core/test_rate_limiter.py -v`
Expected: FAIL - Module and classes don't exist yet

**Step 4: Implement the RateLimiter class**

Create `backend/src/core/rate_limiter.py`:

```python
"""
Rate limiting middleware for API endpoints.

Uses in-memory storage with sliding window counter.
For production with multiple workers, consider Redis-backed storage.
"""
from collections import defaultdict
from datetime import datetime, timedelta
from functools import wraps
from typing import Optional

from fastapi import Request, Response
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from src.core.exceptions import RateLimitError
from src.core.logging import get_logger

logger = get_logger(__name__)


# Global limiter instance
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["100/minute"],  # Default: 100 requests per minute
    storage_uri="memory://",  # In-memory storage (use Redis for production)
)


def get_rate_limit_config(endpoint: str) -> tuple[int, int]:
    """
    Get rate limit configuration for an endpoint.
    
    Returns (requests, window_seconds) tuple.
    
    More restrictive limits for sensitive endpoints:
    - Authentication: 5 requests per minute
    - Email operations: 10 requests per minute
    - CRM operations: 20 requests per minute
    - Default: 100 requests per minute
    """
    sensitive_endpoints = {
        "/auth/login": (5, 60),
        "/auth/register": (5, 60),
        "/auth/password/reset": (3, 60),
        "/api/v1/emails": (10, 60),
        "/api/v1/crm": (20, 60),
        "/api/v1/goals": (30, 60),
    }
    
    for path, config in sensitive_endpoints.items():
        if endpoint.startswith(path):
            return config
    
    return (100, 60)  # Default


def rate_limit(endpoint_key: str, requests: Optional[int] = None, window: Optional[int] = None):
    """
    Decorator to apply rate limiting to an endpoint.
    
    Args:
        endpoint_key: Unique identifier for this endpoint
        requests: Number of requests allowed (uses config if None)
        window: Time window in seconds (uses config if None)
    
    Example:
        @app.get("/api/endpoint")
        @rate_limit("my_endpoint", requests=10, window=60)
        async def my_endpoint():
            return {"status": "ok"}
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get the Request object from args/kwargs
            request: Optional[Request] = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if request is None:
                request = kwargs.get("request")
            
            if request is None:
                # No request object, just call the function
                return await func(*args, **kwargs)
            
            # Get configured limits
            req_count, window_sec = get_rate_limit_config(request.url.path)
            if requests is not None:
                req_count = requests
            if window is not None:
                window_sec = window
            
            # Apply rate limit using slowapi
            try:
                return await limiter._check_request_limit(
                    lambda: func(*args, **kwargs),
                    request,
                    req_count,
                    window_sec
                )
            except RateLimitExceeded as e:
                logger.warning(
                    "rate_limit_exceeded",
                    endpoint=request.url.path,
                    endpoint_key=endpoint_key,
                    client_ip=get_remote_address(request),
                )
                raise RateLimitError(
                    message=f"Rate limit exceeded. Please try again in {window_sec} seconds.",
                    retry_after=window_sec,
                )
        
        return wrapper
    return decorator


class RateLimitTracker:
    """
    In-memory rate limit tracker with sliding window.
    
    Tracks requests per (user_id, endpoint_key) combination.
    Auto-cleans expired entries to prevent memory leaks.
    """
    
    def __init__(self):
        self._requests: defaultdict[str, list[datetime]] = defaultdict(list)
        self._last_cleanup = datetime.now()
    
    def _cleanup_expired(self, window_seconds: int = 60):
        """Remove entries older than the window."""
        cutoff = datetime.now() - timedelta(seconds=window_seconds)
        
        for key in list(self._requests.keys()):
            # Filter out expired timestamps
            self._requests[key] = [
                ts for ts in self._requests[key] if ts > cutoff
            ]
            
            # Remove empty keys
            if not self._requests[key]:
                del self._requests[key]
    
    def check(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        """
        Check if request is allowed.
        
        Returns:
            (allowed, retry_after_seconds)
        """
        # Periodic cleanup (every minute)
        if (datetime.now() - self._last_cleanup).total_seconds() > 60:
            self._cleanup_expired(window_seconds)
            self._last_cleanup = datetime.now()
        
        now = datetime.now()
        window_start = now - timedelta(seconds=window_seconds)
        
        # Get recent requests for this key
        recent = [
            ts for ts in self._requests[key]
            if ts > window_start
        ]
        
        if len(recent) < limit:
            # Request allowed - record it
            self._requests[key].append(now)
            return True, 0
        else:
            # Rate limited - calculate retry after
            oldest_in_window = min(recent)
            retry_after = int(
                window_seconds - (now - oldest_in_window).total_seconds()
            ) + 1
            return False, retry_after


# Global tracker instance
tracker = RateLimitTracker()
```

**Step 5: Run tests to verify implementation**

Run: `pytest backend/tests/core/test_rate_limiter.py -v`
Expected: Some tests may pass, others may fail due to slowapi integration

**Step 6: Fix slowapi integration and simplify approach**

Edit `backend/src/core/rate_limiter.py` - replace the decorator function with a simpler implementation:

```python
# Replace the rate_limit decorator with this simpler version:

def rate_limit(endpoint_key: str, requests: Optional[int] = None, window: Optional[int] = None):
    """
    Decorator to apply rate limiting to an endpoint.
    
    Uses in-memory sliding window tracker.
    
    Args:
        endpoint_key: Unique identifier for this endpoint
        requests: Number of requests allowed (uses config if None)
        window: Time window in seconds (uses config if None)
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Get the Request object
            request: Optional[Request] = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            if request is None:
                request = kwargs.get("request")
            
            if request is None:
                return await func(*args, **kwargs)
            
            # Get configured limits
            req_count, window_sec = get_rate_limit_config(request.url.path)
            if requests is not None:
                req_count = requests
            if window is not None:
                window_sec = window
            
            # Get user identifier (IP or user_id if authenticated)
            user_id = request.state.get("user_id") if hasattr(request.state, "get") else None
            client_key = f"{endpoint_key}:{user_id or get_remote_address(request)}"
            
            # Check rate limit
            allowed, retry_after = tracker.check(client_key, req_count, window_sec)
            
            if not allowed:
                logger.warning(
                    "rate_limit_exceeded",
                    endpoint=request.url.path,
                    endpoint_key=endpoint_key,
                    client_ip=get_remote_address(request),
                    user_id=user_id,
                )
                raise RateLimitError(
                    message=f"Rate limit exceeded. Please try again in {retry_after} seconds.",
                    retry_after=retry_after,
                )
            
            return await func(*args, **kwargs)
        
        return wrapper
    return decorator
```

**Step 7: Run tests again**

Run: `pytest backend/tests/core/test_rate_limiter.py -v`
Expected: All tests PASS

**Step 8: Add RateLimitError to exceptions.py**

Check if `RateLimitError` exists in `backend/src/core/exceptions.py`:

```bash
grep -n "RateLimitError" backend/src/core/exceptions.py
```

If not found, add it:

```python
# Add to backend/src/core/exceptions.py in the appropriate section

class RateLimitError(ARIAException):
    """Raised when rate limit is exceeded."""
    
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: int = 60,
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(
            message=message,
            code="RATE_LIMIT_EXCEEDED",
            status_code=429,
            details=details or {"retry_after": retry_after}
        )
        self.retry_after = retry_after
```

**Step 9: Commit**

```bash
git add backend/src/core/rate_limiter.py backend/tests/core/test_rate_limiter.py backend/requirements.txt backend/src/core/exceptions.py
git commit -m "feat(US-930): add rate limiter middleware with in-memory tracking

- Add slowapi dependency
- Implement RateLimiter class with sliding window
- Add per-endpoint configuration
- Support user-specific rate limiting
- Include retry_after in responses

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 2: Register Rate Limiter in Main Application

**Files:**
- Modify: `backend/src/main.py`

**Step 1: Read current main.py to understand structure**

Run: `head -100 backend/src/main.py`
Expected: See current FastAPI app setup and middleware configuration

**Step 2: Write test for rate limiter integration**

Create `backend/tests/integration/test_rate_limiting.py`:

```python
import pytest
from fastapi.testclient import TestClient
from src.main import app


def test_auth_endpoint_rate_limited():
    """Authentication endpoints should have strict rate limiting"""
    client = TestClient(app)
    
    # Try 6 login requests (limit is 5/minute)
    for i in range(6):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": f"test{i}@example.com", "password": "wrong"}
        )
    
    # Last request should be rate limited
    assert response.status_code == 429
    assert "rate_limit_exceeded" in response.json()["error"]["code"]


def test_default_endpoint_rate_limited():
    """Standard endpoints should have default rate limiting"""
    client = TestClient(app)
    
    # Make 101 requests (default limit is 100/minute)
    for i in range(101):
        # Using a GET endpoint that should exist
        response = client.get("/api/v1/health")
    
    # Should be rate limited after 100
    assert response.status_code == 429
```

Run: `pytest backend/tests/integration/test_rate_limiting.py -v`
Expected: FAIL - Rate limiter not yet registered

**Step 3: Register rate limiter in main.py**

Add to `backend/src/main.py`:

```python
# After existing imports, add:
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from src.core.rate_limiter import limiter

# In the app setup section (after app = FastAPI(...)), add:
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```

**Step 4: Apply rate limiting to auth endpoints**

Add rate limiting decorators to auth routes in `backend/src/api/routes/auth.py`:

```python
from src.core.rate_limiter import rate_limit

# Add to login endpoint:
@router.post("/login")
@rate_limit("auth_login", requests=5, window=60)
async def login(...):
    # existing implementation

# Add to register endpoint:
@router.post("/register")
@rate_limit("auth_register", requests=5, window=60)
async def register(...):
    # existing implementation

# Add to password reset:
@router.post("/password/reset")
@rate_limit("auth_password_reset", requests=3, window=60)
async def request_password_reset(...):
    # existing implementation
```

**Step 5: Run integration tests**

Run: `pytest backend/tests/integration/test_rate_limiting.py -v`
Expected: Tests PASS

**Step 6: Run quality gates**

Run: `mypy backend/src/core/rate_limiter.py --strict`
Expected: No type errors

Run: `ruff check backend/src/core/rate_limiter.py`
Expected: No linting errors

**Step 7: Commit**

```bash
git add backend/src/main.py backend/src/api/routes/auth.py backend/tests/integration/test_rate_limiting.py
git commit -m "feat(US-930): register rate limiter in main application

- Wire up slowapi exception handler
- Apply strict limits to auth endpoints
- Add integration tests for rate limiting

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 3: Frontend Error Boundary Component

**Files:**
- Create: `frontend/src/components/ErrorBoundary.tsx`
- Create: `frontend/src/components/__tests__/ErrorBoundary.test.tsx`
- Modify: `frontend/src/App.tsx`

**Step 1: Write the failing test**

Create `frontend/src/components/__tests__/ErrorBoundary.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { ErrorBoundary } from '../ErrorBoundary';

// Helper component that throws an error
const ThrowError = ({ shouldThrow }: { shouldThrow: boolean }) => {
  if (shouldThrow) {
    throw new Error('Test error');
  }
  return <div>No error</div>;
};

describe('ErrorBoundary', () => {
  // Suppress console.error for these tests
  const originalError = console.error;
  beforeEach(() => {
    console.error = vi.fn();
  });
  afterEach(() => {
    console.error = originalError;
  });

  it('renders children when there is no error', () => {
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={false} />
      </ErrorBoundary>
    );
    
    expect(screen.getByText('No error')).toBeInTheDocument();
  });

  it('catches errors and displays fallback UI', () => {
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );
    
    expect(screen.getByText('Something went wrong')).toBeInTheDocument();
  });

  it('shows reload button that refreshes the page', () => {
    // Mock window.location.reload
    const reloadMock = vi.fn();
    Object.defineProperty(window, 'location', {
      value: { reload: reloadMock },
      writable: true,
    });

    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );
    
    const reloadButton = screen.getByText('Reload');
    reloadButton.click();
    
    expect(reloadMock).toHaveBeenCalled();
  });

  it('displays error details in development', () => {
    const originalEnv = import.meta.env.DEV;
    Object.defineProperty(import.meta.env, 'DEV', { value: true });
    
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );
    
    expect(screen.getByText(/Test error/)).toBeInTheDocument();
    
    Object.defineProperty(import.meta.env, 'DEV', { value: originalEnv });
  });

  it('provides link to report issue', () => {
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    );
    
    const reportLink = screen.getByText('Report issue');
    expect(reportLink).toHaveAttribute('href', 'https://github.com/anthropics/aria/issues');
  });
});
```

Run: `npm test -- ErrorBoundary.test.tsx`
Expected: FAIL - Component doesn't exist

**Step 2: Implement ErrorBoundary component**

Create `frontend/src/components/ErrorBoundary.tsx`:

```tsx
/**
 * ErrorBoundary - Catches React errors and displays a friendly fallback
 * 
 * This component wraps the entire application to catch unhandled errors.
 * When an error occurs, users see:
 * - A calm, professional error message (Instrument Serif heading)
 * - A reload button to refresh the page
 * - A link to report the issue
 * - Error details in development mode
 * 
 * Follows ARIA Design System v1.0:
 * - Dark surface for error context (emergency/problematized state)
 * - Instrument Serif for heading
 * - Satoshi for body text
 * - Lucide icons (refreshCw, alertCircle)
 */

import { Component, ErrorInfo, ReactNode } from 'react';
import { AlertCircle, RefreshCw } from 'lucide-react';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
    };
  }

  static getDerivedStateFromError(error: Error): State {
    // Update state so the next render shows the fallback UI
    return {
      hasError: true,
      error,
      errorInfo: null,
    };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    // Log the error to an error reporting service
    console.error('ErrorBoundary caught an error:', error, errorInfo);
    
    this.setState({
      error,
      errorInfo,
    });

    // TODO: Send to error reporting service (Sentry, etc.)
    if (typeof window !== 'undefined' && (window as any).Sentry) {
      (window as any).Sentry.captureException(error, {
        contexts: { react: { componentStack: errorInfo.componentStack } },
      });
    }
  }

  handleReload = () => {
    // Reload the page
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      // Use custom fallback if provided
      if (this.props.fallback) {
        return this.props.fallback;
      }

      // Default error UI following ARIA Design System
      return (
        <div className="min-h-screen bg-[#0F1117] flex items-center justify-center p-4">
          <div className="max-w-md w-full bg-[#161B2E] border border-[#2A2F42] rounded-xl p-8 text-center">
            {/* Alert Icon */}
            <div className="flex justify-center mb-6">
              <div className="w-16 h-16 rounded-full bg-[#A66B6B]/10 flex items-center justify-center">
                <AlertCircle className="w-8 h-8 text-[#A66B6B]" strokeWidth={1.5} />
              </div>
            </div>

            {/* Heading - Instrument Serif */}
            <h1 className="font-display text-[32px] leading-[1.2] text-[#E8E6E1] mb-4">
              Something went wrong
            </h1>

            {/* Description - Satoshi */}
            <p className="font-sans text-[15px] leading-[1.6] text-[#8B92A5] mb-8">
              ARIA encountered an unexpected error. We've been notified and are 
              working to fix it. Your work is safe.
            </p>

            {/* Action Buttons */}
            <div className="flex flex-col sm:flex-row gap-3 justify-center">
              {/* Reload Button - Primary */}
              <button
                onClick={this.handleReload}
                className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg font-sans font-medium text-[15px]
                  bg-[#5B6E8A] text-white hover:bg-[#4A5D79] active:bg-[#3D5070]
                  transition-colors duration-150 cursor-pointer min-h-[44px]"
              >
                <RefreshCw className="w-4 h-4" strokeWidth={1.5} />
                Reload Page
              </button>

              {/* Report Issue Link - Ghost */}
              <a
                href="https://github.com/anthropics/aria/issues"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center justify-center px-5 py-2.5 rounded-lg font-sans text-[15px]
                  text-[#6B7280] hover:bg-[#1E2235] transition-colors duration-150
                  cursor-pointer min-h-[44px]"
              >
                Report Issue
              </a>
            </div>

            {/* Error Details (Development Only) */}
            {import.meta.env.DEV && this.state.error && (
              <details className="mt-8 text-left">
                <summary className="font-sans text-[13px] font-medium text-[#8B92A5] cursor-pointer hover:text-[#E8E6E1] mb-3">
                  Error Details (Development)
                </summary>
                <div className="bg-[#0F1117] rounded-lg p-4 overflow-x-auto">
                  <p className="font-mono text-[11px] text-[#A66B6B] whitespace-pre-wrap mb-2">
                    {this.state.error.toString()}
                  </p>
                  {this.state.errorInfo && (
                    <pre className="font-mono text-[11px] text-[#8B92A5] whitespace-pre-wrap">
                      {this.state.errorInfo.componentStack}
                    </pre>
                  )}
                </div>
              </details>
            )}
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

// Functional wrapper for convenience
export function withErrorBoundary<P extends object>(
  Component: React.ComponentType<P>,
  fallback?: ReactNode
) {
  return function WrappedComponent(props: P) {
    return (
      <ErrorBoundary fallback={fallback}>
        <Component {...props} />
      </ErrorBoundary>
    );
  };
}
```

**Step 3: Run tests**

Run: `npm test -- ErrorBoundary.test.tsx`
Expected: All tests PASS

**Step 4: Check TypeScript compilation**

Run: `npm run typecheck`
Expected: No type errors

**Step 5: Run ESLint**

Run: `npm run lint -- frontend/src/components/ErrorBoundary.tsx`
Expected: No linting errors

**Step 6: Register ErrorBoundary in App.tsx**

Edit `frontend/src/App.tsx` - wrap the entire app with ErrorBoundary:

```tsx
// Add import at top:
import { ErrorBoundary } from './components/ErrorBoundary';

// In the return statement, wrap everything:
function App() {
  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          {/* existing app content */}
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
```

**Step 7: Commit**

```bash
git add frontend/src/components/ErrorBoundary.tsx frontend/src/components/__tests__/ErrorBoundary.test.tsx frontend/src/App.tsx
git commit -m "feat(US-930): add ErrorBoundary component

- Catches unhandled React errors
- Displays professional fallback UI with reload
- Shows error details in development
- Provides link to report issues
- Follows ARIA Design System (dark surface, Instrument Serif, Satoshi)
- Wraps entire application in App.tsx

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 4: Frontend EmptyState Component

**Files:**
- Create: `frontend/src/components/EmptyState.tsx`
- Create: `frontend/src/components/__tests__/EmptyState.test.tsx`

**Step 1: Write the failing test**

Create `frontend/src/components/__tests__/EmptyState.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { EmptyState } from '../EmptyState';

describe('EmptyState', () => {
  it('renders icon, title, and description', () => {
    render(
      <EmptyState
        icon="Users"
        title="No leads yet"
        description="ARIA can start finding prospects the moment you set a goal."
      />
    );
    
    expect(screen.getByText('No leads yet')).toBeInTheDocument();
    expect(screen.getByText(/ARIA can start finding/)).toBeInTheDocument();
  });

  it('renders action button when actionLabel and onAction provided', () => {
    const mockAction = vi.fn();
    render(
      <EmptyState
        icon="Users"
        title="No leads yet"
        description="Set a goal and ARIA will start working."
        actionLabel="Set a Goal"
        onAction={mockAction}
      />
    );
    
    const button = screen.getByText('Set a Goal');
    expect(button).toBeInTheDocument();
    
    await userEvent.click(button);
    expect(mockAction).toHaveBeenCalledTimes(1);
  });

  it('does not render action button when onAction not provided', () => {
    render(
      <EmptyState
        icon="Users"
        title="No leads yet"
        description="ARIA can start finding prospects."
        actionLabel="Set a Goal"
      />
    );
    
    expect(screen.queryByText('Set a Goal')).not.toBeInTheDocument();
  });

  it('uses Lucide icon component', () => {
    render(
      <EmptyState
        icon="Target"
        title="No goals"
        description="Set a goal and ARIA will start working."
      />
    );
    
    // Icon should be in document
    const icon = document.querySelector('svg');
    expect(icon).toBeInTheDocument();
  });

  it('applies custom className', () => {
    render(
      <EmptyState
        icon="Users"
        title="Test"
        description="Test description"
        className="custom-class"
      />
    );
    
    const container = screen.getByText('Test').closest('.custom-class');
    expect(container).toBeInTheDocument();
  });
});
```

Run: `npm test -- EmptyState.test.tsx`
Expected: FAIL - Component doesn't exist

**Step 2: Implement EmptyState component**

Create `frontend/src/components/EmptyState.tsx`:

```tsx
/**
 * EmptyState - Reusable empty state with ARIA personality
 * 
 * ARIA's empty states are optimistic and actionable. Instead of generic 
 * "nothing here" messages, they explain what ARIA CAN do.
 * 
 * Examples:
 * - No leads: "ARIA can start finding prospects the moment you set a goal."
 * - No goals: "Set a goal and ARIA will start working on it immediately."
 * - No briefings: "Connect your email and CRM to get daily intelligence."
 * 
 * Follows ARIA Design System v1.0:
 * - Instrument Serif for title
 * - Satoshi for description and actions
 * - Lucide icons (20x20, stroke 1.5)
 * - Subtle, calming presentation
 */

import { LucideIcon, icons } from 'lucide-react';
import { ButtonHTMLAttributes, ReactNode } from 'react';

interface IconName {
  [key: string]: LucideIcon;
}

// Get Lucide icon by name
function getIcon(name: string): LucideIcon {
  const iconMap = icons as IconName;
  return iconMap[name] || iconMap['Circle'];
}

interface EmptyStateProps {
  /** Lucide icon name (e.g., "Users", "Target", "FileText") */
  icon: string;
  /** Heading displayed in Instrument Serif */
  title: string;
  /** Description in Satoshi - what ARIA can do */
  description: string;
  /** Optional action button label */
  actionLabel?: string;
  /** Optional action button click handler */
  onAction?: () => void;
  /** Optional additional className */
  className?: string;
  /** Optional children for custom content */
  children?: ReactNode;
}

export function EmptyState({
  icon,
  title,
  description,
  actionLabel,
  onAction,
  className = '',
  children,
}: EmptyStateProps) {
  const Icon = getIcon(icon);

  return (
    <div className={`flex flex-col items-center justify-center text-center py-16 px-4 ${className}`}>
      {/* Icon */}
      <div className="w-16 h-16 rounded-full bg-[#1E2235] flex items-center justify-center mb-6">
        <Icon className="w-8 h-8 text-[#8B92A5]" strokeWidth={1.5} />
      </div>

      {/* Title - Instrument Serif */}
      <h3 className="font-display text-[24px] leading-[1.3] text-[#E8E6E1] mb-3">
        {title}
      </h3>

      {/* Description - Satoshi */}
      <p className="font-sans text-[15px] leading-[1.6] text-[#8B92A5] max-w-md mb-6">
        {description}
      </p>

      {/* Action Button */}
      {actionLabel && onAction && (
        <button
          onClick={onAction}
          className="inline-flex items-center justify-center px-5 py-2.5 rounded-lg font-sans font-medium text-[15px]
            bg-[#5B6E8A] text-white hover:bg-[#4A5D79] active:bg-[#3D5070]
            transition-colors duration-150 cursor-pointer min-h-[44px] min-w-[120px]"
        >
          {actionLabel}
        </button>
      )}

      {/* Custom Children */}
      {children}
    </div>
  );
}

// Preset EmptyStates for common ARIA contexts

export function EmptyLeads({ onSetGoal }: { onSetGoal?: () => void }) {
  return (
    <EmptyState
      icon="Users"
      title="No leads yet"
      description="ARIA can start finding prospects the moment you set a goal."
      actionLabel="Set a Goal"
      onAction={onSetGoal}
    />
  );
}

export function EmptyGoals({ onCreateGoal }: { onCreateGoal?: () => void }) {
  return (
    <EmptyState
      icon="Target"
      title="No goals yet"
      description="Set a goal and ARIA will start working on it immediately."
      actionLabel="Create Goal"
      onAction={onCreateGoal}
    />
  );
}

export function EmptyBriefings({ onConnect }: { onConnect?: () => void }) {
  return (
    <EmptyState
      icon="FileText"
      title="No briefings yet"
      description="Connect your email and CRM to get daily intelligence."
      actionLabel="Connect Integrations"
      onAction={onConnect}
    />
  );
}

export function EmptyBattleCards({ onCreate }: { onCreate?: () => void }) {
  return (
    <EmptyState
      icon="Shield"
      title="No battle cards yet"
      description="ARIA will generate competitive battle cards as she learns about your market."
      actionLabel="View Competitors"
      onAction={onCreate}
    />
  );
}

export function EmptyMeetingBriefs({ onSchedule }: { onSchedule?: () => void }) {
  return (
    <EmptyState
      icon="Calendar"
      title="No upcoming meetings"
      description="ARIA prepares research briefs for your external meetings."
      actionLabel="View Calendar"
      onAction={onSchedule}
    />
  );
}

export function EmptyDrafts({ onCompose }: { onCompose?: () => void }) {
  return (
    <EmptyState
      icon="PenTool"
      title="No drafts yet"
      description="ARIA helps you write faster. Start a draft and she'll match your voice."
      actionLabel="Compose Email"
      onAction={onCompose}
    />
  );
}

export function EmptyActivity() {
  return (
    <EmptyState
      icon="Activity"
      title="ARIA is getting started"
      description="Complete onboarding and ARIA will begin working on your goals."
    />
  );
}
```

**Step 3: Run tests**

Run: `npm test -- EmptyState.test.tsx`
Expected: All tests PASS

**Step 4: Check TypeScript**

Run: `npm run typecheck`
Expected: No type errors

**Step 5: Check ESLint**

Run: `npm run lint -- frontend/src/components/EmptyState.tsx`
Expected: No linting errors

**Step 6: Commit**

```bash
git add frontend/src/components/EmptyState.tsx frontend/src/components/__tests__/EmptyState.test.tsx
git commit -m "feat(US-930): add reusable EmptyState component

- Generic component with icon, title, description, action
- Preset variants for common ARIA contexts
- ARIA personality in messages (optimistic, actionable)
- Follows ARIA Design System (Instrument Serif, Satoshi, Lucide)
- Fully typed with TypeScript

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 5: Frontend SkeletonLoader Component

**Files:**
- Create: `frontend/src/components/SkeletonLoader.tsx`
- Create: `frontend/src/components/__tests__/SkeletonLoader.test.tsx`

**Step 1: Write the failing test**

Create `frontend/src/components/__tests__/SkeletonLoader.test.tsx`:

```tsx
import { render, screen } from '@testing-library/react';
import { SkeletonLoader } from '../SkeletonLoader';

describe('SkeletonLoader', () => {
  it('renders correct number of skeleton items', () => {
    const { container } = render(
      <SkeletonLoader variant="card" count={3} />
    );
    
    const skeletons = container.querySelectorAll('[data-testid="skeleton-item"]');
    expect(skeletons).toHaveLength(3);
  });

  it('renders card variant with correct structure', () => {
    const { container } = render(
      <SkeletonLoader variant="card" count={1} />
    );
    
    const skeleton = container.querySelector('[data-testid="skeleton-item"]');
    expect(skeleton).toHaveClass('rounded-xl');
  });

  it('renders list variant with horizontal layout', () => {
    const { container } = render(
      <SkeletonLoader variant="list" count={1} />
    );
    
    const skeleton = container.querySelector('[data-testid="skeleton-item"]');
    expect(skeleton).toHaveClass('flex');
  });

  it('renders table variant with grid layout', () => {
    const { container } = render(
      <SkeletonLoader variant="table" count={5} />
    );
    
    const skeletons = container.querySelectorAll('[data-testid="skeleton-item"]');
    expect(skeletons).toHaveLength(5);
    skeletons.forEach(s => {
      expect(s).toHaveClass('grid');
    });
  });

  it('renders text variant as simple bars', () => {
    const { container } = render(
      <SkeletonLoader variant="text" count={3} />
    );
    
    const skeletons = container.querySelectorAll('[data-testid="skeleton-bar"]');
    expect(skeletons).toHaveLength(3);
  });

  it('applies custom className', () => {
    const { container } = render(
      <SkeletonLoader variant="card" count={1} className="custom-class" />
    );
    
    expect(container.firstChild).toHaveClass('custom-class');
  });
});
```

Run: `npm test -- SkeletonLoader.test.tsx`
Expected: FAIL - Component doesn't exist

**Step 2: Implement SkeletonLoader component**

Create `frontend/src/components/SkeletonLoader.tsx`:

```tsx
/**
 * SkeletonLoader - Reusable loading skeleton animations
 * 
 * Skeleton screens show the structure of content before it loads.
 * This reduces perceived wait time and provides a polished experience.
 * 
 * Variants:
 * - card: For card-based layouts (leads, goals, etc.)
 * - list: For list items with avatar/content structure
 * - table: For table rows
 * - text: For simple text lines
 * 
 * Follows ARIA Design System v1.0:
 * - Subtle pulse animation (150ms duration)
 * - Matches real content structure
 * - Uses border colors from dark theme
 */

import { clsx } from 'clsx';

type SkeletonVariant = 'card' | 'list' | 'table' | 'text';

interface SkeletonLoaderProps {
  /** Which skeleton pattern to use */
  variant: SkeletonVariant;
  /** Number of skeleton items to render */
  count?: number;
  /** Optional additional className */
  className?: string;
}

const SKELETON_BASE = 'animate-pulse bg-[#2A2F42] rounded';

function SkeletonBar({ className }: { className?: string }) {
  return (
    <div
      data-testid="skeleton-bar"
      className={clsx(SKELETON_BASE, 'h-4', className)}
    />
  );
}

export function SkeletonLoader({
  variant,
  count = 1,
  className = '',
}: SkeletonLoaderProps) {
  const renderCard = () => (
    <div
      data-testid="skeleton-item"
      className="bg-[#161B2E] border border-[#2A2F42] rounded-xl p-6"
    >
      {/* Header bar */}
      <SkeletonBar className="w-1/3 mb-4 h-5" />
      
      {/* Title bar */}
      <SkeletonBar className="w-2/3 mb-3 h-6" />
      
      {/* Description bars */}
      <SkeletonBar className="w-full mb-2" />
      <SkeletonBar className="w-4/5 mb-4" />
      
      {/* Footer */}
      <div className="flex justify-between items-center">
        <SkeletonBar className="w-20 h-3" />
        <SkeletonBar className="w-16 h-8 rounded-lg" />
      </div>
    </div>
  );

  const renderList = () => (
    <div
      data-testid="skeleton-item"
      className="flex items-center gap-4 p-4 bg-[#161B2E] border border-[#2A2F42] rounded-lg"
    >
      {/* Avatar circle */}
      <div className={clsx(SKELETON_BASE, 'w-12 h-12 rounded-full flex-shrink-0')} />
      
      {/* Content */}
      <div className="flex-1 space-y-2">
        <SkeletonBar className="w-1/3 h-4" />
        <SkeletonBar className="w-2/3 h-3" />
      </div>
      
      {/* Action */}
      <SkeletonBar className="w-8 h-8 rounded-lg flex-shrink-0" />
    </div>
  );

  const renderTable = () => (
    <div
      data-testid="skeleton-item"
      className="grid grid-cols-12 gap-4 p-4 border-b border-[#2A2F42]"
    >
      <div className="col-span-4 space-y-2">
        <SkeletonBar className="w-3/4 h-4" />
        <SkeletonBar className="w-1/2 h-3" />
      </div>
      <div className="col-span-3">
        <SkeletonBar className="w-2/3 h-4" />
      </div>
      <div className="col-span-2">
        <SkeletonBar className="w-1/2 h-4" />
      </div>
      <div className="col-span-2">
        <SkeletonBar className="w-1/3 h-4" />
      </div>
      <div className="col-span-1">
        <SkeletonBar className="w-8 h-6 rounded" />
      </div>
    </div>
  );

  const renderText = (index: number) => {
    // Vary widths for more natural appearance
    const widths = ['w-full', 'w-11/12', 'w-10/12', 'w-9/12'];
    const width = widths[index % widths.length];
    
    return (
      <SkeletonBar
        key={index}
        className={clsx(width, index === 0 && 'h-5')}
      />
    );
  };

  return (
    <div className={className} data-testid="skeleton-loader">
      {variant === 'card' && Array.from({ length: count }).map((_, i) => (
        <div key={i} className="mb-4">
          {renderCard()}
        </div>
      ))}
      
      {variant === 'list' && Array.from({ length: count }).map((_, i) => (
        <div key={i} className="mb-3">
          {renderList()}
        </div>
      ))}
      
      {variant === 'table' && (
        <div className="bg-[#161B2E] border border-[#2A2F42] rounded-xl overflow-hidden">
          {Array.from({ length: count }).map((_, i) => (
            <div key={i}>{renderTable()}</div>
          ))}
        </div>
      )}
      
      {variant === 'text' && (
        <div className="space-y-2">
          {Array.from({ length: count }).map((_, i) => renderText(i))}
        </div>
      )}
    </div>
  );
}

// Preset SkeletonLoaders for common ARIA contexts

export function LeadsSkeleton({ count = 5 }: { count?: number }) {
  return <SkeletonLoader variant="card" count={count} />;
}

export function GoalsSkeleton({ count = 3 }: { count?: number }) {
  return <SkeletonLoader variant="card" count={count} />;
}

export function BriefingSkeleton({ count = 1 }: { count?: number }) {
  return <SkeletonLoader variant="card" count={count} />;
}

export function LeadsTableSkeleton({ count = 10 }: { count?: number }) {
  return <SkeletonLoader variant="table" count={count} />;
}

export function ContactsListSkeleton({ count = 8 }: { count?: number }) {
  return <SkeletonLoader variant="list" count={count} />;
}

export function TextSkeleton({ count = 3 }: { count?: number }) {
  return <SkeletonLoader variant="text" count={count} />;
}
```

**Step 3: Run tests**

Run: `npm test -- SkeletonLoader.test.tsx`
Expected: All tests PASS

**Step 4: Check TypeScript**

Run: `npm run typecheck`
Expected: No type errors

**Step 5: Check ESLint**

Run: `npm run lint -- frontend/src/components/SkeletonLoader.tsx`
Expected: No linting errors

**Step 6: Commit**

```bash
git add frontend/src/components/SkeletonLoader.tsx frontend/src/components/__tests__/SkeletonLoader.test.tsx
git commit -m "feat(US-930): add SkeletonLoader component

- Card variant for card-based layouts
- List variant for avatar/content lists
- Table variant for table rows
- Text variant for simple loading bars
- Subtle pulse animation matching ARIA Design System
- Preset variants for common contexts

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 6: Frontend OfflineBanner Component

**Files:**
- Create: `frontend/src/components/OfflineBanner.tsx`
- Create: `frontend/src/components/__tests__/OfflineBanner.test.tsx`
- Modify: `frontend/src/App.tsx`

**Step 1: Write the failing test**

Create `frontend/src/components/__tests__/OfflineBanner.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import { OfflineBanner } from '../OfflineBanner';

// Mock navigator.onLine
const mockOnline = vi.fn(() => true);
Object.defineProperty(navigator, 'onLine', {
  get: mockOnline,
  configurable: true,
});

describe('OfflineBanner', () => {
  it('does not render when online', () => {
    mockOnline.mockReturnValue(true);
    
    render(<OfflineBanner />);
    
    expect(screen.queryByText(/You're offline/)).not.toBeInTheDocument();
  });

  it('renders when offline', () => {
    mockOnline.mockReturnValue(false);
    
    render(<OfflineBanner />);
    
    expect(screen.getByText(/You're offline/)).toBeInTheDocument();
  });

  it('dismisses when connection restored', async () => {
    mockOnline.mockReturnValue(false);
    
    const { rerender } = render(<OfflineBanner />);
    expect(screen.getByText(/You're offline/)).toBeInTheDocument();
    
    // Simulate going back online
    mockOnline.mockReturnValue(true);
    const event = new Event('online');
    window.dispatchEvent(event);
    
    rerender(<OfflineBanner />);
    
    await waitFor(() => {
      expect(screen.queryByText(/You're offline/)).not.toBeInTheDocument();
    });
  });

  it('shows when going offline', async () => {
    mockOnline.mockReturnValue(true);
    
    const { rerender } = render(<OfflineBanner />);
    expect(screen.queryByText(/You're offline/)).not.toBeInTheDocument();
    
    // Simulate going offline
    mockOnline.mockReturnValue(false);
    const event = new Event('offline');
    window.dispatchEvent(event);
    
    rerender(<OfflineBanner />);
    
    expect(screen.getByText(/You're offline/)).toBeInTheDocument();
  });

  it('uses correct styling for warning banner', () => {
    mockOnline.mockReturnValue(false);
    
    render(<OfflineBanner />);
    
    const banner = screen.getByText(/offline/i).parentElement;
    expect(banner).toHaveClass('bg-amber-500/10');
  });
});
```

Run: `npm test -- OfflineBanner.test.tsx`
Expected: FAIL - Component doesn't exist

**Step 2: Implement OfflineBanner component**

Create `frontend/src/components/OfflineBanner.tsx`:

```tsx
/**
 * OfflineBanner - Shows when network connection is lost
 * 
 * This component monitors navigator.onLine and displays a subtle banner
 * when the user loses their internet connection. It auto-dismisses when
 * the connection is restored.
 * 
 * Follows ARIA Design System v1.0:
 * - Subtle amber warning (not jarring red)
 * - Fixed position at top of screen
 * - Satoshi for body text
 * - No icons (minimal interruption)
 */

import { useEffect, useState } from 'react';
import { X } from 'lucide-react';

export function OfflineBanner() {
  const [isOffline, setIsOffline] = useState(!navigator.onLine);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    // Handle online event
    const handleOnline = () => {
      setIsOffline(false);
      setDismissed(false);
    };

    // Handle offline event
    const handleOffline = () => {
      setIsOffline(true);
      setDismissed(false);
    };

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  // Don't show if online or dismissed
  if (!isOffline || dismissed) {
    return null;
  }

  return (
    <div className="fixed top-0 left-0 right-0 z-50 bg-amber-500/10 border-b border-amber-500/20">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between py-3">
          {/* Message */}
          <p className="font-sans text-[13px] text-amber-200">
            You're offline. Some features may be limited.
          </p>

          {/* Dismiss button */}
          <button
            onClick={() => setDismissed(true)}
            className="flex-shrink-0 ml-4 p-1 rounded hover:bg-amber-500/10 transition-colors cursor-pointer"
            aria-label="Dismiss"
          >
            <X className="w-4 h-4 text-amber-200" strokeWidth={1.5} />
          </button>
        </div>
      </div>
    </div>
  );
}
```

**Step 3: Run tests**

Run: `npm test -- OfflineBanner.test.tsx`
Expected: All tests PASS

**Step 4: Check TypeScript**

Run: `npm run typecheck`
Expected: No type errors

**Step 5: Check ESLint**

Run: `npm run lint -- frontend/src/components/OfflineBanner.tsx`
Expected: No linting errors

**Step 6: Register OfflineBanner in App.tsx**

Edit `frontend/src/App.tsx` - add the banner at the top of the app:

```tsx
// Add import:
import { OfflineBanner } from './components/OfflineBanner';

// In the return statement, add OfflineBanner at the top:
function App() {
  return (
    <ErrorBoundary>
      <OfflineBanner />
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          {/* existing app content */}
        </BrowserRouter>
      </QueryClientProvider>
    </ErrorBoundary>
  );
}
```

**Step 7: Add top padding to body when banner is visible**

To prevent content overlap when the banner shows, add padding to the main content. In your App.tsx or a global styles file:

```tsx
// If you have a main layout component, add conditional padding:
// <main className={isOffline ? 'pt-12' : ''}>
```

**Step 8: Commit**

```bash
git add frontend/src/components/OfflineBanner.tsx frontend/src/components/__tests__/OfflineBanner.test.tsx frontend/src/App.tsx
git commit -m "feat(US-930): add OfflineBanner component

- Monitors navigator.onLine status
- Shows subtle amber banner when offline
- Auto-dismisses when connection restored
- Fixed position at top of screen
- Registered globally in App.tsx

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 7: Enhanced API Client with Retry Logic

**Files:**
- Modify: `frontend/src/api/client.ts`
- Create: `frontend/src/hooks/useApiClient.ts`

**Step 1: Read current API client**

Run: `cat frontend/src/api/client.ts`
Expected: See existing axios configuration

**Step 2: Write test for retry logic**

Create `frontend/src/api/__tests__/client.test.ts`:

```tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';
import { apiClient } from '../client';

// Mock axios
vi.mock('axios');

describe('API Client Retry Logic', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('retries failed requests with exponential backoff', async () => {
    const mockError = {
      response: { status: 500 },
      config: { headers: {} },
    };
    
    // First two calls fail, third succeeds
    vi.mocked(axios).mockRejectedValueOnce(mockError)
      .mockRejectedValueOnce(mockError)
      .mockResolvedValueOnce({ data: { success: true } });
    
    const response = await apiClient.get('/test');
    expect(response.data).toEqual({ success: true });
    expect(axios).toHaveBeenCalledTimes(3);
  });

  it('does not retry 4xx errors (except 429)', async () => {
    const mockError = {
      response: { status: 400 },
      config: { headers: {} },
    };
    
    vi.mocked(axios).mockRejectedValue(mockError);
    
    await expect(apiClient.get('/test')).rejects.toThrow();
    expect(axios).toHaveBeenCalledTimes(1);
  });

  it('retries 429 errors with retry-after delay', async () => {
    const mockError = {
      response: { 
        status: 429,
        headers: { 'retry-after': '2' },
      },
      config: { headers: {} },
    };
    
    vi.mocked(axios).mockRejectedValueOnce(mockError)
      .mockResolvedValueOnce({ data: { success: true } });
    
    const startTime = Date.now();
    const response = await apiClient.get('/test');
    const elapsed = Date.now() - startTime;
    
    expect(response.data).toEqual({ success: true });
    expect(elapsed).toBeGreaterThan(2000); // At least 2 second delay
  });

  it('redirects to login on 401', async () => {
    const mockError = {
      response: { status: 401 },
      config: { headers: {} },
    };
    
    vi.mocked(axios).mockRejectedValue(mockError);
    
    // Mock window.location
    const mockLocation = { href: '' };
    Object.defineProperty(window, 'location', {
      value: mockLocation,
      writable: true,
    });
    
    await apiClient.get('/test');
    
    expect(mockLocation.href).toContain('/login');
  });

  it('shows toast notification on 500 errors', async () => {
    const mockError = {
      response: { status: 500 },
      config: { headers: {} },
    };
    
    vi.mocked(axios).mockRejectedValue(mockError);
    
    // Mock toast
    const toastMock = vi.fn();
    vi.mock('@/components/ui/use-toast', () => ({
      useToast: () => ({ toast: toastMock }),
    }));
    
    await expect(apiClient.get('/test')).rejects.toThrow();
    
    // Should eventually show error toast after retries exhausted
  });
});
```

Run: `npm test -- client.test.ts`
Expected: FAIL - Retry logic not implemented

**Step 3: Enhance API client with retry logic**

Edit `frontend/src/api/client.ts`:

```tsx
import axios, { AxiosError, InternalAxiosRequestConfig, AxiosResponse } from 'axios';
import { useToast } from '@/hooks/use-toast';

// Retry configuration
const MAX_RETRIES = 3;
const BASE_DELAY = 1000; // 1 second
const RETRYABLE_STATUS_CODES = [408, 429, 500, 502, 503, 504];

/**
 * Sleep for specified milliseconds
 */
function sleep(ms: number): Promise<void> {
  return new Promise(resolve => setTimeout(resolve, ms));
}

/**
 * Calculate exponential backoff delay
 */
function getRetryDelay(attemptNumber: number, retryAfter?: string): number {
  // If server provided retry-after, use it
  if (retryAfter) {
    const seconds = parseInt(retryAfter, 10);
    if (!isNaN(seconds)) {
      return seconds * 1000;
    }
  }
  
  // Exponential backoff: 1s, 2s, 4s
  return BASE_DELAY * Math.pow(2, attemptNumber);
}

/**
 * Check if error is retryable
 */
function isRetryableError(error: AxiosError): boolean {
  if (!error.response) {
    // Network errors are retryable
    return true;
  }
  
  return RETRYABLE_STATUS_CODES.includes(error.response.status);
}

// Create axios instance
export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_URL || 'http://localhost:8000',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor - add auth token
apiClient.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem('auth_token');
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error: AxiosError) => Promise.reject(error)
);

// Response interceptor - handle errors and retries
apiClient.interceptors.response.use(
  (response: AxiosResponse) => response,
  async (error: AxiosError) => {
    const { toast } = useToast();
    
    // Get retry count from config
    const config = error.config as any;
    const retryCount = config._retryCount || 0;
    
    // Handle 401 - redirect to login
    if (error.response?.status === 401) {
      // Try token refresh first
      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        try {
          const response = await axios.post(
            `${apiClient.defaults.baseURL}/api/v1/auth/refresh`,
            { refresh_token: refreshToken }
          );
          
          const { access_token } = response.data;
          localStorage.setItem('auth_token', access_token);
          
          // Retry original request with new token
          if (config.headers) {
            config.headers.Authorization = `Bearer ${access_token}`;
          }
          return apiClient(config);
        } catch (refreshError) {
          // Refresh failed, redirect to login
          localStorage.removeItem('auth_token');
          localStorage.removeItem('refresh_token');
          window.location.href = '/login';
          return Promise.reject(refreshError);
        }
      } else {
        window.location.href = '/login';
        return Promise.reject(error);
      }
    }
    
    // Handle 429 - Rate limited
    if (error.response?.status === 429) {
      const retryAfter = error.response.headers?.['retry-after'];
      const delay = getRetryDelay(retryCount, retryAfter);
      
      if (retryCount < MAX_RETRIES) {
        config._retryCount = retryCount + 1;
        
        toast({
          title: 'Please wait',
          description: 'Too many requests. Retrying...',
          variant: 'default',
        });
        
        await sleep(delay);
        return apiClient(config);
      } else {
        toast({
          title: 'Rate limited',
          description: 'Please wait a moment before trying again.',
          variant: 'destructive',
        });
      }
    }
    
    // Handle 500 errors with retry
    if (error.response?.status && error.response.status >= 500) {
      if (isRetryableError(error) && retryCount < MAX_RETRIES) {
        config._retryCount = retryCount + 1;
        const delay = getRetryDelay(retryCount);
        
        await sleep(delay);
        return apiClient(config);
      } else {
        toast({
          title: 'Something went wrong',
          description: 'ARIA encountered an error. Please try again.',
          variant: 'destructive',
        });
      }
    }
    
    // Handle network errors
    if (!error.response && retryCount < MAX_RETRIES) {
      config._retryCount = retryCount + 1;
      const delay = getRetryDelay(retryCount);
      
      toast({
        title: 'Connection issue',
        description: 'ARIA is having trouble connecting. Retrying...',
        variant: 'default',
      });
      
      await sleep(delay);
      return apiClient(config);
    }
    
    return Promise.reject(error);
  }
);

export default apiClient;
```

**Note:** The above toast integration in the interceptor won't work directly because hooks can't be used outside React components. We need a different approach.

**Step 4: Fix toast integration - use event-based approach**

Create `frontend/src/lib/errorEvents.ts`:

```tsx
/**
 * Event-based error notifications for use outside React components
 */

type ErrorEvent = {
  type: 'error' | 'warning' | 'info';
  title: string;
  description?: string;
};

const listeners = Set<(event: ErrorEvent) => void>();

export function showError(type: 'error' | 'warning' | 'info', title: string, description?: string) {
  const event: ErrorEvent = { type, title, description };
  listeners.forEach(listener => listener(event));
}

export function onError(callback: (event: ErrorEvent) => void) {
  listeners.add(callback);
  return () => listeners.delete(callback);
}
```

Then update `frontend/src/api/client.ts`:

```tsx
import { showError } from '@/lib/errorEvents';

// In the interceptor, replace toast() calls with showError():

// For 429:
showError('warning', 'Please wait', 'Too many requests. Retrying...');

// For 500:
showError('error', 'Something went wrong', 'ARIA encountered an error. Please try again.');

// For network:
showError('info', 'Connection issue', 'ARIA is having trouble connecting. Retrying...');
```

And create `frontend/src/components/ErrorToaster.tsx`:

```tsx
/**
 * ErrorToaster - Displays error events from API client
 */

import { useEffect } from 'react';
import { useToast } from '@/hooks/use-toast';
import { onError } from '@/lib/errorEvents';

export function ErrorToaster() {
  const { toast } = useToast();

  useEffect(() => {
    const unsubscribe = onError((event) => {
      toast({
        title: event.title,
        description: event.description,
        variant: event.type === 'error' ? 'destructive' : 'default',
      });
    });

    return unsubscribe;
  }, [toast]);

  return null;
}
```

Register in `frontend/src/App.tsx`:

```tsx
import { ErrorToaster } from './components/ErrorToaster';

// Inside App component, add:
<ErrorToaster />
```

**Step 5: Run tests**

Run: `npm test -- client.test.ts`
Expected: Tests pass with updated implementation

**Step 6: Check TypeScript**

Run: `npm run typecheck`
Expected: No type errors

**Step 7: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/lib/errorEvents.ts frontend/src/components/ErrorToaster.tsx frontend/src/api/__tests__/client.test.ts frontend/src/App.tsx
git commit -m "feat(US-930): add retry logic and error notifications to API client

- Exponential backoff retry (1s, 2s, 4s)
- Retries on 429, 500, 502, 503, 504
- Honors retry-after header
- 401 redirects to login with token refresh
- Event-based error notifications
- ErrorToaster component for displaying toasts

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 8: Create Index Barrel for New Components

**Files:**
- Modify: `frontend/src/components/index.ts`

**Step 1: Add exports for new components**

Edit `frontend/src/components/index.ts`:

```typescript
// Error Handling
export { ErrorBoundary, withErrorBoundary } from './ErrorBoundary';
export { 
  EmptyState, 
  EmptyLeads, 
  EmptyGoals, 
  EmptyBriefings, 
  EmptyBattleCards, 
  EmptyMeetingBriefs, 
  EmptyDrafts,
  EmptyActivity 
} from './EmptyState';
export { 
  SkeletonLoader, 
  LeadsSkeleton, 
  GoalsSkeleton, 
  BriefingSkeleton, 
  LeadsTableSkeleton, 
  ContactsListSkeleton, 
  TextSkeleton 
} from './SkeletonLoader';
export { OfflineBanner } from './OfflineBanner';
export { ErrorToaster } from './ErrorToaster';
```

**Step 2: Verify exports work**

Run: `npm run typecheck`
Expected: No errors - exports are accessible

**Step 3: Commit**

```bash
git add frontend/src/components/index.ts
git commit -m "feat(US-930): export error handling components from barrel file

- Export ErrorBoundary, EmptyState, SkeletonLoader, OfflineBanner
- Export all preset variants
- Export ErrorToaster for API error notifications

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 9: Integration Tests and Quality Gates

**Files:**
- Create: `frontend/tests/integration/error-handling.test.tsx`

**Step 1: Write integration tests**

Create `frontend/tests/integration/error-handling.test.tsx`:

```tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, it, expect, vi } from 'vitest';
import { ErrorBoundary, EmptyState, SkeletonLoader, OfflineBanner } from '@/components';

describe('Error Handling Integration', () => {
  describe('ErrorBoundary catches component errors', () => {
    it('catches errors in child components and shows fallback', () => {
      const ThrowError = () => {
        throw new Error('Test error');
      };

      render(
        <ErrorBoundary>
          <ThrowError />
        </ErrorBoundary>
      );

      expect(screen.getByText('Something went wrong')).toBeInTheDocument();
    });

    it('allows reloading the page', () => {
      const reloadMock = vi.fn();
      Object.defineProperty(window, 'location', {
        value: { reload: reloadMock },
        writable: true,
      });

      const ThrowError = () => {
        throw new Error('Test error');
      };

      render(
        <ErrorBoundary>
          <ThrowError />
        </ErrorBoundary>
      );

      const reloadButton = screen.getByText(/reload/i);
      reloadButton.click();

      expect(reloadMock).toHaveBeenCalled();
    });
  });

  describe('EmptyState displays correctly', () => {
    it('shows all elements when provided', () => {
      const mockAction = vi.fn();

      render(
        <EmptyState
          icon="Users"
          title="No leads"
          description="ARIA can find prospects"
          actionLabel="Set Goal"
          onAction={mockAction}
        />
      );

      expect(screen.getByText('No leads')).toBeInTheDocument();
      expect(screen.getByText(/ARIA can find prospects/)).toBeInTheDocument();
      expect(screen.getByText('Set Goal')).toBeInTheDocument();

      screen.getByText('Set Goal').click();
      expect(mockAction).toHaveBeenCalled();
    });

    it('without action button when onAction not provided', () => {
      render(
        <EmptyState
          icon="Users"
          title="No leads"
          description="ARIA can find prospects"
        />
      );

      expect(screen.queryByText('Set Goal')).not.toBeInTheDocument();
    });
  });

  describe('SkeletonLoader renders correct variants', () => {
    it('renders card variant', () => {
      const { container } = render(
        <SkeletonLoader variant="card" count={3} />
      );

      const skeletons = container.querySelectorAll('[data-testid="skeleton-item"]');
      expect(skeletons).toHaveLength(3);
    });

    it('renders list variant', () => {
      const { container } = render(
        <SkeletonLoader variant="list" count={5} />
      );

      const skeletons = container.querySelectorAll('[data-testid="skeleton-item"]');
      expect(skeletons).toHaveLength(5);
    });

    it('renders table variant', () => {
      const { container } = render(
        <SkeletonLoader variant="table" count={10} />
      );

      const skeletons = container.querySelectorAll('[data-testid="skeleton-item"]');
      expect(skeletons).toHaveLength(10);
    });

    it('renders text variant', () => {
      const { container } = render(
        <SkeletonLoader variant="text" count={4} />
      );

      const bars = container.querySelectorAll('[data-testid="skeleton-bar"]');
      expect(bars).toHaveLength(4);
    });
  });

  describe('OfflineBanner responds to network events', () => {
    it('shows when offline event fires', async () => {
      // Start online
      Object.defineProperty(navigator, 'onLine', {
        get: () => true,
        configurable: true,
      });

      const { rerender } = render(<OfflineBanner />);
      expect(screen.queryByText(/offline/i)).not.toBeInTheDocument();

      // Go offline
      Object.defineProperty(navigator, 'onLine', {
        get: () => false,
        configurable: true,
      });

      window.dispatchEvent(new Event('offline'));
      rerender(<OfflineBanner />);

      expect(screen.getByText(/offline/i)).toBeInTheDocument();
    });

    it('hides when online event fires', async () => {
      // Start offline
      Object.defineProperty(navigator, 'onLine', {
        get: () => false,
        configurable: true,
      });

      const { rerender } = render(<OfflineBanner />);
      expect(screen.getByText(/offline/i)).toBeInTheDocument();

      // Go online
      Object.defineProperty(navigator, 'onLine', {
        get: () => true,
        configurable: true,
      });

      window.dispatchEvent(new Event('online'));
      rerender(<OfflineBanner />);

      await waitFor(() => {
        expect(screen.queryByText(/offline/i)).not.toBeInTheDocument();
      });
    });
  });
});
```

**Step 2: Run integration tests**

Run: `npm test -- error-handling.test.tsx`
Expected: All tests PASS

**Step 3: Run full test suite**

Run: `npm test`
Expected: All tests PASS

**Step 4: Run TypeScript check**

Run: `npm run typecheck`
Expected: No type errors

**Step 5: Run ESLint**

Run: `npm run lint`
Expected: No linting errors

**Step 6: Run frontend build**

Run: `npm run build`
Expected: Build succeeds without errors

**Step 7: Run backend quality gates**

Run: `mypy backend/src/core/rate_limiter.py --strict`
Expected: No type errors

Run: `ruff check backend/src/core/rate_limiter.py`
Expected: No linting errors

Run: `pytest backend/tests/core/test_rate_limiter.py backend/tests/integration/test_rate_limiting.py -v`
Expected: All tests PASS

**Step 8: Commit**

```bash
git add frontend/tests/integration/error-handling.test.tsx
git commit -m "test(US-930): add integration tests for error handling

- ErrorBoundary catches and displays errors
- EmptyState renders with optional actions
- SkeletonLoader renders all variants correctly
- OfflineBanner responds to network events

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Task 10: Documentation and Final Verification

**Files:**
- Create: `backend/src/core/rate_limiter.md`
- Modify: `docs/plans/2026-02-06-us-930-error-handling-edge-cases.md`

**Step 1: Create rate limiter documentation**

Create `backend/src/core/rate_limiter.md`:

```markdown
# Rate Limiter

## Overview

The rate limiter protects API endpoints from abuse using in-memory sliding window tracking.

## Configuration

Rate limits are configured per endpoint:

| Endpoint Pattern | Requests | Window |
|-----------------|----------|--------|
| `/auth/login` | 5 | 60 seconds |
| `/auth/register` | 5 | 60 seconds |
| `/auth/password/reset` | 3 | 60 seconds |
| `/api/v1/emails` | 10 | 60 seconds |
| `/api/v1/crm` | 20 | 60 seconds |
| Default | 100 | 60 seconds |

## Usage

```python
from src.core.rate_limiter import rate_limit

@router.get("/api/endpoint")
@rate_limit("endpoint_key", requests=10, window=60)
async def my_endpoint():
    return {"status": "ok"}
```

## Response

When rate limited, clients receive:

```json
{
  "error": {
    "code": "RATE_LIMIT_EXCEEDED",
    "message": "Rate limit exceeded. Please try again in X seconds.",
    "details": {
      "retry_after": 42
    }
  }
}
```

With HTTP header: `retry-after: 42`

## Production Considerations

For multi-worker deployments, replace in-memory storage with Redis:

```python
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="redis://localhost:6379"
)
```
```

**Step 2: Update frontend component documentation**

Create `frontend/src/components/ERROR_HANDLING.md`:

```markdown
# Error Handling Components

## Components

### ErrorBoundary

Catches unhandled React errors and displays a professional fallback UI.

```tsx
import { ErrorBoundary } from '@/components';

<ErrorBoundary>
  <YourComponent />
</ErrorBoundary>
```

### EmptyState

Reusable empty state with ARIA personality.

```tsx
import { EmptyState } from '@/components';

<EmptyState
  icon="Users"
  title="No leads yet"
  description="ARIA can start finding prospects the moment you set a goal."
  actionLabel="Set a Goal"
  onAction={() => navigate('/goals')}
/>
```

Preset variants: `EmptyLeads`, `EmptyGoals`, `EmptyBriefings`, `EmptyBattleCards`, `EmptyMeetingBriefs`, `EmptyDrafts`, `EmptyActivity`.

### SkeletonLoader

Loading skeletons that match content structure.

```tsx
import { SkeletonLoader } from '@/components';

<SkeletonLoader variant="card" count={5} />
```

Variants: `card`, `list`, `table`, `text`.

Preset variants: `LeadsSkeleton`, `GoalsSkeleton`, `BriefingSkeleton`, `LeadsTableSkeleton`, `ContactsListSkeleton`, `TextSkeleton`.

### OfflineBanner

Auto-shows when network connection is lost. Registered globally in App.tsx.

### ErrorToaster

Displays API error notifications. Registered globally in App.tsx.

## Design System Compliance

All components follow ARIA Design System v1.0:
- **Fonts**: Instrument Serif (headings), Satoshi (body), JetBrains Mono (data)
- **Icons**: Lucide React, 20x20, stroke 1.5
- **Colors**: Dark surface palette (#0F1117, #161B2E, #2A2F42)
- **Spacing**: 4px multiples
- **Accessibility**: WCAG AA, keyboard nav, ARIA labels
```

**Step 3: Create final verification checklist**

Create a verification script or document listing all acceptance criteria:

```markdown
# US-930 Verification Checklist

## Backend
- [x] Standardized exceptions (ARIAException hierarchy)
- [x] Rate limiter middleware with in-memory storage
- [x] Per-endpoint rate limit configuration
- [x] Global exception handler returns JSON format
- [x] Tests for rate limiting behavior
- [x] mypy strict mode passes
- [x] ruff linting passes

## Frontend
- [x] ErrorBoundary component catches errors
- [x] EmptyState component with presets
- [x] SkeletonLoader component with variants
- [x] OfflineBanner monitors network status
- [x] API client with retry logic
- [x] ErrorToaster for notifications
- [x] All components registered in App.tsx
- [x] TypeScript compilation passes
- [x] ESLint passes
- [x] All tests pass

## Integration
- [x] ErrorBoundary wraps entire app
- [x] OfflineBanner visible at top
- [x] ErrorToaster registered globally
- [x] API client handles 401, 429, 500
- [x] Integration tests pass

## Design System
- [x] Dark surface colors used
- [x] Instrument Serif for headings
- [x] Satoshi for body text
- [x] Lucide React icons (20x20, stroke 1.5)
- [x] No emojis as icons
- [x] Proper spacing (4px multiples)
- [x] Accessible (WCAG AA, keyboard nav, labels)
```

**Step 4: Run final quality gates**

```bash
# Backend
cd backend
mypy src/ --strict
ruff check src/
pytest tests/ -v

# Frontend
cd ../frontend
npm run typecheck
npm run lint
npm run test
npm run build
```

**Step 5: Commit documentation**

```bash
git add backend/src/core/rate_limiter.md frontend/src/components/ERROR_HANDLING.md
git commit -m "docs(US-930): add error handling documentation

- Rate limiter configuration and usage
- Error handling component documentation
- Design system compliance notes
- Verification checklist

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>"
```

---

## Summary

This plan implements US-930: Error Handling & Edge Cases across the full stack:

**Backend (Tasks 1-2):**
- Rate limiter middleware with in-memory sliding window
- Per-endpoint configuration (auth strict, others moderate)
- Standardized error JSON format
- Integration with existing exception hierarchy

**Frontend (Tasks 3-8):**
- ErrorBoundary for catching React errors
- EmptyState with ARIA personality (optimistic messages)
- SkeletonLoader for all major content types
- OfflineBanner for network status
- Enhanced API client with exponential backoff retry
- ErrorToaster for notifications

**Quality (Tasks 9-10):**
- Integration tests
- Type checking (mypy strict, TypeScript strict)
- Linting (ruff, ESLint)
- Design system compliance verification

All components follow ARIA Design System v1.0 with dark surfaces, proper typography, and Lucide icons.
