-- Migration: Add signal deduplication columns to market_signals
-- Supports clustering near-duplicate signals into groups

-- Add cluster_id to group related signals
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'market_signals' AND column_name = 'cluster_id'
    ) THEN
        ALTER TABLE market_signals ADD COLUMN cluster_id UUID;
    END IF;
END $$;

-- Add is_cluster_primary to mark the representative signal in each cluster
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'market_signals' AND column_name = 'is_cluster_primary'
    ) THEN
        ALTER TABLE market_signals ADD COLUMN is_cluster_primary BOOLEAN DEFAULT FALSE;
    END IF;
END $$;

-- Index for filtering by cluster
CREATE INDEX IF NOT EXISTS idx_market_signals_cluster_id ON market_signals(cluster_id)
    WHERE cluster_id IS NOT NULL;

-- Index for quickly finding primary signals
CREATE INDEX IF NOT EXISTS idx_market_signals_cluster_primary ON market_signals(is_cluster_primary)
    WHERE is_cluster_primary = TRUE;

-- Comments
COMMENT ON COLUMN market_signals.cluster_id IS 'UUID grouping near-duplicate signals about the same event';
COMMENT ON COLUMN market_signals.is_cluster_primary IS 'True if this is the representative signal in its cluster (longest headline)';
