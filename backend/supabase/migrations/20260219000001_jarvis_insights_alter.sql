-- Migration: Alter jarvis_insights table for US-702 Implication Reasoning Engine
-- Purpose: Add missing columns for the Implication Reasoning Engine
-- User Story: US-702 Implication Reasoning Engine

-- Add missing columns if they don't exist
DO $$
BEGIN
    -- Add classification column if missing
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'jarvis_insights' AND column_name = 'classification'
    ) THEN
        ALTER TABLE jarvis_insights ADD COLUMN classification TEXT;
        ALTER TABLE jarvis_insights ADD CONSTRAINT chk_jarvis_classification
            CHECK (classification IN ('opportunity', 'threat', 'neutral'));
    END IF;

    -- Add impact_score column if missing
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'jarvis_insights' AND column_name = 'impact_score'
    ) THEN
        ALTER TABLE jarvis_insights ADD COLUMN impact_score REAL;
        ALTER TABLE jarvis_insights ADD CONSTRAINT chk_jarvis_impact
            CHECK (impact_score BETWEEN 0 AND 1);
    END IF;

    -- Add confidence column if missing
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'jarvis_insights' AND column_name = 'confidence'
    ) THEN
        ALTER TABLE jarvis_insights ADD COLUMN confidence REAL;
        ALTER TABLE jarvis_insights ADD CONSTRAINT chk_jarvis_confidence
            CHECK (confidence BETWEEN 0 AND 1);
    END IF;

    -- Add urgency column if missing
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'jarvis_insights' AND column_name = 'urgency'
    ) THEN
        ALTER TABLE jarvis_insights ADD COLUMN urgency REAL;
        ALTER TABLE jarvis_insights ADD CONSTRAINT chk_jarvis_urgency
            CHECK (urgency BETWEEN 0 AND 1);
    END IF;

    -- Add combined_score column if missing
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'jarvis_insights' AND column_name = 'combined_score'
    ) THEN
        ALTER TABLE jarvis_insights ADD COLUMN combined_score REAL;
        ALTER TABLE jarvis_insights ADD CONSTRAINT chk_jarvis_combined
            CHECK (combined_score BETWEEN 0 AND 1);
    END IF;

    -- Add causal_chain column if missing
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'jarvis_insights' AND column_name = 'causal_chain'
    ) THEN
        ALTER TABLE jarvis_insights ADD COLUMN causal_chain JSONB DEFAULT '[]'::jsonb;
    END IF;

    -- Add affected_goals column if missing
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'jarvis_insights' AND column_name = 'affected_goals'
    ) THEN
        ALTER TABLE jarvis_insights ADD COLUMN affected_goals JSONB DEFAULT '[]'::jsonb;
    END IF;

    -- Add recommended_actions column if missing
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'jarvis_insights' AND column_name = 'recommended_actions'
    ) THEN
        ALTER TABLE jarvis_insights ADD COLUMN recommended_actions JSONB DEFAULT '[]'::jsonb;
    END IF;

    -- Add status column if missing
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'jarvis_insights' AND column_name = 'status'
    ) THEN
        ALTER TABLE jarvis_insights ADD COLUMN status TEXT DEFAULT 'new';
        ALTER TABLE jarvis_insights ADD CONSTRAINT chk_jarvis_status
            CHECK (status IN ('new', 'engaged', 'dismissed', 'feedback'));
    END IF;

    -- Add feedback_text column if missing
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'jarvis_insights' AND column_name = 'feedback_text'
    ) THEN
        ALTER TABLE jarvis_insights ADD COLUMN feedback_text TEXT;
    END IF;

    -- Add updated_at column if missing
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'jarvis_insights' AND column_name = 'updated_at'
    ) THEN
        ALTER TABLE jarvis_insights ADD COLUMN updated_at TIMESTAMPTZ DEFAULT NOW();
    END IF;
END $$;

-- Create indexes if they don't exist
CREATE INDEX IF NOT EXISTS idx_jarvis_insights_user_id ON jarvis_insights(user_id);
CREATE INDEX IF NOT EXISTS idx_jarvis_insights_type ON jarvis_insights(insight_type);
CREATE INDEX IF NOT EXISTS idx_jarvis_insights_classification ON jarvis_insights(classification);
CREATE INDEX IF NOT EXISTS idx_jarvis_insights_status ON jarvis_insights(status);
CREATE INDEX IF NOT EXISTS idx_jarvis_insights_score ON jarvis_insights(combined_score DESC);
CREATE INDEX IF NOT EXISTS idx_jarvis_insights_created_at ON jarvis_insights(created_at DESC);

-- Create or replace the trigger for auto-updating updated_at
CREATE OR REPLACE FUNCTION update_jarvis_insights_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Drop trigger if exists and recreate
DROP TRIGGER IF EXISTS trigger_jarvis_insights_updated_at ON jarvis_insights;
CREATE TRIGGER trigger_jarvis_insights_updated_at
    BEFORE UPDATE ON jarvis_insights
    FOR EACH ROW
    EXECUTE FUNCTION update_jarvis_insights_updated_at();

-- Ensure RLS is enabled
ALTER TABLE jarvis_insights ENABLE ROW LEVEL SECURITY;

-- Create RLS policies if they don't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'jarvis_insights' AND policyname = 'Users can view own insights'
    ) THEN
        CREATE POLICY "Users can view own insights" ON jarvis_insights
            FOR SELECT USING (auth.uid() = user_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'jarvis_insights' AND policyname = 'Users can insert own insights'
    ) THEN
        CREATE POLICY "Users can insert own insights" ON jarvis_insights
            FOR INSERT WITH CHECK (auth.uid() = user_id);
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'jarvis_insights' AND policyname = 'Users can update own insights'
    ) THEN
        CREATE POLICY "Users can update own insights" ON jarvis_insights
            FOR UPDATE USING (auth.uid() = user_id)
            WITH CHECK (auth.uid() = user_id);
    END IF;
END $$;

-- Grant permissions
GRANT SELECT, INSERT, UPDATE ON jarvis_insights TO authenticated;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO authenticated;

-- Add comments for documentation
COMMENT ON TABLE jarvis_insights IS 'Stores proactive insights from JARVIS Implication Reasoning Engine (US-702)';
COMMENT ON COLUMN jarvis_insights.classification IS 'Impact classification: opportunity, threat, neutral';
COMMENT ON COLUMN jarvis_insights.status IS 'Engagement status: new (unseen), engaged (viewed), dismissed, feedback (user provided feedback)';
