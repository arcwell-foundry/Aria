-- Performance index for email_drafts list queries filtered by user + status.
-- The existing idx_email_drafts_status (status only) does not help
-- when the query also filters by user_id + excludes dismissed statuses.
CREATE INDEX IF NOT EXISTS idx_email_drafts_user_status
ON email_drafts (user_id, status);
