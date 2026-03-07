-- Migration: Add product enrichment columns to battle_cards
-- Supports Exa-powered competitor product discovery and matchup analysis

-- Add competitor_products (list of discovered product names)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'battle_cards' AND column_name = 'competitor_products'
    ) THEN
        ALTER TABLE battle_cards ADD COLUMN competitor_products JSONB DEFAULT '[]';
    END IF;
END $$;

-- Add product_matchups (competitive matchup analysis)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'battle_cards' AND column_name = 'product_matchups'
    ) THEN
        ALTER TABLE battle_cards ADD COLUMN product_matchups JSONB DEFAULT '[]';
    END IF;
END $$;

-- Add last_enriched_at timestamp
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'battle_cards' AND column_name = 'last_enriched_at'
    ) THEN
        ALTER TABLE battle_cards ADD COLUMN last_enriched_at TIMESTAMPTZ;
    END IF;
END $$;

-- Add enrichment_source to track where data came from
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'battle_cards' AND column_name = 'enrichment_source'
    ) THEN
        ALTER TABLE battle_cards ADD COLUMN enrichment_source TEXT;
    END IF;
END $$;

-- Comments
COMMENT ON COLUMN battle_cards.competitor_products IS 'List of competitor product names discovered via Exa enrichment';
COMMENT ON COLUMN battle_cards.product_matchups IS 'Product-vs-product competitive matchups with positioning statements';
COMMENT ON COLUMN battle_cards.last_enriched_at IS 'Timestamp of last Exa product enrichment run';
COMMENT ON COLUMN battle_cards.enrichment_source IS 'Source of enrichment data (e.g. exa, manual)';
