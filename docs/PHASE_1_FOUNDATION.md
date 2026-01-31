# Phase 1: Foundation & Authentication
## ARIA PRD - Implementation Phase 1

**Prerequisites:** None  
**Estimated Stories:** 12  
**Focus:** Project setup, authentication, basic API structure, database schema

---

## Overview

Phase 1 establishes the foundational architecture for ARIA. This includes:
- Project scaffolding (backend + frontend)
- Supabase integration and auth
- Multi-tenant user management
- Basic API structure
- Core database tables

**Completion Criteria:** User can sign up, log in, and access a basic dashboard with JWT authentication working correctly.

---

## User Stories

### US-101: Backend Project Setup

**As a** developer  
**I want** a properly structured FastAPI backend  
**So that** I have a solid foundation for ARIA's API

#### Acceptance Criteria
- [ ] FastAPI project initialized with Python 3.11+
- [ ] Project structure matches `/backend/src/` layout from PRD
- [ ] `requirements.txt` includes: fastapi, uvicorn, pydantic, python-dotenv, httpx, anthropic
- [ ] `.env.example` file with all required environment variables
- [ ] `src/main.py` runs without errors on `uvicorn src.main:app --reload`
- [ ] Health check endpoint `GET /health` returns `{"status": "healthy"}`
- [ ] CORS configured for localhost:3000 and production domain

#### Technical Notes
```python
# src/main.py structure
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="ARIA API", version="1.0.0")

# CORS middleware
# Router includes
# Health endpoint
```

---

### US-102: Frontend Project Setup

**As a** developer  
**I want** a properly structured React frontend  
**So that** I have a solid foundation for ARIA's UI

#### Acceptance Criteria
- [ ] React 18 project created with Vite and TypeScript
- [ ] Tailwind CSS configured and working
- [ ] Project structure matches `/frontend/src/` layout from PRD
- [ ] `npm run dev` starts development server on port 3000
- [ ] `npm run build` completes without errors
- [ ] `npm run typecheck` passes with strict mode
- [ ] Basic App.tsx renders "ARIA" heading

#### Technical Notes
```bash
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install tailwindcss postcss autoprefixer
npm install @tanstack/react-query axios react-router-dom
```

---

### US-103: Supabase Project Configuration

**As a** developer  
**I want** Supabase configured with proper schema  
**So that** I have a production-ready database

#### Acceptance Criteria
- [ ] Supabase project created
- [ ] Environment variables configured in backend `.env`
- [ ] pgvector extension enabled: `CREATE EXTENSION IF NOT EXISTS vector;`
- [ ] Row Level Security (RLS) enabled on all tables
- [ ] `companies` table created with RLS policy
- [ ] `users` table extends auth.users with additional fields
- [ ] `user_settings` table created
- [ ] Backend can connect and query Supabase

#### SQL Schema
```sql
-- Companies table
CREATE TABLE companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    domain TEXT UNIQUE,
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Extended user profile
CREATE TABLE user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    company_id UUID REFERENCES companies(id),
    full_name TEXT,
    role TEXT DEFAULT 'user',
    avatar_url TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- User settings
CREATE TABLE user_settings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE UNIQUE,
    preferences JSONB DEFAULT '{}',
    integrations JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- RLS Policies
ALTER TABLE companies ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_settings ENABLE ROW LEVEL SECURITY;

-- Users can read their own company
CREATE POLICY "Users can view own company" ON companies
    FOR SELECT USING (id IN (
        SELECT company_id FROM user_profiles WHERE id = auth.uid()
    ));

-- Users can read/update own profile
CREATE POLICY "Users can view own profile" ON user_profiles
    FOR SELECT USING (id = auth.uid());

CREATE POLICY "Users can update own profile" ON user_profiles
    FOR UPDATE USING (id = auth.uid());

-- Users can read/update own settings
CREATE POLICY "Users can view own settings" ON user_settings
    FOR SELECT USING (user_id = auth.uid());

CREATE POLICY "Users can update own settings" ON user_settings
    FOR UPDATE USING (user_id = auth.uid());
```

