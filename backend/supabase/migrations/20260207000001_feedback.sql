-- ============================================================================
-- Feedback Table Migration for US-933: Content & Help System
-- ============================================================================
-- This table captures user feedback for content, help articles, and general
-- system feedback. Supports thumbs up/down ratings with optional comments.
-- ============================================================================

-- Create feedback table
CREATE TABLE IF NOT EXISTS public.feedback (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- User reference
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,

    -- Feedback type with constraint
    type TEXT NOT NULL CHECK (type IN ('response', 'bug', 'feature', 'other')),

    -- Thumbs up/down rating (nullable)
    rating TEXT CHECK (rating IN ('up', 'down')),

    -- Optional message reference (for response feedback) - TEXT for any message ID format
    message_id TEXT,

    -- Optional comment text
    comment TEXT,

    -- Page/context where feedback was given
    page TEXT,

    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Add comment for table documentation
COMMENT ON TABLE public.feedback IS 'User feedback for content, help articles, and system feedback';

-- Create indexes for performance
CREATE INDEX idx_feedback_user_created ON public.feedback(user_id, created_at DESC);
CREATE INDEX idx_feedback_type ON public.feedback(type, created_at DESC);
CREATE INDEX idx_feedback_message ON public.feedback(message_id) WHERE message_id IS NOT NULL;

-- Add column comments
COMMENT ON COLUMN public.feedback.id IS 'Unique identifier for the feedback entry';
COMMENT ON COLUMN public.feedback.user_id IS 'Reference to the user who provided feedback';
COMMENT ON COLUMN public.feedback.type IS 'Type of feedback: response, bug, feature, or other';
COMMENT ON COLUMN public.feedback.rating IS 'Thumbs up or down rating';
COMMENT ON COLUMN public.feedback.message_id IS 'Optional reference to the message being rated (text format)';
COMMENT ON COLUMN public.feedback.comment IS 'Optional free-text comment from user';
COMMENT ON COLUMN public.feedback.page IS 'Page or context where feedback was submitted';

-- ============================================================================
-- Row Level Security (RLS) Policies
-- ============================================================================

-- Enable RLS
ALTER TABLE public.feedback ENABLE ROW LEVEL SECURITY;

-- Policy: Users can read their own feedback
CREATE POLICY "Users can read own feedback"
ON public.feedback
FOR SELECT
USING (auth.uid() = user_id);

-- Policy: Users can insert their own feedback
CREATE POLICY "Users can insert own feedback"
ON public.feedback
FOR INSERT
WITH CHECK (auth.uid() = user_id);

-- Policy: Service role has full access (for admin/analysis)
CREATE POLICY "Service role full access"
ON public.feedback
FOR ALL
USING (auth.role() = 'service_role')
WITH CHECK (auth.role() = 'service_role');

-- ============================================================================
-- Grant Permissions
-- ============================================================================

-- Grant select, insert on table (using UUID, no sequence needed)
GRANT SELECT, INSERT ON public.feedback TO authenticated;
