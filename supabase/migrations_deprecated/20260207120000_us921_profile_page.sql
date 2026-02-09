-- US-921: Profile Page - Add profile detail columns and document tables
-- Extends user_profiles, companies for full profile management

-- Add user detail columns to user_profiles
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS full_name TEXT;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS title TEXT;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS department TEXT;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS linkedin_url TEXT;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS avatar_url TEXT;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS communication_preferences JSONB DEFAULT '{}'::jsonb;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS privacy_exclusions JSONB DEFAULT '[]'::jsonb;
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS default_tone TEXT DEFAULT 'friendly';
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS tracked_competitors TEXT[] DEFAULT '{}';

-- Add company detail columns to companies
ALTER TABLE companies ADD COLUMN IF NOT EXISTS website TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS industry TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS sub_vertical TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS description TEXT;
ALTER TABLE companies ADD COLUMN IF NOT EXISTS key_products TEXT[] DEFAULT '{}';

-- Company documents table (shared across company users)
CREATE TABLE IF NOT EXISTS company_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    uploaded_by UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    content_type TEXT,
    file_size BIGINT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_company_documents_company ON company_documents(company_id);
CREATE INDEX IF NOT EXISTS idx_company_documents_uploader ON company_documents(uploaded_by);

ALTER TABLE company_documents ENABLE ROW LEVEL SECURITY;

-- All company members can read company documents
CREATE POLICY "Company members can read company documents"
    ON company_documents FOR SELECT
    USING (
        company_id IN (
            SELECT company_id FROM user_profiles WHERE id = auth.uid()
        )
    );

-- Only uploader can delete their own documents
CREATE POLICY "Uploader can delete own documents"
    ON company_documents FOR DELETE
    USING (uploaded_by = auth.uid());

-- Service role full access
CREATE POLICY "Service can manage company documents"
    ON company_documents FOR ALL
    USING (auth.role() = 'service_role');

-- User documents table (private writing samples)
CREATE TABLE IF NOT EXISTS user_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    file_path TEXT NOT NULL,
    content_type TEXT,
    file_size BIGINT,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_user_documents_user ON user_documents(user_id);

ALTER TABLE user_documents ENABLE ROW LEVEL SECURITY;

-- Users can only access their own documents
CREATE POLICY "Users can manage own documents"
    ON user_documents FOR ALL
    USING (user_id = auth.uid());

-- Service role full access
CREATE POLICY "Service can manage user documents"
    ON user_documents FOR ALL
    USING (auth.role() = 'service_role');

COMMENT ON TABLE company_documents IS 'Shared company documents uploaded during onboarding or profile management';
COMMENT ON TABLE user_documents IS 'Private user documents (writing samples) for Digital Twin calibration';
