-- US-943: ROI Analytics Dashboard (Task 1 - Database Schema)
-- Tracks ARIA-generated value metrics for time savings, intelligence delivery, and pipeline impact

-- aria_actions table: tracks ARIA-generated actions that save user time
CREATE TABLE IF NOT EXISTS aria_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    action_type TEXT NOT NULL CHECK (action_type IN (
        'email_draft',
        'meeting_prep',
        'research_report',
        'crm_update',
        'follow_up',
        'lead_discovery'
    )),
    source_id TEXT, -- Reference to related entity (email_id, meeting_id, lead_id, etc.)
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending',
        'auto_approved',
        'user_approved',
        'rejected'
    )),
    estimated_minutes_saved INTEGER NOT NULL DEFAULT 0 CHECK (estimated_minutes_saved >= 0),
    metadata JSONB DEFAULT '{}', -- Additional context about the action
    created_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

-- intelligence_delivered table: tracks intelligence delivered to users
CREATE TABLE IF NOT EXISTS intelligence_delivered (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    intelligence_type TEXT NOT NULL CHECK (intelligence_type IN (
        'fact',
        'signal',
        'gap_filled',
        'briefing',
        'proactive_insight'
    )),
    source_id TEXT, -- Reference to related entity (memory_id, signal_id, briefing_id, etc.)
    confidence_score FLOAT CHECK (confidence_score >= 0 AND confidence_score <= 1),
    metadata JSONB DEFAULT '{}', -- Additional context about the intelligence
    delivered_at TIMESTAMPTZ DEFAULT NOW()
);

-- pipeline_impact table: tracks pipeline impact metrics
CREATE TABLE IF NOT EXISTS pipeline_impact (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    impact_type TEXT NOT NULL CHECK (impact_type IN (
        'lead_discovered',
        'meeting_prepped',
        'follow_up_sent',
        'deal_influenced'
    )),
    source_id TEXT, -- Reference to related entity (lead_id, opportunity_id, etc.)
    estimated_value FLOAT CHECK (estimated_value >= 0), -- Estimated value in USD
    metadata JSONB DEFAULT '{}', -- Additional context about the impact
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_aria_actions_user_created ON aria_actions(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_aria_actions_type_status ON aria_actions(action_type, status);
CREATE INDEX IF NOT EXISTS idx_aria_actions_source ON aria_actions(source_id);

CREATE INDEX IF NOT EXISTS idx_intelligence_delivered_user_delivered ON intelligence_delivered(user_id, delivered_at DESC);
CREATE INDEX IF NOT EXISTS idx_intelligence_delivered_type ON intelligence_delivered(intelligence_type);
CREATE INDEX IF NOT EXISTS idx_intelligence_delivered_source ON intelligence_delivered(source_id);

CREATE INDEX IF NOT EXISTS idx_pipeline_impact_user_created ON pipeline_impact(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_impact_type ON pipeline_impact(impact_type);
CREATE INDEX IF NOT EXISTS idx_pipeline_impact_source ON pipeline_impact(source_id);

-- Enable Row Level Security
ALTER TABLE aria_actions ENABLE ROW LEVEL SECURITY;
ALTER TABLE intelligence_delivered ENABLE ROW LEVEL SECURITY;
ALTER TABLE pipeline_impact ENABLE ROW LEVEL SECURITY;

-- RLS Policies for aria_actions
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'users_own_actions_select' AND tablename = 'aria_actions') THEN
        CREATE POLICY "users_own_actions_select" ON aria_actions
            FOR SELECT TO authenticated USING (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'users_own_actions_insert' AND tablename = 'aria_actions') THEN
        CREATE POLICY "users_own_actions_insert" ON aria_actions
            FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'users_own_actions_update' AND tablename = 'aria_actions') THEN
        CREATE POLICY "users_own_actions_update" ON aria_actions
            FOR UPDATE TO authenticated USING (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'admin_can_read_actions' AND tablename = 'aria_actions') THEN
        CREATE POLICY "admin_can_read_actions" ON aria_actions
            FOR SELECT TO authenticated
            USING (
                EXISTS (
                    SELECT 1 FROM user_profiles
                    WHERE user_profiles.id = auth.uid()
                    AND user_profiles.role IN ('admin', 'manager')
                )
            );
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'service_role_actions_all' AND tablename = 'aria_actions') THEN
        CREATE POLICY "service_role_actions_all" ON aria_actions
            FOR ALL TO service_role USING (true);
    END IF;
