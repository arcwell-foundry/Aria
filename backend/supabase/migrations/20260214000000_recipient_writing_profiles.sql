-- ============================================================
-- recipient_writing_profiles
-- Per-recipient writing style profiles for Digital Twin.
-- Stores how a user adapts writing style per contact.
-- ============================================================
CREATE TABLE IF NOT EXISTS recipient_writing_profiles (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    recipient_email         TEXT NOT NULL,
    recipient_name          TEXT,
    relationship_type       TEXT DEFAULT 'unknown'
                            CHECK (relationship_type IN (
                                'internal_team', 'external_executive', 'external_peer',
                                'vendor', 'new_contact', 'unknown'
                            )),
    formality_level         FLOAT DEFAULT 0.5,
    average_message_length  INTEGER DEFAULT 0,
    greeting_style          TEXT DEFAULT '',
    signoff_style           TEXT DEFAULT '',
    tone                    TEXT DEFAULT 'balanced'
                            CHECK (tone IN ('warm', 'direct', 'formal', 'casual', 'balanced')),
    uses_emoji              BOOLEAN DEFAULT FALSE,
    email_count             INTEGER DEFAULT 0,
    last_email_date         TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, recipient_email)
);

ALTER TABLE recipient_writing_profiles ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'recipient_writing_profiles'
        AND policyname = 'recipient_writing_profiles_user_own'
    ) THEN
        CREATE POLICY recipient_writing_profiles_user_own
            ON recipient_writing_profiles FOR ALL TO authenticated
            USING (user_id = auth.uid());
    END IF;
END $$;

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'recipient_writing_profiles'
        AND policyname = 'recipient_writing_profiles_service_role'
    ) THEN
        CREATE POLICY recipient_writing_profiles_service_role
            ON recipient_writing_profiles FOR ALL TO service_role
            USING (true);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_recipient_writing_profiles_user
    ON recipient_writing_profiles(user_id);

CREATE INDEX IF NOT EXISTS idx_recipient_writing_profiles_user_recipient
    ON recipient_writing_profiles(user_id, recipient_email);

DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'update_recipient_writing_profiles_updated_at'
    ) THEN
        CREATE TRIGGER update_recipient_writing_profiles_updated_at
            BEFORE UPDATE ON recipient_writing_profiles
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;