---

### US-104: Supabase Client Integration

**As a** developer  
**I want** a reusable Supabase client module  
**So that** all backend code uses consistent database access

#### Acceptance Criteria
- [ ] `src/db/supabase.py` created with async client
- [ ] Client uses service role key for backend operations
- [ ] Connection pooling configured
- [ ] Helper functions for common operations (get_user, get_company)
- [ ] Error handling with custom exceptions
- [ ] Unit tests pass for client initialization

#### Technical Notes
```python
# src/db/supabase.py
from supabase import create_client, Client
from src.core.config import settings

class SupabaseClient:
    _client: Client | None = None
    
    @classmethod
    def get_client(cls) -> Client:
        if cls._client is None:
            cls._client = create_client(
                settings.SUPABASE_URL,
                settings.SUPABASE_SERVICE_ROLE_KEY
            )
        return cls._client
    
    @classmethod
    async def get_user_by_id(cls, user_id: str) -> dict | None:
        # Implementation
        pass
```

---

### US-105: Configuration Management

**As a** developer  
**I want** centralized configuration management  
**So that** all settings are validated and accessible

#### Acceptance Criteria
- [ ] `src/core/config.py` uses Pydantic Settings
- [ ] All environment variables from PRD are defined
- [ ] Validation ensures required vars are present
- [ ] Settings singleton pattern implemented
- [ ] Different configs for dev/staging/prod via APP_ENV
- [ ] Sensitive values not logged

#### Technical Notes
```python
# src/core/config.py
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # Supabase
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    SUPABASE_SERVICE_ROLE_KEY: str
    
    # Anthropic
    ANTHROPIC_API_KEY: str
    
    # Neo4j
    NEO4J_URI: str
    NEO4J_USER: str
    NEO4J_PASSWORD: str
    
    # App
    APP_SECRET_KEY: str
    APP_ENV: str = "development"
    
    class Config:
        env_file = ".env"

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
```

---

### US-106: JWT Authentication Middleware

**As a** user  
**I want** secure JWT-based authentication  
**So that** my data is protected

#### Acceptance Criteria
- [ ] `src/api/deps.py` contains auth dependency
- [ ] JWT tokens validated against Supabase
- [ ] `get_current_user` dependency extracts user from token
- [ ] 401 returned for invalid/expired tokens
- [ ] 403 returned for insufficient permissions
- [ ] User ID available in all protected routes
- [ ] Unit tests for auth middleware

#### Technical Notes
```python
# src/api/deps.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from src.db.supabase import SupabaseClient

security = HTTPBearer()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> dict:
    token = credentials.credentials
    client = SupabaseClient.get_client()
    
    try:
        user = client.auth.get_user(token)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication token"
            )
        return user.user
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )
```

---

### US-107: Auth API Routes

**As a** user  
**I want** authentication endpoints  
**So that** I can sign up, log in, and manage my session

#### Acceptance Criteria
- [ ] `POST /api/v1/auth/signup` - Create new account
- [ ] `POST /api/v1/auth/login` - Login with email/password
- [ ] `POST /api/v1/auth/logout` - Invalidate session
- [ ] `POST /api/v1/auth/refresh` - Refresh access token
- [ ] `GET /api/v1/auth/me` - Get current user profile
- [ ] Input validation with Pydantic models
- [ ] Proper error messages for all failure cases
- [ ] Integration tests for all endpoints

#### Technical Notes
```python
# src/api/routes/auth.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

router = APIRouter(prefix="/auth", tags=["auth"])

class SignupRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    company_name: str | None = None

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

@router.post("/signup", response_model=TokenResponse)
async def signup(request: SignupRequest):
    # Implementation
    pass

@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    # Implementation
    pass
```

---

### US-108: Frontend Auth Context

**As a** frontend developer  
**I want** React auth context and hooks  
**So that** auth state is managed consistently

