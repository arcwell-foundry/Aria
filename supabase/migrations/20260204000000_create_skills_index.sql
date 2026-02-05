-- Migration: Create skills_index table
-- US-524: Skill Index Service

-- Create enum for trust level (matches SkillTrustLevel in backend/src/security/trust_levels.py)
DO $$ BEGIN
    CREATE TYPE skill_trust_level AS ENUM (
        'core',
        'verified',
        'community',
        'user'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Create enum for summary verbosity
DO $$ BEGIN
    CREATE TYPE skill_summary_verbosity AS ENUM (
        'minimal',
        'standard',
        'detailed'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Create skills_index table
CREATE TABLE IF NOT EXISTS skills_index (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_path TEXT UNIQUE NOT NULL,
    skill_name TEXT NOT NULL,
    description TEXT,
    full_content TEXT,
    content_hash TEXT,
    author TEXT,
    version TEXT,
    tags TEXT[] DEFAULT '{}',
    trust_level skill_trust_level DEFAULT 'community',
    life_sciences_relevant BOOLEAN DEFAULT FALSE,
    declared_permissions TEXT[] DEFAULT '{}',
    summary_verbosity skill_summary_verbosity DEFAULT 'standard',
    last_synced TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Create indexes for efficient querying
CREATE INDEX idx_skills_index_skill_path ON skills_index(skill_path);
CREATE INDEX idx_skills_index_trust_level ON skills_index(trust_level);
CREATE INDEX idx_skills_index_life_sciences ON skills_index(life_sciences_relevant);
CREATE INDEX idx_skills_index_tags ON skills_index USING GIN(tags);
CREATE INDEX idx_skills_index_name_gin ON skills_index USING GIN(to_tsvector('english', skill_name || ' ' || COALESCE(description, '')));
CREATE INDEX idx_skills_index_last_synced ON skills_index(last_synced DESC);
CREATE INDEX idx_skills_index_content_hash ON skills_index(content_hash);
CREATE INDEX idx_skills_index_updated_at ON skills_index(updated_at DESC);

-- Enable RLS
ALTER TABLE skills_index ENABLE ROW LEVEL SECURITY;

-- RLS Policies: All authenticated users can read skills (skill catalog is shared)
CREATE POLICY "Authenticated users can view skills"
    ON skills_index FOR SELECT
    USING (auth.uid() IS NOT NULL);

-- Only service role can insert/update/delete skills (via backend service)
CREATE POLICY "Service role can insert skills"
    ON skills_index FOR INSERT
    WITH CHECK (auth.role() = 'service_role');

CREATE POLICY "Service role can update skills"
    ON skills_index FOR UPDATE
    USING (auth.role() = 'service_role');

CREATE POLICY "Service role can delete skills"
    ON skills_index FOR DELETE
    USING (auth.role() = 'service_role');

-- Trigger for updated_at
CREATE OR REPLACE FUNCTION update_skills_index_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_update_skills_index_updated_at
    BEFORE UPDATE ON skills_index
    FOR EACH ROW
    EXECUTE FUNCTION update_skills_index_updated_at();

-- Comment on table
COMMENT ON TABLE skills_index IS 'Catalog of skills from skills.sh with metadata for search and security classification';
