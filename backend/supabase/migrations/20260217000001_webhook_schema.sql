-- ============================================================
-- Webhook Schema Migration
-- Date: 2026-02-17
-- Purpose: Add perception_analysis and shutdown_reason columns
--          to video_sessions table for Tavus webhook callbacks.
-- ============================================================


-- ============================================================
-- 1. Add perception_analysis column to video_sessions
--    Stores Raven-1 perception analysis from Tavus callbacks.
-- ============================================================
ALTER TABLE video_sessions
ADD COLUMN IF NOT EXISTS perception_analysis jsonb DEFAULT '{}';

COMMENT ON COLUMN video_sessions.perception_analysis IS
'JSONB payload from Tavus application.perception_analysis webhook containing user emotion, engagement, and attention metrics.';


-- ============================================================
-- 2. Add shutdown_reason column to video_sessions
--    Stores the reason for session termination from Tavus.
-- ============================================================
ALTER TABLE video_sessions
ADD COLUMN IF NOT EXISTS shutdown_reason text;

COMMENT ON COLUMN video_sessions.shutdown_reason IS
'Reason for session shutdown from Tavus system.shutdown webhook (e.g., "user_left", "timeout", "error").';


-- ============================================================
-- 3. Add lead_id column to video_sessions (optional)
--    Links video sessions to leads for intelligence enrichment.
-- ============================================================
ALTER TABLE video_sessions
ADD COLUMN IF NOT EXISTS lead_id uuid REFERENCES leads(id) ON DELETE SET NULL;

COMMENT ON COLUMN video_sessions.lead_id IS
'Optional reference to a lead if this video session is related to lead engagement.';


-- ============================================================
-- 4. Add index for lead_id lookups
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_video_sessions_lead_id
    ON video_sessions(lead_id);


-- ============================================================
-- 5. Add index for tavus_conversation_id lookups (webhook routing)
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_video_sessions_tavus_conversation_id
    ON video_sessions(tavus_conversation_id);
