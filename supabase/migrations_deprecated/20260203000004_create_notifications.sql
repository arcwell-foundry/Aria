-- ============================================
-- US-415: Notification System
-- ============================================
-- Creates notifications table with RLS policies, indexes, and notification preferences

-- Notifications table
CREATE TABLE IF NOT EXISTS notifications (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('briefing_ready', 'signal_detected', 'task_due', 'meeting_brief_ready', 'draft_ready')),
    title TEXT NOT NULL,
    message TEXT,
    link TEXT,
    metadata JSONB DEFAULT '{}',
    read_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW() NOT NULL
);

-- Add table comment
COMMENT ON TABLE notifications IS 'Stores in-app notifications for users with support for multiple notification types';

-- Index for unread notifications query (partial index for efficiency)
CREATE INDEX IF NOT EXISTS idx_notifications_user_unread ON notifications(user_id, created_at DESC) WHERE read_at IS NULL;

-- Index for user notifications list (full table scan support)
CREATE INDEX IF NOT EXISTS idx_notifications_user_created ON notifications(user_id, created_at DESC);

-- Index for notification type filtering
CREATE INDEX IF NOT EXISTS idx_notifications_user_type ON notifications(user_id, type, created_at DESC);

-- =============================================================================
-- Row Level Security
-- =============================================================================

ALTER TABLE notifications ENABLE ROW LEVEL SECURITY;

-- Users can read their own notifications
CREATE POLICY "Users can read own notifications"
    ON notifications FOR SELECT
    USING (auth.uid() = user_id);

-- Users can insert their own notifications (for system operations)
CREATE POLICY "Users can insert own notifications"
    ON notifications FOR INSERT
    WITH CHECK (auth.uid() = user_id);

-- Users can update their own notifications (mark read)
CREATE POLICY "Users can update own notifications"
    ON notifications FOR UPDATE
    USING (auth.uid() = user_id);

-- Users can delete their own notifications
CREATE POLICY "Users can delete own notifications"
    ON notifications FOR DELETE
    USING (auth.uid() = user_id);

-- Service role can insert notifications (for background jobs)
CREATE POLICY "Service role can insert notifications"
    ON notifications FOR INSERT
    TO service_role
    WITH CHECK (true);

-- Service role bypass for all operations
CREATE POLICY "Service role full access to notifications"
    ON notifications FOR ALL
    USING (auth.role() = 'service_role');

-- =============================================================================
-- Notification Preferences in user_settings
-- =============================================================================

-- Add notification preferences column to user_settings
ALTER TABLE user_settings
    ADD COLUMN IF NOT EXISTS notification_preferences JSONB DEFAULT '{
        "in_app_enabled": true,
        "email_enabled": false,
        "briefing_ready": true,
        "signal_detected": true,
        "task_due": true,
        "meeting_brief_ready": true,
        "draft_ready": true
    }'::jsonb;

-- Add column comment
COMMENT ON COLUMN user_settings.notification_preferences IS 'User notification preferences for each notification type';
