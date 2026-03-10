-- Migration: Create aria_knowledge table for ARIA self-knowledge
-- Stores identity, agents, capabilities, integrations, and constraints
-- seeded from backend/src/core/aria_capabilities.yaml at startup

CREATE TABLE IF NOT EXISTS aria_knowledge (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    category text NOT NULL,
    name text NOT NULL,
    description text NOT NULL,
    metadata jsonb DEFAULT '{}',
    updated_at timestamptz DEFAULT NOW(),
    UNIQUE(category, name)
);

-- Disable RLS — this is non-user data, read by the service role only
ALTER TABLE aria_knowledge DISABLE ROW LEVEL SECURITY;

COMMENT ON TABLE aria_knowledge IS 'ARIA self-knowledge seeded from aria_capabilities.yaml — queried for deck generation and chat system prompt';
