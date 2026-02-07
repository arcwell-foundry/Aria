-- US-925: Ambient Gap Filling prompt tracking
-- Stores pending and historical ambient prompts for continuous onboarding

CREATE TABLE IF NOT EXISTS ambient_prompts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    domain TEXT NOT NULL,         -- readiness domain: corporate_memory, digital_twin, etc.
    prompt TEXT NOT NULL,         -- natural language prompt text
    score FLOAT NOT NULL,        -- readiness score at time of generation
    status TEXT NOT NULL DEFAULT 'pending',  -- pending, delivered, engaged, dismissed, deferred
    metadata JSONB DEFAULT '{}', -- additional context (gap details, generation params)
    created_at TIMESTAMPTZ DEFAULT now(),
    delivered_at TIMESTAMPTZ,    -- when shown to user in conversation
    resolved_at TIMESTAMPTZ      -- when user engaged/dismissed/deferred
);

-- Index for fast lookup of pending prompts per user
CREATE INDEX idx_ambient_prompts_user_pending
    ON ambient_prompts(user_id, status) WHERE status = 'pending';

-- Index for weekly count queries
CREATE INDEX idx_ambient_prompts_user_created
    ON ambient_prompts(user_id, created_at DESC);

-- RLS
ALTER TABLE ambient_prompts ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own_ambient_prompts" ON ambient_prompts
    FOR ALL TO authenticated USING (user_id = auth.uid());
