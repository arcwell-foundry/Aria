-- Migration: Create skills_index table
-- US-524: Skill Index Service
-- NOTE: Applied manually via Supabase Dashboard

CREATE TABLE IF NOT EXISTS skills_index (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    skill_path TEXT NOT NULL UNIQUE,
    skill_name TEXT NOT NULL,
    description TEXT,
    full_content TEXT,
    content_hash TEXT,
    author TEXT,
    version TEXT,
    tags TEXT[] DEFAULT '{}',
    install_count INT DEFAULT 0,
    trust_level TEXT DEFAULT 'community',
    security_verified BOOLEAN DEFAULT FALSE,
    life_sciences_relevant BOOLEAN DEFAULT FALSE,
    declared_permissions TEXT[] DEFAULT '{}',
    summary_verbosity TEXT DEFAULT 'standard',
    last_synced TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE skills_index ENABLE ROW LEVEL SECURITY;
CREATE POLICY "skills_index_read" ON skills_index FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role can manage skills_index" ON skills_index FOR ALL USING (auth.role() = 'service_role');
CREATE INDEX idx_skills_index_tags ON skills_index USING GIN(tags);
CREATE INDEX idx_skills_index_trust ON skills_index(trust_level);
CREATE INDEX idx_skills_index_path ON skills_index(skill_path);
