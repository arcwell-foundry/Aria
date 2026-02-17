-- Add status field to meeting_debriefs for two-phase debrief workflow
-- Supports: initiate -> process -> post_process flow

ALTER TABLE meeting_debriefs
ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'completed'
CHECK (status IN ('pending', 'processing', 'completed'));

-- Create index for finding pending debriefs
CREATE INDEX IF NOT EXISTS idx_debriefs_status ON meeting_debriefs(user_id, status);

-- Add comment for documentation
COMMENT ON COLUMN meeting_debriefs.status IS 'Debrief workflow status: pending (initiated), processing (AI extraction in progress), completed (fully processed)';
