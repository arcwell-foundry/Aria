-- Migration: Deduplicate email drafts across processing runs
-- Fixes: _check_existing_draft() using maybe_single() which threw on 2+ rows,
-- causing the exception handler to return false and snowball more duplicates.

-- Step 1: Delete duplicate drafts, keeping only the most recent per email_id per user
DELETE FROM email_drafts
WHERE id NOT IN (
    SELECT DISTINCT ON (user_id, original_email_id) id
    FROM email_drafts
    WHERE original_email_id IS NOT NULL
    ORDER BY user_id, original_email_id, created_at DESC
)
AND original_email_id IS NOT NULL;

-- Step 2: Add a partial unique index to prevent future duplicates.
-- Only enforces uniqueness for drafts that haven't been acted on (user_action IS NULL)
-- and are still in draft/saved_to_client status.
CREATE UNIQUE INDEX IF NOT EXISTS uq_email_drafts_pending_per_email
ON email_drafts (user_id, original_email_id)
WHERE original_email_id IS NOT NULL
  AND status IN ('draft', 'saved_to_client')
  AND user_action IS NULL;
