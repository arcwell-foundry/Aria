-- Intelligence Pulse Engine tables
-- pulse_signals: stores every detected signal with salience scores and delivery routing
-- user_pulse_config: per-user thresholds and delivery preferences

CREATE TABLE IF NOT EXISTS pulse_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,

    -- Signal classification
    pulse_type TEXT NOT NULL CHECK (pulse_type IN ('scheduled', 'event', 'intelligent')),
    source TEXT NOT NULL,
    signal_category TEXT,

    -- Content
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    entities TEXT[],
    related_goal_id UUID REFERENCES goals(id) ON DELETE SET NULL,
    related_lead_id UUID,
    raw_data JSONB,

    -- Salience scores (0.0 to 1.0)
    goal_relevance FLOAT DEFAULT 0 CHECK (goal_relevance >= 0 AND goal_relevance <= 1),
    time_sensitivity FLOAT DEFAULT 0 CHECK (time_sensitivity >= 0 AND time_sensitivity <= 1),
    value_impact FLOAT DEFAULT 0 CHECK (value_impact >= 0 AND value_impact <= 1),
    user_preference FLOAT DEFAULT 0.5 CHECK (user_preference >= 0 AND user_preference <= 1),
    surprise_factor FLOAT DEFAULT 0 CHECK (surprise_factor >= 0 AND surprise_factor <= 1),

    -- Computed priority (0-100)
    priority_score FLOAT DEFAULT 0,

    -- Delivery routing
    delivery_channel TEXT CHECK (delivery_channel IN ('immediate', 'check_in', 'morning_brief', 'weekly_digest', 'silent')),
    delivered_at TIMESTAMPTZ,
    read_at TIMESTAMPTZ,
    dismissed_at TIMESTAMPTZ,

    -- Timestamps
    detected_at TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pulse_signals_user_undelivered
    ON pulse_signals(user_id, delivery_channel) WHERE delivered_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_pulse_signals_user_priority
    ON pulse_signals(user_id, priority_score DESC);
CREATE INDEX IF NOT EXISTS idx_pulse_signals_source
    ON pulse_signals(source, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pulse_signals_category
    ON pulse_signals(user_id, signal_category);

ALTER TABLE pulse_signals ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see own pulse signals" ON pulse_signals
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on pulse_signals" ON pulse_signals
    FOR ALL TO service_role USING (true);

CREATE TABLE IF NOT EXISTS user_pulse_config (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL UNIQUE,
    morning_brief_enabled BOOLEAN DEFAULT TRUE,
    morning_brief_time TIME DEFAULT '07:00',
    immediate_threshold INT DEFAULT 90,
    check_in_threshold INT DEFAULT 70,
    morning_brief_threshold INT DEFAULT 50,
    push_notifications_enabled BOOLEAN DEFAULT TRUE,
    email_digest_enabled BOOLEAN DEFAULT FALSE,
    weekend_briefings TEXT DEFAULT 'abbreviated' CHECK (weekend_briefings IN ('full', 'abbreviated', 'none')),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE user_pulse_config ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users see own pulse config" ON user_pulse_config
    FOR ALL USING (auth.uid() = user_id);
CREATE POLICY "Service role full access on user_pulse_config" ON user_pulse_config
    FOR ALL TO service_role USING (true);
