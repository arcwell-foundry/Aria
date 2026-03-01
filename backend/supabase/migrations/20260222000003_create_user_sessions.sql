-- Migration: Create user_sessions table for cross-modal session persistence
-- Required by: SessionManager.ts, frontend session management
-- Part of: ARIA Memory Persistence Architecture (IDD v3 Section 4)

-- =============================================================================
-- User Sessions Table
-- =============================================================================

CREATE TABLE IF NOT EXISTS user_sessions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    session_data JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active BOOLEAN NOT NULL DEFAULT true,
    day_date DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Ensure only one active session per user per day
    CONSTRAINT unique_active_session_per_day UNIQUE (user_id, day_date, is_active)
    DEFERRABLE INITIALLY DEFERRED
);

-- =============================================================================
-- Indexes
-- =============================================================================

-- Fast lookup for active session by user
CREATE INDEX IF NOT EXISTS idx_user_sessions_user_active
    ON user_sessions(user_id, is_active)
    WHERE is_active = true;

-- Fast lookup for today's session
CREATE INDEX IF NOT EXISTS idx_user_sessions_today
    ON user_sessions(user_id, day_date)
    WHERE is_active = true;

-- Cleanup queries for old sessions
CREATE INDEX IF NOT EXISTS idx_user_sessions_created
    ON user_sessions(created_at);

-- =============================================================================
-- Row Level Security
-- =============================================================================

ALTER TABLE user_sessions ENABLE ROW LEVEL SECURITY;

-- Users can only access their own sessions
CREATE POLICY "Users can view own sessions" ON user_sessions
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own sessions" ON user_sessions
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own sessions" ON user_sessions
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own sessions" ON user_sessions
    FOR DELETE USING (auth.uid() = user_id);

-- Service role has full access (for backend operations)
CREATE POLICY "Service role full access to user_sessions" ON user_sessions
    FOR ALL USING (auth.role() = 'service_role');

-- =============================================================================
-- Triggers
-- =============================================================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE TRIGGER update_user_sessions_updated_at
    BEFORE UPDATE ON user_sessions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- =============================================================================
-- Functions
-- =============================================================================

-- Helper function to get or create today's session for a user
CREATE OR REPLACE FUNCTION get_or_create_user_session(p_user_id UUID)
RETURNS UUID
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_session_id UUID;
BEGIN
    -- Try to get today's active session
    SELECT id INTO v_session_id
    FROM user_sessions
    WHERE user_id = p_user_id
      AND day_date = CURRENT_DATE
      AND is_active = true
    LIMIT 1;

    -- If not found, create a new session
    IF v_session_id IS NULL THEN
        -- Archive any previous active sessions for this user
        UPDATE user_sessions
        SET is_active = false
        WHERE user_id = p_user_id
          AND is_active = true
          AND day_date < CURRENT_DATE;

        -- Create new session
        INSERT INTO user_sessions (user_id, session_data, is_active, day_date)
        VALUES (
            p_user_id,
            jsonb_build_object(
                'current_route', '/',
                'active_modality', 'text',
                'conversation_thread', '[]'::jsonb,
                'metadata', '{}'::jsonb
            ),
            true,
            CURRENT_DATE
        )
        RETURNING id INTO v_session_id;
    END IF;

    RETURN v_session_id;
END;
$$;

-- =============================================================================
-- Comments
-- =============================================================================

COMMENT ON TABLE user_sessions IS 'Cross-modal session persistence for ARIA. Each user has at most one active session per day.';
COMMENT ON COLUMN user_sessions.session_data IS 'Full UnifiedSession object stored as JSONB';
COMMENT ON COLUMN user_sessions.day_date IS 'Date for new-day detection - sessions reset on new day';
COMMENT ON COLUMN user_sessions.is_active IS 'Whether this session is currently active';
