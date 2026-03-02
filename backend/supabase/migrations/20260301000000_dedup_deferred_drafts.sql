-- Deduplicate existing deferred_email_drafts rows and add unique constraint
-- to prevent future duplicates.

-- Step 1: Delete duplicate rows, keeping the most recent per (user_id, thread_id)
DELETE FROM deferred_email_drafts
WHERE id NOT IN (
  SELECT DISTINCT ON (user_id, thread_id) id
  FROM deferred_email_drafts
  ORDER BY user_id, thread_id, created_at DESC
);

-- Step 2: Add unique constraint on (user_id, thread_id) to enforce at DB level.
-- This backs the upsert on_conflict="user_id,thread_id" in the application code.
ALTER TABLE deferred_email_drafts
  ADD CONSTRAINT uq_deferred_user_thread UNIQUE (user_id, thread_id);
