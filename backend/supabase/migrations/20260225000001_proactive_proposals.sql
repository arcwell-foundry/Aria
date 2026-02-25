-- Proactive goal proposals: stores ARIA-generated goal proposals
-- triggered by market signals or OODA implication chains.
--
-- Status lifecycle: proposed → approved | dismissed | expired

CREATE TABLE IF NOT EXISTS proactive_proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    source_signal_id UUID,
    source_goal_id UUID,
    goal_title TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'proposed'
        CHECK (status IN ('proposed', 'approved', 'dismissed', 'expired')),
    proposal_data JSONB NOT NULL DEFAULT '{}',
    goal_id UUID,  -- set when proposal is approved and a goal is created
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Fast lookup for dedup: already proposed for this signal?
CREATE INDEX IF NOT EXISTS idx_proactive_proposals_user_signal
    ON proactive_proposals (user_id, source_signal_id)
    WHERE source_signal_id IS NOT NULL;

-- Frequency control: count today's proposals per user
CREATE INDEX IF NOT EXISTS idx_proactive_proposals_user_date
    ON proactive_proposals (user_id, created_at DESC);

-- Pending proposals for a user (for login delivery)
CREATE INDEX IF NOT EXISTS idx_proactive_proposals_user_status
    ON proactive_proposals (user_id, status)
    WHERE status = 'proposed';

ALTER TABLE proactive_proposals ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users read own proposals"
    ON proactive_proposals FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Service role manages proposals"
    ON proactive_proposals FOR ALL
    USING (auth.role() = 'service_role');
