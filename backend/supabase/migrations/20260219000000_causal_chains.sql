-- ============================================================
-- ARIA: Causal Chains Table for Phase 7 Jarvis Intelligence
-- Date: 2026-02-19
-- Purpose: Store causal chain analysis results for tracing
--          how events propagate through connected entities.
-- ============================================================

-- Helper: ensure updated_at trigger function exists
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;


-- ============================================================
-- causal_chains - Create table if not exists, then add missing columns
-- ============================================================

-- Create table with minimal schema if it doesn't exist
CREATE TABLE IF NOT EXISTS causal_chains (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    trigger_event   TEXT NOT NULL,
    hops            JSONB NOT NULL DEFAULT '[]'::jsonb,
    final_confidence FLOAT NOT NULL CHECK (final_confidence >= 0 AND final_confidence <= 1),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Add columns if they don't exist (idempotent)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'causal_chains' AND column_name = 'time_to_impact') THEN
        ALTER TABLE causal_chains ADD COLUMN time_to_impact TEXT;
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'causal_chains' AND column_name = 'source_context') THEN
        ALTER TABLE causal_chains ADD COLUMN source_context TEXT;
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'causal_chains' AND column_name = 'source_id') THEN
        ALTER TABLE causal_chains ADD COLUMN source_id UUID;
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'causal_chains' AND column_name = 'invalidated_at') THEN
        ALTER TABLE causal_chains ADD COLUMN invalidated_at TIMESTAMPTZ;
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name = 'causal_chains' AND column_name = 'updated_at') THEN
        ALTER TABLE causal_chains ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
    END IF;
END $$;

-- Enable RLS
ALTER TABLE causal_chains ENABLE ROW LEVEL SECURITY;

-- Policies (create if not exists)
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'causal_chains' AND policyname = 'causal_chains_user_own') THEN
        CREATE POLICY causal_chains_user_own ON causal_chains FOR ALL TO authenticated USING (user_id = auth.uid());
    END IF;
END $$;

DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_policies WHERE tablename = 'causal_chains' AND policyname = 'causal_chains_service_role') THEN
        CREATE POLICY causal_chains_service_role ON causal_chains FOR ALL TO service_role USING (true);
    END IF;
END $$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_causal_chains_user ON causal_chains(user_id);
CREATE INDEX IF NOT EXISTS idx_causal_chains_created ON causal_chains(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_causal_chains_user_created ON causal_chains(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_causal_chains_source ON causal_chains(user_id, source_context);
CREATE INDEX IF NOT EXISTS idx_causal_chains_active ON causal_chains(user_id, created_at DESC) WHERE invalidated_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_causal_chains_hops ON causal_chains USING GIN (hops jsonb_path_ops);

-- Trigger for updated_at
DROP TRIGGER IF EXISTS update_causal_chains_updated_at ON causal_chains;
CREATE TRIGGER update_causal_chains_updated_at
    BEFORE UPDATE ON causal_chains
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
