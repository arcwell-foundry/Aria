-- Migration: Add priority labeling to jarvis_insights and signal linking to market_signals
-- Supports insight priority computation and signal-to-insight traceability

-- Add priority_label to jarvis_insights
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'jarvis_insights' AND column_name = 'priority_label'
    ) THEN
        ALTER TABLE jarvis_insights ADD COLUMN priority_label TEXT;
        ALTER TABLE jarvis_insights ADD CONSTRAINT chk_jarvis_priority_label
            CHECK (priority_label IN ('critical', 'high', 'medium', 'low'));
    END IF;
END $$;

-- Add linked_insight_id to market_signals for signal-to-insight traceability
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'market_signals' AND column_name = 'linked_insight_id'
    ) THEN
        ALTER TABLE market_signals ADD COLUMN linked_insight_id UUID;
    END IF;
END $$;

-- Add linked_action_summary to market_signals
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'market_signals' AND column_name = 'linked_action_summary'
    ) THEN
        ALTER TABLE market_signals ADD COLUMN linked_action_summary TEXT;
    END IF;
END $$;

-- Index for filtering insights by priority
CREATE INDEX IF NOT EXISTS idx_jarvis_insights_priority_label ON jarvis_insights(priority_label);

-- Index for looking up signals linked to insights
CREATE INDEX IF NOT EXISTS idx_market_signals_linked_insight ON market_signals(linked_insight_id)
    WHERE linked_insight_id IS NOT NULL;

-- Comments
COMMENT ON COLUMN jarvis_insights.priority_label IS 'Computed priority: critical, high, medium, low — based on confidence and classification';
COMMENT ON COLUMN market_signals.linked_insight_id IS 'ID of the jarvis_insight derived from this signal';
COMMENT ON COLUMN market_signals.linked_action_summary IS 'Summary of the recommended action from the linked insight';
