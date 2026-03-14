-- Add lead processing columns to market_signals for signal-to-lead pipeline
-- processed_for_leads_at: tracks when SignalLeadTrigger evaluated this signal
-- lead_relevance_score: buying-signal relevance score (0.0-1.0) from trigger scoring

ALTER TABLE market_signals
  ADD COLUMN IF NOT EXISTS processed_for_leads_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS lead_relevance_score FLOAT;

-- Index for finding unprocessed signals efficiently (used by signal_lead_trigger)
CREATE INDEX IF NOT EXISTS idx_market_signals_unprocessed
  ON market_signals (user_id, detected_at DESC)
  WHERE processed_for_leads_at IS NULL;
