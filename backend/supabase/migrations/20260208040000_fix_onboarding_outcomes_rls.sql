-- Fix RLS policies that reference user_profiles.user_id (nonexistent column).
-- The correct column is user_profiles.id (PK that references auth.users.id).

-- 1. Fix admin_outcome_select on onboarding_outcomes
DROP POLICY IF EXISTS "admin_outcome_select" ON onboarding_outcomes;
CREATE POLICY "admin_outcome_select" ON onboarding_outcomes
    FOR SELECT TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM user_profiles
            WHERE user_profiles.id = auth.uid()
            AND user_profiles.role IN ('admin', 'manager')
        )
    );

-- 2. Fix admin_insights_all on procedural_insights
DROP POLICY IF EXISTS "admin_insights_all" ON procedural_insights;
CREATE POLICY "admin_insights_all" ON procedural_insights
    FOR ALL TO authenticated
    USING (
        EXISTS (
            SELECT 1 FROM user_profiles
            WHERE user_profiles.id = auth.uid()
            AND user_profiles.role = 'admin'
        )
    );
