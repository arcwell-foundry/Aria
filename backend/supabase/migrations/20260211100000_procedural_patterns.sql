-- Migration: Add procedural_patterns table
-- Required by: backend/src/api/routes/perception.py (Raven-0 emotion detection)
-- Part of the Memory System (procedural memory type)

CREATE TABLE IF NOT EXISTS procedural_patterns (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    pattern_type    TEXT NOT NULL,
    pattern_data    JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index for querying by user and pattern type
CREATE INDEX IF NOT EXISTS idx_procedural_patterns_user_type
    ON procedural_patterns(user_id, pattern_type);

-- Index for time-ordered queries (engagement summary)
CREATE INDEX IF NOT EXISTS idx_procedural_patterns_created
    ON procedural_patterns(user_id, created_at DESC);

-- RLS policies
ALTER TABLE procedural_patterns ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can read own procedural patterns"
    ON procedural_patterns FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert own procedural patterns"
    ON procedural_patterns FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own procedural patterns"
    ON procedural_patterns FOR UPDATE
    USING (auth.uid() = user_id);

-- updated_at trigger
CREATE OR REPLACE FUNCTION update_procedural_patterns_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER procedural_patterns_updated_at
    BEFORE UPDATE ON procedural_patterns
    FOR EACH ROW
    EXECUTE FUNCTION update_procedural_patterns_updated_at();
