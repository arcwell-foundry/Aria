-- ============================================================
-- Perception Events Migration
-- Date: 2026-02-17
-- Purpose: Add perception_events JSONB array column to
--          video_sessions and create perception_topic_stats
--          table for tracking topic-level perception analytics.
--
-- Context: Raven-1 perception tools emit individual events
--          (confusion, disengagement, attention shifts) during
--          Tavus video sessions. perception_events stores the
--          raw event array per session; perception_topic_stats
--          aggregates topic-level patterns across sessions.
--
-- Depends on: 20260212030900_video_sessions.sql (video_sessions table)
--             20260217000001_webhook_schema.sql  (perception_analysis column)
-- ============================================================


-- ============================================================
-- 1. Add perception_events JSONB array column to video_sessions
--    Stores individual Raven-1 perception events as an array.
--    Separate from perception_analysis (aggregate metrics).
-- ============================================================
ALTER TABLE video_sessions
ADD COLUMN IF NOT EXISTS perception_events jsonb DEFAULT '[]';

COMMENT ON COLUMN video_sessions.perception_events IS
'JSONB array of individual Raven-1 perception events (confusion, disengagement, attention shifts) captured during the video session. Each element contains event_type, timestamp, topic, metrics, and optional context. Distinct from perception_analysis which stores aggregate metrics.';


-- ============================================================
-- 2. Create perception_topic_stats table
--    Aggregates perception patterns per user per topic across
--    all video sessions for long-term learning.
-- ============================================================
CREATE TABLE IF NOT EXISTS perception_topic_stats (
    id                          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                     uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    topic                       text NOT NULL,
    confusion_count             int DEFAULT 0,
    disengagement_count         int DEFAULT 0,
    total_mentions              int DEFAULT 0,
    last_confused_at            timestamptz,
    last_disengaged_at          timestamptz,
    avg_engagement_when_discussed float,
    created_at                  timestamptz DEFAULT now(),
    updated_at                  timestamptz DEFAULT now(),
    UNIQUE(user_id, topic)
);


-- ============================================================
-- 3. Enable RLS on perception_topic_stats
-- ============================================================
ALTER TABLE perception_topic_stats ENABLE ROW LEVEL SECURITY;

-- Users can SELECT their own rows
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'perception_topic_stats'
        AND policyname = 'perception_topic_stats_select_own'
    ) THEN
        CREATE POLICY perception_topic_stats_select_own
            ON perception_topic_stats FOR SELECT
            TO authenticated
            USING (auth.uid() = user_id);
    END IF;
END $$;

-- Service role can do ALL operations
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies
        WHERE tablename = 'perception_topic_stats'
        AND policyname = 'perception_topic_stats_service_all'
    ) THEN
        CREATE POLICY perception_topic_stats_service_all
            ON perception_topic_stats FOR ALL
            TO service_role
            USING (true)
            WITH CHECK (true);
    END IF;
END $$;


-- ============================================================
-- 4. Indexes
-- ============================================================
-- Primary lookup: find all topic stats for a user
CREATE INDEX IF NOT EXISTS idx_perception_topic_stats_user
    ON perception_topic_stats(user_id);

-- Ranked confusion topics: find topics a user struggles with most
CREATE INDEX IF NOT EXISTS idx_perception_topic_stats_confusion
    ON perception_topic_stats(user_id, confusion_count DESC);
