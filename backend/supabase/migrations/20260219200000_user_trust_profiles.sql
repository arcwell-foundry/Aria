-- User Trust Profiles for Trust Calibration (Wave 2)
-- One row per user per action_category. Tracks trust score,
-- success/failure counts, and override history.

CREATE TABLE IF NOT EXISTS user_trust_profiles (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    action_category     TEXT NOT NULL,
    trust_score         DOUBLE PRECISION NOT NULL DEFAULT 0.3
                        CHECK (trust_score >= 0.0 AND trust_score <= 1.0),
    successful_actions  INTEGER NOT NULL DEFAULT 0,
    failed_actions      INTEGER NOT NULL DEFAULT 0,
    override_count      INTEGER NOT NULL DEFAULT 0,
    last_failure_at     TIMESTAMPTZ,
    last_override_at    TIMESTAMPTZ,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, action_category)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_user_trust_profiles_user_id
    ON user_trust_profiles (user_id);
CREATE INDEX IF NOT EXISTS idx_user_trust_profiles_user_category
    ON user_trust_profiles (user_id, action_category);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_user_trust_profiles_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_user_trust_profiles_updated_at
    BEFORE UPDATE ON user_trust_profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_user_trust_profiles_updated_at();

-- Atomic upsert RPC
-- Caller computes the new trust_score in Python and sends the final value.
-- SECURITY DEFINER bypasses RLS for the upsert but only touches the
-- row matching p_user_id + p_action_category, so it's safe.
CREATE OR REPLACE FUNCTION update_trust_score(
    p_user_id           UUID,
    p_action_category   TEXT,
    p_new_score         DOUBLE PRECISION,
    p_success_delta     INTEGER DEFAULT 0,
    p_failure_delta     INTEGER DEFAULT 0,
    p_override_delta    INTEGER DEFAULT 0,
    p_set_last_failure  BOOLEAN DEFAULT FALSE,
    p_set_last_override BOOLEAN DEFAULT FALSE
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    INSERT INTO user_trust_profiles (
        user_id, action_category, trust_score,
        successful_actions, failed_actions, override_count,
        last_failure_at, last_override_at
    ) VALUES (
        p_user_id, p_action_category, p_new_score,
        p_success_delta, p_failure_delta, p_override_delta,
        CASE WHEN p_set_last_failure THEN now() ELSE NULL END,
        CASE WHEN p_set_last_override THEN now() ELSE NULL END
    )
    ON CONFLICT (user_id, action_category) DO UPDATE SET
        trust_score        = p_new_score,
        successful_actions = user_trust_profiles.successful_actions + p_success_delta,
        failed_actions     = user_trust_profiles.failed_actions     + p_failure_delta,
        override_count     = user_trust_profiles.override_count     + p_override_delta,
        last_failure_at    = CASE WHEN p_set_last_failure THEN now()
                             ELSE user_trust_profiles.last_failure_at END,
        last_override_at   = CASE WHEN p_set_last_override THEN now()
                             ELSE user_trust_profiles.last_override_at END;
END;
$$;

-- RLS
ALTER TABLE user_trust_profiles ENABLE ROW LEVEL SECURITY;

-- Users can read their own rows
CREATE POLICY user_trust_profiles_select_own ON user_trust_profiles
    FOR SELECT USING (user_id = auth.uid());

-- Service role has full access (for the RPC and admin queries)
CREATE POLICY user_trust_profiles_service_all ON user_trust_profiles
    FOR ALL USING (auth.role() = 'service_role');
