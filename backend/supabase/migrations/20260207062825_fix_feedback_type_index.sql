-- ============================================================================
-- Fix Feedback Type Index - Add created_at DESC
-- ============================================================================
-- This migration fixes the idx_feedback_type index to include created_at DESC
-- for better query performance when sorting by timestamp.
-- ============================================================================

-- Drop the old index
DROP INDEX IF EXISTS public.idx_feedback_type;

-- Recreate with created_at DESC
CREATE INDEX idx_feedback_type ON public.feedback(type, created_at DESC);
