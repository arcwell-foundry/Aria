-- Migration: Create companion_mistake_acknowledgments table and add missing updated_at triggers
-- Addresses: 4A (missing table) and 4B (missing triggers)

-- ============================================================
-- 4A: companion_mistake_acknowledgments table
-- Used by: backend/src/companion/self_reflection.py:901
-- ============================================================

CREATE TABLE IF NOT EXISTS companion_mistake_acknowledgments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    mistake_description TEXT NOT NULL,
    acknowledgment TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_companion_mistakes_user
    ON companion_mistake_acknowledgments(user_id);

-- RLS: users can only see their own mistake acknowledgments
ALTER TABLE companion_mistake_acknowledgments ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'companion_mistake_acknowledgments'
          AND policyname = 'Users can view own mistake acknowledgments'
    ) THEN
        CREATE POLICY "Users can view own mistake acknowledgments"
            ON companion_mistake_acknowledgments FOR SELECT
            USING (auth.uid() = user_id);
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'companion_mistake_acknowledgments'
          AND policyname = 'Users can insert own mistake acknowledgments'
    ) THEN
        CREATE POLICY "Users can insert own mistake acknowledgments"
            ON companion_mistake_acknowledgments FOR INSERT
            WITH CHECK (auth.uid() = user_id);
    END IF;
END $$;

-- Service role bypass for backend inserts
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'companion_mistake_acknowledgments'
          AND policyname = 'Service role full access to mistake acknowledgments'
    ) THEN
        CREATE POLICY "Service role full access to mistake acknowledgments"
            ON companion_mistake_acknowledgments FOR ALL
            USING (auth.role() = 'service_role');
    END IF;
END $$;

-- ============================================================
-- 4B: Missing updated_at triggers
-- The update_updated_at_column() function already exists
-- (defined in 20260211000000_missing_tables_comprehensive.sql)
-- ============================================================

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.triggers
        WHERE trigger_name = 'set_updated_at_lead_memories'
          AND event_object_table = 'lead_memories'
    ) THEN
        CREATE TRIGGER set_updated_at_lead_memories
            BEFORE UPDATE ON lead_memories
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.triggers
        WHERE trigger_name = 'set_updated_at_company_documents'
          AND event_object_table = 'company_documents'
    ) THEN
        CREATE TRIGGER set_updated_at_company_documents
            BEFORE UPDATE ON company_documents
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.triggers
        WHERE trigger_name = 'set_updated_at_discovered_leads'
          AND event_object_table = 'discovered_leads'
    ) THEN
        CREATE TRIGGER set_updated_at_discovered_leads
            BEFORE UPDATE ON discovered_leads
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.triggers
        WHERE trigger_name = 'set_updated_at_proactive_proposals'
          AND event_object_table = 'proactive_proposals'
    ) THEN
        CREATE TRIGGER set_updated_at_proactive_proposals
            BEFORE UPDATE ON proactive_proposals
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.triggers
        WHERE trigger_name = 'set_updated_at_strategic_plans'
          AND event_object_table = 'strategic_plans'
    ) THEN
        CREATE TRIGGER set_updated_at_strategic_plans
            BEFORE UPDATE ON strategic_plans
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;
