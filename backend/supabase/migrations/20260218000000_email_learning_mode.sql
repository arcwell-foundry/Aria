-- Email Learning Mode Migration
-- Adds support for first-week learning mode and ongoing feedback integration
-- Designed to be idempotent - safe to run multiple times

-- ============================================================================
-- Part 1: Create draft_user_action enum
-- ============================================================================

DO $$ BEGIN
    CREATE TYPE draft_user_action AS ENUM (
        'pending',
        'approved',
        'edited',
        'rejected',
        'ignored'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

COMMENT ON TYPE draft_user_action IS 'Tracks user action on ARIA-generated email drafts for learning';

-- ============================================================================
-- Part 2: Add feedback columns to email_drafts table
-- ============================================================================

ALTER TABLE email_drafts
    ADD COLUMN IF NOT EXISTS user_action draft_user_action DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS user_edited_body TEXT,
    ADD COLUMN IF NOT EXISTS edit_distance FLOAT CHECK (edit_distance >= 0 AND edit_distance <= 1),
    ADD COLUMN IF NOT EXISTS action_detected_at TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS learning_mode_draft BOOLEAN DEFAULT false;

-- Indexes for learning mode queries
CREATE INDEX IF NOT EXISTS idx_email_drafts_user_action ON email_drafts(user_id, user_action) WHERE user_action != 'pending';
CREATE INDEX IF NOT EXISTS idx_email_drafts_learning_mode ON email_drafts(user_id, learning_mode_draft) WHERE learning_mode_draft = true;
CREATE INDEX IF NOT EXISTS idx_email_drafts_action_detected ON email_drafts(action_detected_at DESC) WHERE action_detected_at IS NOT NULL;

-- Comments for new columns
COMMENT ON COLUMN email_drafts.user_action IS 'User action on draft: pending/approved/edited/rejected/ignored';
COMMENT ON COLUMN email_drafts.user_edited_body IS 'If edited, stores the user-modified version';
COMMENT ON COLUMN email_drafts.edit_distance IS 'Levenshtein ratio (0-1) between original and edited draft';
COMMENT ON COLUMN email_drafts.action_detected_at IS 'When the user action was detected';
COMMENT ON COLUMN email_drafts.learning_mode_draft IS 'Whether this draft was created during learning mode period';

-- ============================================================================
-- Part 3: Create style_recalibration_log table
-- ============================================================================

CREATE TABLE IF NOT EXISTS style_recalibration_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    run_type TEXT NOT NULL DEFAULT 'weekly' CHECK (run_type IN ('weekly', 'manual', 'threshold')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    status TEXT DEFAULT 'running' CHECK (status IN ('running', 'completed', 'failed')),
    error_message TEXT,

    -- Input data
    emails_analyzed INT DEFAULT 0,
    edited_drafts_included INT DEFAULT 0,
    date_range_start TIMESTAMPTZ,
    date_range_end TIMESTAMPTZ,

    -- Results
    previous_fingerprint JSONB,
    new_fingerprint JSONB,
    fingerprint_changed BOOLEAN DEFAULT false,
    profiles_updated INT DEFAULT 0,
    changes_summary JSONB DEFAULT '{}'::jsonb,

    -- Confidence metrics
    previous_confidence FLOAT,
    new_confidence FLOAT,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for style_recalibration_log
CREATE INDEX IF NOT EXISTS idx_style_recalibration_user ON style_recalibration_log(user_id);
CREATE INDEX IF NOT EXISTS idx_style_recalibration_date ON style_recalibration_log(user_id, started_at DESC);
CREATE INDEX IF NOT EXISTS idx_style_recalibration_status ON style_recalibration_log(status);

-- Enable RLS on style_recalibration_log
ALTER TABLE style_recalibration_log ENABLE ROW LEVEL SECURITY;

-- RLS Policies for style_recalibration_log
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'style_recalibration_log' AND policyname = 'style_recalibration_log_select'
    ) THEN
        CREATE POLICY style_recalibration_log_select ON style_recalibration_log FOR SELECT USING (auth.uid() = user_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'style_recalibration_log' AND policyname = 'style_recalibration_log_insert'
    ) THEN
        CREATE POLICY style_recalibration_log_insert ON style_recalibration_log FOR INSERT WITH CHECK (auth.uid() = user_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'style_recalibration_log' AND policyname = 'style_recalibration_log_update'
    ) THEN
        CREATE POLICY style_recalibration_log_update ON style_recalibration_log FOR UPDATE USING (auth.uid() = user_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'style_recalibration_log' AND policyname = 'style_recalibration_log_delete'
    ) THEN
        CREATE POLICY style_recalibration_log_delete ON style_recalibration_log FOR DELETE USING (auth.uid() = user_id);
    END IF;
END $$;

COMMENT ON TABLE style_recalibration_log IS 'Tracks weekly style recalibration runs and their results';

-- ============================================================================
-- Part 4: Create draft_feedback_summary table
-- ============================================================================

CREATE TABLE IF NOT EXISTS draft_feedback_summary (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    period_start TIMESTAMPTZ NOT NULL,
    period_end TIMESTAMPTZ NOT NULL,

    -- Draft counts
    total_drafts INT DEFAULT 0,
    learning_mode_drafts INT DEFAULT 0,
    full_mode_drafts INT DEFAULT 0,

    -- Action counts
    approved_count INT DEFAULT 0,
    edited_count INT DEFAULT 0,
    rejected_count INT DEFAULT 0,
    ignored_count INT DEFAULT 0,
    pending_count INT DEFAULT 0,

    -- Edit metrics
    avg_edit_distance FLOAT,
    min_edit_distance FLOAT,
    max_edit_distance FLOAT,

    -- Derived insights
    approval_rate FLOAT,
    edit_rate FLOAT,
    rejection_rate FLOAT,

    -- Contact-level stats (top contacts)
    top_contacts JSONB DEFAULT '[]'::jsonb,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE(user_id, period_start, period_end)
);

-- Indexes for draft_feedback_summary
CREATE INDEX IF NOT EXISTS idx_draft_feedback_user ON draft_feedback_summary(user_id);
CREATE INDEX IF NOT EXISTS idx_draft_feedback_period ON draft_feedback_summary(user_id, period_end DESC);

-- Enable RLS on draft_feedback_summary
ALTER TABLE draft_feedback_summary ENABLE ROW LEVEL SECURITY;

-- RLS Policies for draft_feedback_summary
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'draft_feedback_summary' AND policyname = 'draft_feedback_summary_select'
    ) THEN
        CREATE POLICY draft_feedback_summary_select ON draft_feedback_summary FOR SELECT USING (auth.uid() = user_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'draft_feedback_summary' AND policyname = 'draft_feedback_summary_insert'
    ) THEN
        CREATE POLICY draft_feedback_summary_insert ON draft_feedback_summary FOR INSERT WITH CHECK (auth.uid() = user_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'draft_feedback_summary' AND policyname = 'draft_feedback_summary_update'
    ) THEN
        CREATE POLICY draft_feedback_summary_update ON draft_feedback_summary FOR UPDATE USING (auth.uid() = user_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE tablename = 'draft_feedback_summary' AND policyname = 'draft_feedback_summary_delete'
    ) THEN
        CREATE POLICY draft_feedback_summary_delete ON draft_feedback_summary FOR DELETE USING (auth.uid() = user_id);
    END IF;
