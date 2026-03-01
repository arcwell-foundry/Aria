-- Proactive Intelligence Pipeline tables
-- briefing_queue: LOW-priority insights queued for next morning briefing
-- login_message_queue: HIGH-priority messages for offline users
-- weekly_digests: weekly LLM-synthesized summary storage

-- =========================================================================
-- briefing_queue
-- =========================================================================
CREATE TABLE IF NOT EXISTS briefing_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    category TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    consumed BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_briefing_queue_user_consumed
    ON briefing_queue (user_id, consumed)
    WHERE consumed = FALSE;

ALTER TABLE briefing_queue ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users read own briefing queue"
    ON briefing_queue FOR SELECT
    USING (auth.uid() = user_id);

-- Service role can insert/update
CREATE POLICY "Service role manages briefing queue"
    ON briefing_queue FOR ALL
    USING (auth.role() = 'service_role');

-- =========================================================================
-- login_message_queue
-- =========================================================================
CREATE TABLE IF NOT EXISTS login_message_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    category TEXT NOT NULL,
    metadata JSONB NOT NULL DEFAULT '{}',
    delivered BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_login_message_queue_user_delivered
    ON login_message_queue (user_id, delivered)
    WHERE delivered = FALSE;

ALTER TABLE login_message_queue ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users read own login messages"
    ON login_message_queue FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Service role manages login messages"
    ON login_message_queue FOR ALL
    USING (auth.role() = 'service_role');

-- =========================================================================
-- weekly_digests
-- =========================================================================
CREATE TABLE IF NOT EXISTS weekly_digests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    week_start DATE NOT NULL,
    content JSONB NOT NULL DEFAULT '{}',
    executive_summary TEXT,
    wins JSONB NOT NULL DEFAULT '[]',
    risks JSONB NOT NULL DEFAULT '[]',
    stats JSONB NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, week_start)
);

CREATE INDEX IF NOT EXISTS idx_weekly_digests_user
    ON weekly_digests (user_id, week_start DESC);

ALTER TABLE weekly_digests ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users read own weekly digests"
    ON weekly_digests FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Service role manages weekly digests"
    ON weekly_digests FOR ALL
    USING (auth.role() = 'service_role');
