-- Clean up stuck email processing run from Feb 15
-- This run was stuck in "running" status for 6+ days because
-- the scan endpoint was not wired to AutonomousDraftEngine.process_inbox()
UPDATE email_processing_runs
SET
    status = 'failed',
    completed_at = NOW(),
    error_message = 'Stuck since Feb 15 - scan endpoint was not wired to draft pipeline. Cleaned up by migration 20260221.'
WHERE id = '446b7982-4138-4d1b-ac42-986219c246c8'
  AND status = 'running';
