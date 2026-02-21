-- Add drafts_failed column to email_processing_runs table.
-- The column was present in the original migration (20260216000000) but missing
-- from the later email_intelligence_system migration (20260217000000) which
-- recreated the table schema without it. The application code tracks draft
-- generation failures in this column.

ALTER TABLE email_processing_runs
    ADD COLUMN IF NOT EXISTS drafts_failed INTEGER DEFAULT 0;

COMMENT ON COLUMN email_processing_runs.drafts_failed IS 'Number of draft generation failures during this processing run';
