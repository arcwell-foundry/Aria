-- Sprint 4: Depth & Polish
-- Adds role column to user_profiles for role-based behavior (Fix 3)
-- Extends goal_milestones with agent_type and success_criteria for goal decomposition (Fix 2)

-- Fix 3: Role dropdown in User Profile
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS role TEXT;

-- Fix 2: Goal decomposition — extend goal_milestones with agent assignment and success criteria
ALTER TABLE goal_milestones ADD COLUMN IF NOT EXISTS agent_type TEXT;
ALTER TABLE goal_milestones ADD COLUMN IF NOT EXISTS success_criteria TEXT;