#### Acceptance Criteria
- [ ] `AuthContext` provides user state globally
- [ ] `useAuth` hook for accessing auth state
- [ ] `login()`, `logout()`, `signup()` functions available
- [ ] JWT stored securely (httpOnly cookie preferred, else localStorage)
- [ ] Auto-refresh of tokens before expiry
- [ ] Protected route wrapper component
- [ ] Loading state while checking auth

#### Technical Notes
```typescript
// src/contexts/AuthContext.tsx
interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  signup: (data: SignupData) => Promise<void>;
}

// src/hooks/useAuth.ts
export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};
```

---

### US-109: Login Page

**As a** user  
**I want** a login page  
**So that** I can access my ARIA account

#### Acceptance Criteria
- [ ] `/login` route renders login form
- [ ] Email and password fields with validation
- [ ] "Forgot password" link (can be placeholder)
- [ ] "Sign up" link to registration page
- [ ] Error messages displayed for failed login
- [ ] Loading state during submission
- [ ] Redirect to dashboard on success
- [ ] Responsive design (mobile + desktop)

---

### US-110: Signup Page

**As a** new user  
**I want** a signup page  
**So that** I can create an ARIA account

#### Acceptance Criteria
- [ ] `/signup` route renders registration form
- [ ] Fields: email, password, confirm password, full name, company name
- [ ] Client-side validation (email format, password strength)
- [ ] Password requirements: 8+ chars, 1 uppercase, 1 number
- [ ] Error messages for validation failures
- [ ] Loading state during submission
- [ ] Redirect to dashboard on success
- [ ] Link to login page for existing users

---

### US-111: Basic Dashboard Layout

**As a** logged-in user  
**I want** a dashboard layout  
**So that** I have a home base for ARIA

#### Acceptance Criteria
- [ ] `/dashboard` route protected (requires auth)
- [ ] Sidebar navigation with placeholder links
- [ ] Header with user avatar and logout button
- [ ] Main content area with "Welcome to ARIA" message
- [ ] User's name displayed in header
- [ ] Responsive: sidebar collapses on mobile
- [ ] Logout button works correctly

#### Sidebar Links (Placeholders)
- Dashboard (active)
- ARIA Chat
- Goals
- Lead Memory
- Daily Briefing
- Settings

---

### US-112: API Error Handling

**As a** developer  
**I want** consistent API error handling  
**So that** errors are informative and secure

#### Acceptance Criteria
- [ ] Custom exception classes in `src/core/exceptions.py`
- [ ] Global exception handler in FastAPI
- [ ] Consistent error response format: `{"detail": str, "code": str}`
- [ ] 400 for validation errors
- [ ] 401 for auth errors
- [ ] 403 for permission errors
- [ ] 404 for not found
- [ ] 500 for server errors (without exposing internals)
- [ ] Request ID included in error responses
- [ ] Errors logged with context

#### Technical Notes
```python
# src/core/exceptions.py
class ARIAException(Exception):
    def __init__(self, message: str, code: str, status_code: int = 400):
        self.message = message
        self.code = code
        self.status_code = status_code

class NotFoundError(ARIAException):
    def __init__(self, resource: str):
        super().__init__(
            message=f"{resource} not found",
            code="NOT_FOUND",
            status_code=404
        )

# In main.py
@app.exception_handler(ARIAException)
async def aria_exception_handler(request: Request, exc: ARIAException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message, "code": exc.code}
    )
```

---

## Phase 1 Completion Checklist

Before moving to Phase 2, verify:

- [ ] All 12 user stories completed
- [ ] `pytest tests/` passes with 100% of tests
- [ ] `mypy src/ --strict` has no errors
- [ ] `ruff check src/` has no warnings
- [ ] User can sign up with email/password
- [ ] User can log in and see dashboard
- [ ] JWT authentication working correctly
- [ ] Database tables created with RLS
- [ ] Frontend build completes without errors

---

## Next Phase

Proceed to `PHASE_2_MEMORY.md` for Memory Architecture implementation.
