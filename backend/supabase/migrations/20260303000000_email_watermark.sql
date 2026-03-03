-- Email Watermark Tracking
-- Adds watermark columns to email_processing_runs to prevent re-scanning emails

-- Add watermark columns to track which emails have been processed
ALTER TABLE email_processing_runs
    ADD COLUMN IF NOT EXISTS watermark_email_id TEXT,
    ADD COLUMN IF NOT EXISTS watermark_timestamp TIMESTAMPTZ;

-- Add comments to explain the columns
COMMENT ON COLUMN email_processing_runs.watermark_email_id IS 'ID of the newest email processed in this run (from Composio)';
COMMENT ON COLUMN email_processing_runs.watermark_timestamp IS 'Timestamp of the newest email processed - used to filter future scans';

-- Create index for efficient watermark queries
CREATE INDEX IF NOT EXISTS idx_email_processing_runs_watermark
    ON email_processing_runs(user_id, status, watermark_timestamp DESC);
