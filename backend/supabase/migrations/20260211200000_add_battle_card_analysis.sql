-- Add analysis JSONB column to battle_cards for competitive metrics, strategies, feature gaps, and critical gaps
-- This replaces hardcoded mock data in the frontend with real API-sourced data

ALTER TABLE battle_cards
ADD COLUMN IF NOT EXISTS analysis JSONB DEFAULT '{}';

COMMENT ON COLUMN battle_cards.analysis IS 'JSONB containing competitive analysis data: metrics (win_rate, market_cap_gap, pricing_delta, last_signal_at), strategies, feature_gaps, and critical_gaps';
