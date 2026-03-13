-- Migration: Add settings columns to apollo_config for UI preferences
-- Created: 2026-03-13

-- Add auto-enrich preference
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'apollo_config' AND column_name = 'auto_enrich_on_approval'
    ) THEN
        ALTER TABLE apollo_config ADD COLUMN auto_enrich_on_approval BOOLEAN DEFAULT false;
    END IF;
END $$;

-- Add default reveal emails preference
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'apollo_config' AND column_name = 'default_reveal_emails'
    ) THEN
        ALTER TABLE apollo_config ADD COLUMN default_reveal_emails BOOLEAN DEFAULT true;
    END IF;
END $$;

-- Add default reveal phones preference
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'apollo_config' AND column_name = 'default_reveal_phones'
    ) THEN
        ALTER TABLE apollo_config ADD COLUMN default_reveal_phones BOOLEAN DEFAULT false;
    END IF;
END $$;

COMMENT ON COLUMN apollo_config.auto_enrich_on_approval IS 'Automatically enrich contacts when leads are approved';
COMMENT ON COLUMN apollo_config.default_reveal_emails IS 'Default to revealing email addresses during enrichment';
COMMENT ON COLUMN apollo_config.default_reveal_phones IS 'Default to revealing phone numbers during enrichment (8x credit cost)';
