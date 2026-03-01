-- Performance Indexes Migration for ARIA
-- Creates indexes to optimize frequently queried columns
--
-- Indexes created:
-- 1. messages: (conversation_id, created_at) - for conversation message retrieval
-- 2. aria_activity: (user_id, created_at DESC) - for activity feed queries
-- 3. lead_memory_events: (lead_memory_id, occurred_at DESC) - for lead timeline
-- 4. email_drafts: (user_id, created_at DESC) - for email draft listing

-- =============================================================================
-- Messages Index
-- =============================================================================
-- Optimizes: Conversation message retrieval with chronological ordering
-- Used by: Chat/conversation endpoints, message history queries
CREATE INDEX IF NOT EXISTS idx_messages_conversation_created
ON messages (conversation_id, created_at);

-- =============================================================================
-- ARIA Activity Index
-- =============================================================================
-- Optimizes: Activity feed queries filtered by user with recent-first ordering
-- Used by: ActivityService.get_feed(), dashboard activity widgets
CREATE INDEX IF NOT EXISTS idx_aria_activity_user_created_desc
ON aria_activity (user_id, created_at DESC);

-- =============================================================================
-- Lead Memory Events Index
-- =============================================================================
-- Optimizes: Lead timeline queries with event ordering
-- Used by: Lead event retrieval, engagement tracking
CREATE INDEX IF NOT EXISTS idx_lead_memory_events_lead_occurred_desc
ON lead_memory_events (lead_memory_id, occurred_at DESC);

-- =============================================================================
-- Email Drafts Index
-- =============================================================================
-- Optimizes: Email draft listing queries filtered by user with recent-first
-- Used by: Email draft endpoints, draft review interfaces
CREATE INDEX IF NOT EXISTS idx_email_drafts_user_created_desc
ON email_drafts (user_id, created_at DESC);

-- =============================================================================
-- Additional Performance Indexes
-- =============================================================================
-- These indexes support common query patterns identified in analytics service

-- Lead memories: user_id + status (for active lead queries)
CREATE INDEX IF NOT EXISTS idx_lead_memories_user_status
ON lead_memories (user_id, status);

-- Lead memories: user_id + health_score (for hot leads queries)
CREATE INDEX IF NOT EXISTS idx_lead_memories_user_health
ON lead_memories (user_id, health_score DESC)
WHERE status = 'active';

-- Market signals: user_id + dismissed_at (for unread signals)
CREATE INDEX IF NOT EXISTS idx_market_signals_user_undismissed
ON market_signals (user_id, detected_at DESC)
WHERE dismissed_at IS NULL;

-- Calendar events: user_id + created_at (for meeting queries)
CREATE INDEX IF NOT EXISTS idx_calendar_events_user_created
ON calendar_events (user_id, created_at);

-- Goals: user_id + status (for active goals)
CREATE INDEX IF NOT EXISTS idx_goals_user_status
ON goals (user_id, status);

-- Comment documenting the migration
COMMENT ON SCHEMA public IS 'Performance indexes added 2026-02-17 for caching optimization task';
