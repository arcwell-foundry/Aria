-- Add retry_count column to lead_memory_crm_sync
ALTER TABLE lead_memory_crm_sync
ADD COLUMN IF NOT EXISTS retry_count INT DEFAULT 0;

-- Add index for finding failed syncs needing retry
CREATE INDEX IF NOT EXISTS idx_crm_sync_status_retry
ON lead_memory_crm_sync(status, retry_count)
WHERE status IN ('error', 'pending');

COMMENT ON COLUMN lead_memory_crm_sync.retry_count IS 'Number of retry attempts after sync failure. Max 5.';
