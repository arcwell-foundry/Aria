-- Migration: Create user_skills table
-- US-525: Skill Installation Service

-- Create user_skills table for tracking installed skills per user
CREATE TABLE user_skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    tenant_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    skill_id UUID REFERENCES skills_index(id) ON DELETE CASCADE NOT NULL,
    skill_path TEXT NOT NULL,
    trust_level TEXT NOT NULL CHECK (trust_level IN ('core', 'verified', 'community', 'user')),
    permissions_granted TEXT[] DEFAULT '{}',
    installed_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    auto_installed BOOLEAN DEFAULT FALSE,
    last_used_at TIMESTAMPTZ,
    execution_count INT DEFAULT 0,
    success_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    UNIQUE(user_id, skill_id)
);

-- Create indexes for efficient querying
CREATE INDEX idx_user_skills_user_id ON user_skills(user_id);
CREATE INDEX idx_user_skills_tenant_id ON user_skills(tenant_id);
CREATE INDEX idx_user_skills_skill_id ON user_skills(skill_id);
CREATE INDEX idx_user_skills_skill_path ON user_skills(skill_path);
CREATE INDEX idx_user_skills_trust_level ON user_skills(trust_level);
CREATE INDEX idx_user_skills_last_used ON user_skills(last_used_at DESC);
CREATE INDEX idx_user_skills_auto_installed ON user_skills(auto_installed) WHERE auto_installed = TRUE;

-- Enable Row Level Security
ALTER TABLE user_skills ENABLE ROW LEVEL SECURITY;

-- RLS Policies: Users can manage their own installed skills
CREATE POLICY "Users can view own skills"
    ON user_skills FOR SELECT
    USING (user_id = auth.uid());

CREATE POLICY "Users can insert own skills"
    ON user_skills FOR INSERT
    WITH CHECK (user_id = auth.uid());

CREATE POLICY "Users can update own skills"
    ON user_skills FOR UPDATE
    USING (user_id = auth.uid());

CREATE POLICY "Users can delete own skills"
    ON user_skills FOR DELETE
    USING (user_id = auth.uid());

-- Service role bypass policies (for backend operations)
CREATE POLICY "Service role can manage user_skills"
    ON user_skills FOR ALL
    USING (auth.role() = 'service_role');

-- Updated_at trigger
CREATE TRIGGER update_user_skills_updated_at
    BEFORE UPDATE ON user_skills
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Add comments for documentation
COMMENT ON TABLE user_skills IS 'Tracks skills installed by users with usage statistics and trust levels';
COMMENT ON COLUMN user_skills.tenant_id IS 'Optional company/tenant association for multi-tenant scenarios';
COMMENT ON COLUMN user_skills.skill_id IS 'References the skill in skills_index table';
COMMENT ON COLUMN user_skills.skill_path IS 'Cached skill path for quick lookup without joining';
COMMENT ON COLUMN user_skills.trust_level IS 'Cached trust level: core, verified, community, user';
COMMENT ON COLUMN user_skills.permissions_granted IS 'Array of permissions granted to this skill';
COMMENT ON COLUMN user_skills.auto_installed IS 'TRUE if automatically installed by ARIA, FALSE if user-installed';
COMMENT ON COLUMN user_skills.execution_count IS 'Total number of times this skill has been executed';
COMMENT ON COLUMN user_skills.success_count IS 'Number of successful executions';
