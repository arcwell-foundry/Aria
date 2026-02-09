-- supabase/migrations/20260206000000_create_team_invites.sql
-- US-927: Team & Company Administration - Team Invites and User Management

-- Add is_active column to user_profiles for soft deactivation
ALTER TABLE user_profiles ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true;

-- Create team_invites table
CREATE TABLE IF NOT EXISTS team_invites (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID REFERENCES companies(id) ON DELETE CASCADE NOT NULL,
    invited_by UUID REFERENCES auth.users(id) NOT NULL,
    email TEXT NOT NULL,
    role TEXT DEFAULT 'user' CHECK (role IN ('user', 'manager', 'admin')),
    token TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'cancelled', 'expired')),
    expires_at TIMESTAMPTZ DEFAULT (NOW() + INTERVAL '7 days'),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for invite token lookup
CREATE INDEX IF NOT EXISTS idx_invite_token ON team_invites(token);

-- Index for company invites listing
CREATE INDEX IF NOT EXISTS idx_invites_company ON team_invites(company_id, created_at DESC);

-- Enable Row Level Security
ALTER TABLE team_invites ENABLE ROW LEVEL SECURITY;

-- RLS Policy: Admins can see all invites for their company
CREATE POLICY "admins_view_invites" ON team_invites
    FOR SELECT TO authenticated
    USING (
        company_id IN (
            SELECT company_id FROM user_profiles
            WHERE id = auth.uid() AND role = 'admin'
        )
    );

-- RLS Policy: Managers can view invites for their company
CREATE POLICY "managers_view_invites" ON team_invites
    FOR SELECT TO authenticated
    USING (
        company_id IN (
            SELECT company_id FROM user_profiles
            WHERE id = auth.uid() AND role IN ('admin', 'manager')
        )
    );

-- RLS Policy: Any user can create invites (open with escalation policy)
CREATE POLICY "users_create_invites" ON team_invites
    FOR INSERT TO authenticated
    WITH CHECK (
        company_id IN (
            SELECT company_id FROM user_profiles
            WHERE id = auth.uid()
        )
    );

-- RLS Policy: Admins can update invites (cancel, resend)
CREATE POLICY "admins_update_invites" ON team_invites
    FOR UPDATE TO authenticated
    USING (
        company_id IN (
            SELECT company_id FROM user_profiles
            WHERE id = auth.uid() AND role = 'admin'
        )
    );

-- Service role bypass for backend operations
CREATE POLICY "service_role_full_access_team_invites" ON team_invites
    FOR ALL USING (auth.role() = 'service_role');
