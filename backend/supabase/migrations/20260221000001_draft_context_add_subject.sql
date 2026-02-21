-- Add missing subject column to draft_context table.
-- The original CREATE TABLE migration included this column, but the table
-- was created before the migration was applied, so the column is absent
-- in production.  This ALTER adds it idempotently.

ALTER TABLE draft_context ADD COLUMN IF NOT EXISTS subject TEXT;
