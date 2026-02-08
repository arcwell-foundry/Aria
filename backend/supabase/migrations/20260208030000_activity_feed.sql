-- US-940: ARIA Activity Feed / Command Center
CREATE TABLE IF NOT EXISTS aria_activity (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id),
    agent TEXT,
    activity_type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT DEFAULT '',
    reasoning TEXT DEFAULT '',
    confidence FLOAT DEFAULT 0.5,
    related_entity_type TEXT,
    related_entity_id UUID,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_activity_user_created
    ON aria_activity(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_activity_user_type
    ON aria_activity(user_id, activity_type);

CREATE INDEX IF NOT EXISTS idx_activity_user_agent
    ON aria_activity(user_id, agent);

ALTER TABLE aria_activity ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "users_own_activity" ON aria_activity;
CREATE POLICY "users_own_activity" ON aria_activity
    FOR ALL TO authenticated USING (user_id = auth.uid());
