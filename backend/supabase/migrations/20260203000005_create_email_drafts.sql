-- Email drafts table for US-408: Email Drafting Backend
-- Stores email drafts created by ARIA with Digital Twin style matching
-- Supports tracking of draft status, sending via Composio, and lead association

-- Create enum types for email metadata (idempotent)
DO $$ BEGIN
    CREATE TYPE email_purpose AS ENUM (
        'intro',
        'follow_up',
        'proposal',
        'thank_you',
        'check_in',
        'other'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE email_tone AS ENUM (
        'formal',
        'friendly',
        'urgent'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE email_draft_status AS ENUM (
        'draft',
        'sent',
        'failed'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Main email drafts table
CREATE TABLE email_drafts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
    recipient_email TEXT NOT NULL,
    recipient_name TEXT,
    subject TEXT NOT NULL,
    body TEXT NOT NULL,
    purpose email_purpose NOT NULL,
    tone email_tone DEFAULT 'friendly',
    context JSONB DEFAULT '{}',
    lead_memory_id UUID REFERENCES lead_memories(id) ON DELETE SET NULL,
    style_match_score FLOAT CHECK (style_match_score >= 0 AND style_match_score <= 1),
    status email_draft_status DEFAULT 'draft',
    sent_at TIMESTAMPTZ,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Add table comment
COMMENT ON TABLE email_drafts IS 'Stores email drafts created by ARIA with Digital Twin style matching. Tracks draft lifecycle from creation through sending via Composio integration.';

-- Create indexes for efficient querying
CREATE INDEX idx_email_drafts_user_id ON email_drafts(user_id);
CREATE INDEX idx_email_drafts_status ON email_drafts(status);
CREATE INDEX idx_email_drafts_lead_memory_id ON email_drafts(lead_memory_id);
CREATE INDEX idx_email_drafts_created_at ON email_drafts(created_at DESC);

-- Enable Row Level Security
ALTER TABLE email_drafts ENABLE ROW LEVEL SECURITY;

-- RLS Policies for user isolation (multi-tenant)
CREATE POLICY "Users can view their own drafts" ON email_drafts
    FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "Users can create their own drafts" ON email_drafts
    FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update their own drafts" ON email_drafts
    FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can delete their own drafts" ON email_drafts
    FOR DELETE USING (auth.uid() = user_id);

-- Create updated_at trigger function specific to email_drafts
CREATE OR REPLACE FUNCTION update_email_drafts_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply updated_at trigger
CREATE TRIGGER update_email_drafts_updated_at
    BEFORE UPDATE ON email_drafts
    FOR EACH ROW EXECUTE FUNCTION update_email_drafts_updated_at();
