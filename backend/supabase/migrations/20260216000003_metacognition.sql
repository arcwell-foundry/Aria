-- Migration: Metacognition Module (US-803)
-- Creates table for caching knowledge assessments

-- Knowledge assessment cache
-- Stores ARIA's self-assessed knowledge confidence on topics
CREATE TABLE IF NOT EXISTS metacognition_assessments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    topic TEXT NOT NULL,
    confidence FLOAT NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    knowledge_source TEXT NOT NULL CHECK (knowledge_source IN ('memory', 'inference', 'uncertain', 'external')),
    last_updated TIMESTAMTZ NOT NULL DEFAULT NOW(),
    reliability_notes TEXT,
    should_research BOOLEAN NOT NULL DEFAULT FALSE,
    fact_count INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- One assessment per user per topic
    UNIQUE(user_id, topic)
);

-- Enable Row Level Security
ALTER TABLE metacognition_assessments ENABLE ROW LEVEL SECURITY;

-- RLS Policies for metacognition_assessments
CREATE POLICY "Users can view their own assessments"
    ON metacognition_assessments FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can insert their own assessments"
    ON metacognition_assessments FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own assessments"
    ON metacognition_assessments FOR UPDATE
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_metacognition_user
    ON metacognition_assessments(user_id);

CREATE INDEX IF NOT EXISTS idx_metacognition_topic
    ON metacognition_assessments(user_id, topic);

CREATE INDEX IF NOT EXISTS idx_metacognition_research
    ON metacognition_assessments(user_id, should_research)
    WHERE should_research = TRUE;

-- Comments
COMMENT ON TABLE metacognition_assessments IS 'Caches ARIA self-assessed knowledge confidence on topics';
COMMENT ON COLUMN metacognition_assessments.confidence IS '0.0-1.0 confidence level in knowledge about the topic';
COMMENT ON COLUMN metacognition_assessments.knowledge_source IS 'Source of knowledge: memory, inference, uncertain, or external';
COMMENT ON COLUMN metacognition_assessments.should_research IS 'True if confidence is below research threshold (0.5)';
COMMENT ON COLUMN metacognition_assessments.fact_count IS 'Number of relevant facts found in memory';
