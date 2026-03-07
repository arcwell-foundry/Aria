-- Add competitive displacement support to email_drafts
-- Extends the table with columns needed for intelligence-generated drafts

-- Add 'competitive_displacement' and 'conference_outreach' and 'clinical_trial_outreach' to email_purpose enum
DO $$ BEGIN
    ALTER TYPE email_purpose ADD VALUE IF NOT EXISTS 'competitive_displacement';
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TYPE email_purpose ADD VALUE IF NOT EXISTS 'conference_outreach';
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TYPE email_purpose ADD VALUE IF NOT EXISTS 'clinical_trial_outreach';
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Add 'pending_review' and 'saved_to_client' to email_draft_status enum
DO $$ BEGIN
    ALTER TYPE email_draft_status ADD VALUE IF NOT EXISTS 'pending_review';
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
    ALTER TYPE email_draft_status ADD VALUE IF NOT EXISTS 'saved_to_client';
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Add competitive positioning columns to email_drafts
ALTER TABLE email_drafts
ADD COLUMN IF NOT EXISTS competitive_positioning JSONB DEFAULT '{}',
ADD COLUMN IF NOT EXISTS draft_type TEXT,
ADD COLUMN IF NOT EXISTS insight_id UUID;

-- Index for efficient querying by draft_type
CREATE INDEX IF NOT EXISTS idx_email_drafts_draft_type ON email_drafts(draft_type);

-- Add 'action_completed' to notifications type check if not already present
-- The CHECK constraint on notifications.type may need updating
-- Using a permissive approach: drop and recreate the constraint
DO $$ BEGIN
    ALTER TABLE notifications DROP CONSTRAINT IF EXISTS notifications_type_check;
    ALTER TABLE notifications ADD CONSTRAINT notifications_type_check
        CHECK (type IN (
            'briefing_ready', 'signal_detected', 'task_due',
            'meeting_brief_ready', 'draft_ready', 'action_completed'
        ));
EXCEPTION WHEN OTHERS THEN NULL; END $$;

-- Also relax pulse_signals pulse_type constraint to allow intelligence-generated pulses
DO $$ BEGIN
    ALTER TABLE pulse_signals DROP CONSTRAINT IF EXISTS pulse_signals_pulse_type_check;
    ALTER TABLE pulse_signals ADD CONSTRAINT pulse_signals_pulse_type_check
        CHECK (pulse_type IN (
            'scheduled', 'event', 'intelligent', 'aria_intelligence'
        ));
EXCEPTION WHEN OTHERS THEN NULL; END $$;
