-- Migration: Deduplicate email drafts across processing runs
-- Fixes: _check_existing_draft() had two bugs:
--   1. status filter referenced non-existent enum value 'saved_to_client',
--      causing the query to throw and the except handler to return None always.
--   2. user_action IS NULL never matched because user_action defaults to 'pending'.
-- Both bugs caused the dedup check to silently find zero rows every time.

-- Step 1: Delete duplicate drafts, keeping only the oldest per email_id per user
DELETE FROM email_drafts
WHERE id NOT IN (
    SELECT DISTINCT ON (user_id, original_email_id) id
    FROM email_drafts
    WHERE original_email_id IS NOT NULL
    ORDER BY user_id, original_email_id, created_at ASC
)
AND original_email_id IS NOT NULL;

-- Step 2: Drop the broken unique index (used non-existent enum value and
-- user_action IS NULL which never matched).
DROP INDEX IF EXISTS uq_email_drafts_pending_per_email;

-- Step 3: Add corrected partial unique index.
-- Enforces uniqueness for drafts that haven't been rejected.
CREATE UNIQUE INDEX IF NOT EXISTS uq_email_drafts_pending_per_email
ON email_drafts (user_id, original_email_id)
WHERE original_email_id IS NOT NULL
  AND user_action IS DISTINCT FROM 'rejected';
