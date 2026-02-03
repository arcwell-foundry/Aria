-- Migration: US-218 Memory Salience Decay System
-- Adds salience tracking to memory tables and creates access log

-- =============================================================================
-- Memory Salience Tracking Tables
-- =============================================================================
-- Note: episodic_memories and semantic_facts are primarily stored in Graphiti.
-- These Supabase tables track salience metadata keyed by Graphiti episode UUIDs.

-- Episodic memory salience tracking
CREATE TABLE episodic_memory_salience (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    graphiti_episode_id TEXT NOT NULL,  -- Reference to Graphiti episode
    current_salience FLOAT DEFAULT 1.0 CHECK (current_salience >= 0 AND current_salience <= 1),
    last_accessed_at TIMESTAMPTZ DEFAULT NOW(),
    access_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, graphiti_episode_id)
);

-- Semantic fact salience tracking
CREATE TABLE semantic_fact_salience (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    graphiti_episode_id TEXT NOT NULL,  -- Reference to Graphiti episode
    current_salience FLOAT DEFAULT 1.0 CHECK (current_salience >= 0 AND current_salience <= 1),
    last_accessed_at TIMESTAMPTZ DEFAULT NOW(),
    access_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(user_id, graphiti_episode_id)
);

-- Memory access log for all memory types
CREATE TABLE memory_access_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    memory_id TEXT NOT NULL,  -- Graphiti episode ID or other memory ID
    memory_type TEXT NOT NULL CHECK (memory_type IN ('episodic', 'semantic', 'lead')),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    access_context TEXT,  -- What triggered the access (e.g., "query: find meetings")
    accessed_at TIMESTAMPTZ DEFAULT NOW()
);

-- =============================================================================
-- Indexes
-- =============================================================================

-- Episodic salience indexes
CREATE INDEX idx_episodic_salience_user ON episodic_memory_salience(user_id);
CREATE INDEX idx_episodic_salience_graphiti ON episodic_memory_salience(graphiti_episode_id);
CREATE INDEX idx_episodic_salience_value ON episodic_memory_salience(user_id, current_salience DESC);
CREATE INDEX idx_episodic_salience_accessed ON episodic_memory_salience(user_id, last_accessed_at DESC);

-- Semantic salience indexes
CREATE INDEX idx_semantic_salience_user ON semantic_fact_salience(user_id);
CREATE INDEX idx_semantic_salience_graphiti ON semantic_fact_salience(graphiti_episode_id);
CREATE INDEX idx_semantic_salience_value ON semantic_fact_salience(user_id, current_salience DESC);
CREATE INDEX idx_semantic_salience_accessed ON semantic_fact_salience(user_id, last_accessed_at DESC);

-- Access log indexes
CREATE INDEX idx_memory_access_log_memory ON memory_access_log(memory_id, memory_type);
CREATE INDEX idx_memory_access_log_user ON memory_access_log(user_id);
CREATE INDEX idx_memory_access_log_time ON memory_access_log(user_id, accessed_at DESC);

-- =============================================================================
-- Row Level Security
-- =============================================================================

ALTER TABLE episodic_memory_salience ENABLE ROW LEVEL SECURITY;
ALTER TABLE semantic_fact_salience ENABLE ROW LEVEL SECURITY;
ALTER TABLE memory_access_log ENABLE ROW LEVEL SECURITY;

-- Users can only access their own salience records
CREATE POLICY "Users can manage own episodic salience" ON episodic_memory_salience
    FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users can manage own semantic salience" ON semantic_fact_salience
    FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "Users can access own memory logs" ON memory_access_log
    FOR ALL USING (auth.uid() = user_id);

-- Service role bypass for backend operations
CREATE POLICY "Service role full access to episodic salience" ON episodic_memory_salience
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access to semantic salience" ON semantic_fact_salience
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role full access to memory logs" ON memory_access_log
    FOR ALL USING (auth.role() = 'service_role');

-- =============================================================================
-- Triggers for updated_at
-- =============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_episodic_salience_updated_at
    BEFORE UPDATE ON episodic_memory_salience
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_semantic_salience_updated_at
    BEFORE UPDATE ON semantic_fact_salience
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
