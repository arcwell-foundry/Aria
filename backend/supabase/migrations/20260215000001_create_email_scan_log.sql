-- Email scan log table for inbox analyzer transparency
-- Stores every categorization decision made by EmailAnalyzer
-- Enables "why didn't ARIA draft?" feature and audit trail

CREATE TABLE IF NOT EXISTS email_scan_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    email_id TEXT NOT NULL,
    thread_id TEXT,
    sender_email TEXT NOT NULL,
    subject TEXT,
    category TEXT NOT NULL CHECK (category IN ('NEEDS_REPLY', 'FYI', 'SKIP')),
    urgency TEXT NOT NULL CHECK (urgency IN ('URGENT', 'NORMAL', 'LOW')),
    needs_draft BOOLEAN DEFAULT FALSE,
    reason TEXT,
    scanned_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

COMMENT ON TABLE email_scan_log IS 'Audit log of every email categorization decision by ARIA EmailAnalyzer. Enables transparency and the why-didnt-ARIA-draft feature.';

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_email_scan_log_user_id ON email_scan_log(user_id);
CREATE INDEX IF NOT EXISTS idx_email_scan_log_scanned_at ON email_scan_log(scanned_at DESC);
CREATE INDEX IF NOT EXISTS idx_email_scan_log_user_category ON email_scan_log(user_id, category);
CREATE INDEX IF NOT EXISTS idx_email_scan_log_email_id ON email_scan_log(email_id);

-- Enable Row Level Security
ALTER TABLE email_scan_log ENABLE ROW LEVEL SECURITY;

-- RLS Policies for user isolation
CREATE POLICY "Users can view their own scan logs" ON email_scan_log
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own scan logs" ON email_scan_log
    FOR INSERT WITH CHECK (auth.uid() = user_id);

-- Service role bypass for backend operations
CREATE POLICY "Service role full access to email_scan_log" ON email_scan_log
    FOR ALL USING (
        current_setting('request.jwt.claims', true)::json->>'role' = 'service_role'
    );
