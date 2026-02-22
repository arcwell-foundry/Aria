-- Add confidence_tier column to email_drafts
-- Part of the refactor from learning-mode gating to confidence-based drafting.
-- Values: HIGH, MEDIUM, LOW, MINIMAL
ALTER TABLE email_drafts ADD COLUMN IF NOT EXISTS confidence_tier TEXT DEFAULT 'LOW';
