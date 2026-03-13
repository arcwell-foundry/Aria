-- Migration: Apollo pricing configuration and encrypted API key support
-- Created: 2026-03-12
-- Purpose: Add vendor_api_pricing for configurable credit costs, and encryption support for BYOK API keys

-- ============================================================================
-- 1. Create vendor_api_pricing table (reusable for any vendor)
-- ============================================================================

CREATE TABLE IF NOT EXISTS vendor_api_pricing (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    vendor TEXT NOT NULL,
    action TEXT NOT NULL,
    credits_per_call INTEGER DEFAULT 0,
    cost_cents_per_credit NUMERIC(10, 4) DEFAULT 0,
    description TEXT,
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(vendor, action)
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_vendor_api_pricing_vendor_action
    ON vendor_api_pricing(vendor, action);

-- ============================================================================
-- 2. Seed Apollo pricing (based on late 2025 credit system)
-- ============================================================================

INSERT INTO vendor_api_pricing (vendor, action, credits_per_call, cost_cents_per_credit, description)
VALUES
    ('apollo', 'people_search', 0, 0, 'Search for people by company/title - FREE'),
    ('apollo', 'people_enrich_email', 1, 3.5, 'Reveal work/personal email - 1 credit'),
    ('apollo', 'people_enrich_phone', 8, 3.5, 'Reveal email + phone - 8 credits (1 base + 7 phone)'),
    ('apollo', 'org_enrich', 1, 3.5, 'Company data enrichment - 1 credit'),
    ('apollo', 'job_postings', 0, 0, 'Job postings lookup - FREE'),
    ('apollo', 'bulk_people_enrich', 1, 3.5, 'Bulk person enrichment - 1 credit per person'),
    ('apollo', 'bulk_org_enrich', 1, 3.5, 'Bulk org enrichment - 1 credit per org')
ON CONFLICT (vendor, action) DO UPDATE SET
    credits_per_call = EXCLUDED.credits_per_call,
    cost_cents_per_credit = EXCLUDED.cost_cents_per_credit,
    description = EXCLUDED.description,
    updated_at = NOW();

-- ============================================================================
-- 3. Add encryption columns to apollo_config (if not exists)
-- ============================================================================

-- Add encrypted_api_key column for BYOK mode (application-level encryption)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'apollo_config' AND column_name = 'encrypted_api_key'
    ) THEN
        ALTER TABLE apollo_config ADD COLUMN encrypted_api_key TEXT;
    END IF;
END $$;

-- Add encryption_key_version for key rotation support
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'apollo_config' AND column_name = 'encryption_key_version'
    ) THEN
        ALTER TABLE apollo_config ADD COLUMN encryption_key_version INTEGER DEFAULT 1;
    END IF;
END $$;

-- ============================================================================
-- 4. Add cost tracking to apollo_credit_log (if not exists)
-- ============================================================================

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'apollo_credit_log' AND column_name = 'cost_cents'
    ) THEN
        ALTER TABLE apollo_credit_log ADD COLUMN cost_cents NUMERIC(10, 4) DEFAULT 0;
    END IF;
END $$;

-- Add pricing_snapshot for audit (stores pricing at time of call)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'apollo_credit_log' AND column_name = 'pricing_snapshot'
    ) THEN
        ALTER TABLE apollo_credit_log ADD COLUMN pricing_snapshot JSONB DEFAULT '{}';
    END IF;
END $$;

-- ============================================================================
-- 5. Create function to get current pricing
-- ============================================================================

CREATE OR REPLACE FUNCTION get_apollo_pricing(p_action TEXT)
RETURNS TABLE (
    credits_per_call INTEGER,
    cost_cents_per_credit NUMERIC
) AS $$
BEGIN
    RETURN QUERY
    SELECT vap.credits_per_call, vap.cost_cents_per_credit
    FROM vendor_api_pricing vap
    WHERE vap.vendor = 'apollo'
      AND vap.action = p_action
      AND vap.is_active = true;
END;
$$ LANGUAGE plpgsql STABLE SECURITY DEFINER;

-- ============================================================================
-- 6. Comments for documentation
-- ============================================================================

COMMENT ON TABLE vendor_api_pricing IS 'Configurable pricing for external API vendors. Credit costs can be updated without code deploys.';
COMMENT ON TABLE apollo_config IS 'Per-company Apollo.io configuration with dual-mode support (BYOK vs LuminOne-provided credits)';
COMMENT ON TABLE apollo_credit_log IS 'Audit log of all Apollo API calls with credit consumption and cost tracking';
COMMENT ON COLUMN apollo_config.encrypted_api_key IS 'BYOK API key encrypted with application master key (Fernet)';
COMMENT ON COLUMN apollo_credit_log.cost_cents IS 'Actual cost in cents based on cost_cents_per_credit * credits_consumed';