END $$;

COMMENT ON TABLE draft_feedback_summary IS 'Weekly aggregated feedback metrics for learning mode tracking';

-- ============================================================================
-- Part 5: Function to get/set learning mode config
-- ============================================================================

-- Helper function to initialize learning mode config in user_settings
CREATE OR REPLACE FUNCTION init_learning_mode_config(user_uuid UUID)
RETURNS VOID AS $$
DECLARE
    current_integrations JSONB;
BEGIN
    -- Get current integrations
    SELECT COALESCE(integrations, '{}'::jsonb) INTO current_integrations
    FROM user_settings
    WHERE user_id = user_uuid;

    -- Initialize email.learning_mode if not exists
    IF current_integrations->'email'->'learning_mode' IS NULL THEN
        current_integrations := jsonb_set(
            current_integrations,
            '{email}',
            COALESCE(current_integrations->'email', '{}'::jsonb) ||
            jsonb_build_object(
                'learning_mode', true,
                'learning_mode_start_date', NOW(),
                'draft_interaction_count', 0,
                'top_contacts', '[]'::jsonb,
                'full_mode_transition_date', NULL
            )
        );

        UPDATE user_settings
        SET integrations = current_integrations
        WHERE user_id = user_uuid;
    END IF;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

COMMENT ON FUNCTION init_learning_mode_config IS 'Initialize learning mode config in user_settings.integrations.email';

-- ============================================================================
-- Part 6: Verification
-- ============================================================================

DO $$
BEGIN
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Email Learning Mode Migration Complete';
    RAISE NOTICE '============================================';
    RAISE NOTICE 'Enum created:';
    RAISE NOTICE '  - draft_user_action (pending/approved/edited/rejected/ignored)';
    RAISE NOTICE '';
    RAISE NOTICE 'Tables created:';
    RAISE NOTICE '  - style_recalibration_log (with RLS)';
    RAISE NOTICE '  - draft_feedback_summary (with RLS)';
    RAISE NOTICE '';
    RAISE NOTICE 'Tables updated:';
    RAISE NOTICE '  - email_drafts (added user_action, user_edited_body, edit_distance, action_detected_at, learning_mode_draft)';
    RAISE NOTICE '';
    RAISE NOTICE 'Functions created:';
    RAISE NOTICE '  - init_learning_mode_config(user_uuid)';
END $$;
