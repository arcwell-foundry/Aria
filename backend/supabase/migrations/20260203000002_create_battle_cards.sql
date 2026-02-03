-- Battle cards tables for US-410: Battle Cards Backend
-- Stores competitive intelligence cards and tracks changes over time
-- Supports company-scoped storage with change history

-- Main battle_cards table
CREATE TABLE battle_cards (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE,
    competitor_name TEXT NOT NULL,
    competitor_domain TEXT,
    overview TEXT,
    strengths JSONB DEFAULT '[]',
    weaknesses JSONB DEFAULT '[]',
    pricing JSONB DEFAULT '{}',
    differentiation JSONB DEFAULT '[]',
    objection_handlers JSONB DEFAULT '[]',
    update_source TEXT DEFAULT 'manual',
    last_updated TIMESTAMPTZ DEFAULT NOW(),
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    UNIQUE(company_id, competitor_name)
);

-- Add table comment
COMMENT ON TABLE battle_cards IS 'Stores competitive intelligence cards for sales teams. One card per competitor per company.';

-- Battle card change history table
CREATE TABLE battle_card_changes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    battle_card_id UUID REFERENCES battle_cards(id) ON DELETE CASCADE NOT NULL,
    change_type TEXT NOT NULL,
    field_name TEXT,
    old_value JSONB,
    new_value JSONB,
    detected_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Add table comment
COMMENT ON TABLE battle_card_changes IS 'Tracks all changes to battle cards for audit and history purposes.';

-- Create indexes for battle_cards
CREATE INDEX idx_battle_cards_company_id ON battle_cards(company_id);
CREATE INDEX idx_battle_cards_competitor_name ON battle_cards(competitor_name);
CREATE INDEX idx_battle_cards_last_updated ON battle_cards(last_updated DESC);

-- Create indexes for battle_card_changes
CREATE INDEX idx_battle_card_changes_card_id ON battle_card_changes(battle_card_id);
CREATE INDEX idx_battle_card_changes_detected_at ON battle_card_changes(detected_at DESC);

-- Enable Row Level Security
ALTER TABLE battle_cards ENABLE ROW LEVEL SECURITY;
ALTER TABLE battle_card_changes ENABLE ROW LEVEL SECURITY;

-- RLS Policies for battle_cards (company-scoped via user_profiles)
CREATE POLICY "Users can view battle cards for their company" ON battle_cards
    FOR SELECT USING (
        company_id IN (
            SELECT company_id FROM user_profiles WHERE id = auth.uid()
        )
    );

CREATE POLICY "Users can create battle cards for their company" ON battle_cards
    FOR INSERT WITH CHECK (
        company_id IN (
            SELECT company_id FROM user_profiles WHERE id = auth.uid()
        )
    );

CREATE POLICY "Users can update battle cards for their company" ON battle_cards
    FOR UPDATE USING (
        company_id IN (
            SELECT company_id FROM user_profiles WHERE id = auth.uid()
        )
    );

CREATE POLICY "Users can delete battle cards for their company" ON battle_cards
    FOR DELETE USING (
        company_id IN (
            SELECT company_id FROM user_profiles WHERE id = auth.uid()
        )
    );

-- RLS Policies for battle_card_changes (via battle_cards relationship)
CREATE POLICY "Users can view changes for their company battle cards" ON battle_card_changes
    FOR SELECT USING (
        battle_card_id IN (
            SELECT bc.id FROM battle_cards bc
            JOIN user_profiles up ON bc.company_id = up.company_id
            WHERE up.id = auth.uid()
        )
    );

CREATE POLICY "Users can create changes for their company battle cards" ON battle_card_changes
    FOR INSERT WITH CHECK (
        battle_card_id IN (
            SELECT bc.id FROM battle_cards bc
            JOIN user_profiles up ON bc.company_id = up.company_id
            WHERE up.id = auth.uid()
        )
    );

-- Service role bypass policies (for backend operations)
CREATE POLICY "Service role can manage battle_cards" ON battle_cards
    FOR ALL USING (auth.role() = 'service_role');

CREATE POLICY "Service role can manage battle_card_changes" ON battle_card_changes
    FOR ALL USING (auth.role() = 'service_role');