END $$;

-- RLS Policies for intelligence_delivered
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'users_own_intelligence_select' AND tablename = 'intelligence_delivered') THEN
        CREATE POLICY "users_own_intelligence_select" ON intelligence_delivered
            FOR SELECT TO authenticated USING (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'users_own_intelligence_insert' AND tablename = 'intelligence_delivered') THEN
        CREATE POLICY "users_own_intelligence_insert" ON intelligence_delivered
            FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'users_own_intelligence_update' AND tablename = 'intelligence_delivered') THEN
        CREATE POLICY "users_own_intelligence_update" ON intelligence_delivered
            FOR UPDATE TO authenticated USING (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'admin_can_read_intelligence' AND tablename = 'intelligence_delivered') THEN
        CREATE POLICY "admin_can_read_intelligence" ON intelligence_delivered
            FOR SELECT TO authenticated
            USING (
                EXISTS (
                    SELECT 1 FROM user_profiles
                    WHERE user_profiles.id = auth.uid()
                    AND user_profiles.role IN ('admin', 'manager')
                )
            );
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'service_role_intelligence_all' AND tablename = 'intelligence_delivered') THEN
        CREATE POLICY "service_role_intelligence_all" ON intelligence_delivered
            FOR ALL TO service_role USING (true);
    END IF;
END $$;

-- RLS Policies for pipeline_impact
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'users_own_impact_select' AND tablename = 'pipeline_impact') THEN
        CREATE POLICY "users_own_impact_select" ON pipeline_impact
            FOR SELECT TO authenticated USING (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'users_own_impact_insert' AND tablename = 'pipeline_impact') THEN
        CREATE POLICY "users_own_impact_insert" ON pipeline_impact
            FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'users_own_impact_update' AND tablename = 'pipeline_impact') THEN
        CREATE POLICY "users_own_impact_update" ON pipeline_impact
            FOR UPDATE TO authenticated USING (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'admin_can_read_impact' AND tablename = 'pipeline_impact') THEN
        CREATE POLICY "admin_can_read_impact" ON pipeline_impact
            FOR SELECT TO authenticated
            USING (
                EXISTS (
                    SELECT 1 FROM user_profiles
                    WHERE user_profiles.id = auth.uid()
                    AND user_profiles.role IN ('admin', 'manager')
                )
            );
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE policyname = 'service_role_impact_all' AND tablename = 'pipeline_impact') THEN
        CREATE POLICY "service_role_impact_all" ON pipeline_impact
            FOR ALL TO service_role USING (true);
    END IF;
END $$;

-- Comments for documentation
COMMENT ON TABLE aria_actions IS 'Tracks ARIA-generated actions that save user time for ROI calculation';
COMMENT ON TABLE intelligence_delivered IS 'Tracks intelligence delivered to users for ROI analytics';
COMMENT ON TABLE pipeline_impact IS 'Tracks pipeline impact metrics for ROI calculation';

COMMENT ON COLUMN aria_actions.estimated_minutes_saved IS 'Estimated time saved by this action (used for time savings ROI metric)';
COMMENT ON COLUMN intelligence_delivered.confidence_score IS 'Confidence level of the intelligence (0-1)';
COMMENT ON COLUMN pipeline_impact.estimated_value IS 'Estimated value in USD for pipeline impact';
