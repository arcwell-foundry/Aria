-- Battle cards for competitive intelligence
-- Part of US-410: Battle Cards Backend

CREATE TABLE battle_cards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    competitor_name TEXT NOT NULL,
    competitor_domain TEXT,
    overview TEXT,
    strengths JSONB DEFAULT '[]',
    weaknesses JSONB DEFAULT '[]',
    pricing JSONB DEFAULT '{}',
    differentiation JSONB DEFAULT '[]',
    objection_handlers JSONB DEFAULT '[]',
    recent_news JSONB DEFAULT '[]',
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    update_source TEXT DEFAULT 'manual',  -- auto, manual
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(company_id, competitor_name)
);

-- Track changes to battle cards
CREATE TABLE battle_card_changes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    battle_card_id UUID NOT NULL REFERENCES battle_cards(id) ON DELETE CASCADE,
    change_type TEXT NOT NULL,  -- strength_added, weakness_updated, news_added, etc.
    field_name TEXT NOT NULL,
    old_value JSONB,
    new_value JSONB,
    detected_at TIMESTAMPTZ DEFAULT NOW()
);

-- RLS
ALTER TABLE battle_cards ENABLE ROW LEVEL SECURITY;
ALTER TABLE battle_card_changes ENABLE ROW LEVEL SECURITY;

-- Users can view battle cards for their company
CREATE POLICY "Users can view company battle cards"
    ON battle_cards
    FOR SELECT
    USING (
        company_id IN (
            SELECT company_id FROM user_profiles WHERE id = auth.uid()
        )
    );

-- Users can manage battle cards for their company
CREATE POLICY "Users can manage company battle cards"
    ON battle_cards
    FOR ALL
    USING (
        company_id IN (
            SELECT company_id FROM user_profiles WHERE id = auth.uid()
        )
    );

-- Users can view battle card changes for their company
CREATE POLICY "Users can view battle card changes"
    ON battle_card_changes
    FOR SELECT
    USING (
        battle_card_id IN (
            SELECT id FROM battle_cards WHERE company_id IN (
                SELECT company_id FROM user_profiles WHERE id = auth.uid()
            )
        )
    );

-- Service role has full access
CREATE POLICY "Service can manage battle_cards"
    ON battle_cards
    FOR ALL
    USING (auth.role() = 'service_role');

CREATE POLICY "Service can manage battle_card_changes"
    ON battle_card_changes
    FOR ALL
    USING (auth.role() = 'service_role');

-- Indexes
CREATE INDEX idx_battle_cards_company ON battle_cards(company_id);
CREATE INDEX idx_battle_cards_competitor ON battle_cards(competitor_name);
CREATE INDEX idx_battle_card_changes_card ON battle_card_changes(battle_card_id);

-- Comments for documentation
COMMENT ON TABLE battle_cards IS 'Competitive intelligence battle cards for sales teams.';
COMMENT ON COLUMN battle_cards.update_source IS 'Source of the update: manual (user) or auto (system-generated).';
COMMENT ON TABLE battle_card_changes IS 'Audit trail of changes to battle cards for tracking modifications.';
