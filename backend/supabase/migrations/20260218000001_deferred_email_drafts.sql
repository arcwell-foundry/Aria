-- Deferred email drafts table for deduplication system
-- Stores threads that were deferred due to active conversations or other reasons
-- Background job retries these drafts after the deferral period

CREATE TABLE IF NOT EXISTS deferred_email_drafts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    thread_id TEXT NOT NULL,
    latest_email_id TEXT NOT NULL,
    subject TEXT,
    sender_email TEXT,
    deferred_until TIMESTAMPTZ NOT NULL,
    reason TEXT NOT NULL CHECK (reason IN ('active_conversation', 'existing_draft', 'other')),
    retry_count INT DEFAULT 0,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'processed', 'expired', 'cancelled')),
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

COMMENT ON TABLE deferred_email_drafts IS 'Queue of email threads deferred from draft generation. Enables deduplication and active conversation detection.';

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_deferred_drafts_user_thread ON deferred_email_drafts(user_id, thread_id);
CREATE INDEX IF NOT EXISTS idx_deferred_drafts_pending ON deferred_email_drafts(status, deferred_until) WHERE status = 'pending';
CREATE INDEX IF NOT EXISTS idx_deferred_drafts_user_status ON deferred_email_drafts(user_id, status);

-- Enable Row Level Security
ALTER TABLE deferred_email_drafts ENABLE ROW LEVEL SECURITY;

-- RLS Policies for user isolation
CREATE POLICY "Users can view their own deferred drafts" ON deferred_email_drafts
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own deferred drafts" ON deferred_email_drafts
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Service role bypass for backend operations
CREATE POLICY "Service role full access to deferred_email_drafts" ON deferred_email_drafts
    FOR ALL USING (
        current_setting('request.jwt.claims', true)::json->>'role' = 'service_role'
    );

-- Trigger to auto-update updated_at
CREATE OR REPLACE FUNCTION update_deferred_drafts_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_deferred_drafts_updated_at
    BEFORE UPDATE ON deferred_email_drafts
    FOR EACH ROW
    EXECUTE FUNCTION update_deferred_drafts_updated_at();
