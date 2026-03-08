-- Add user_replied column to email_scan_log for reply detection caching
-- NULL = not checked, TRUE = user has replied, FALSE = no reply detected
-- Prevents expensive re-checks against email provider API on every scan

ALTER TABLE email_scan_log
    ADD COLUMN IF NOT EXISTS user_replied BOOLEAN DEFAULT NULL;

COMMENT ON COLUMN email_scan_log.user_replied IS
'Cached result of reply detection check. NULL = not checked, TRUE = user replied to this thread, FALSE = no reply detected. Avoids repeated email provider API calls.';

-- Index for efficient lookup of unchecked NEEDS_REPLY emails
CREATE INDEX IF NOT EXISTS idx_email_scan_log_needs_reply_unchecked
    ON email_scan_log(user_id, category)
    WHERE category = 'NEEDS_REPLY' AND user_replied IS NULL;
