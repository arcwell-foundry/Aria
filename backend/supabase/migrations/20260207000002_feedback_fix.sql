-- ============================================================================
-- Feedback Table Migration Fix for US-933
-- ============================================================================
-- This migration fixes the following spec compliance issues:
-- 1. user_id: ON DELETE SET NULL -> ON DELETE CASCADE, NOT NULL
-- 2. message_id: UUID -> TEXT
-- 3. Remove unique constraint on (user_id, message_id)
-- 4. Remove anonymous feedback support
-- 5. Make rating nullable
-- 6. Use auth.role() instead of auth.jwt()->>'role'
-- ============================================================================

-- Drop existing policies
DROP POLICY IF EXISTS "Users can read own feedback" ON public.feedback;
DROP POLICY IF EXISTS "Users can insert own feedback" ON public.feedback;
DROP POLICY IF EXISTS "Service role full access" ON public.feedback;

-- Drop existing grants
REVOKE SELECT, INSERT ON public.feedback FROM authenticated;
REVOKE SELECT, INSERT ON public.feedback FROM anon;

-- Drop the unique constraint
ALTER TABLE public.feedback DROP CONSTRAINT IF EXISTS unique_user_message_feedback;

-- Drop existing indexes
DROP INDEX IF EXISTS public.idx_feedback_user_created;
DROP INDEX IF EXISTS public.idx_feedback_type;
DROP INDEX IF EXISTS public.idx_feedback_message;

-- Alter message_id from UUID to TEXT
ALTER TABLE public.feedback ALTER COLUMN message_id TYPE TEXT USING message_id::TEXT;

-- Make user_id NOT NULL and change ON DELETE to CASCADE
ALTER TABLE public.feedback ALTER COLUMN user_id SET NOT NULL;
ALTER TABLE public.feedback DROP CONSTRAINT feedback_user_id_fkey;
ALTER TABLE public.feedback ADD CONSTRAINT feedback_user_id_fkey
    FOREIGN KEY (user_id) REFERENCES auth.users(id) ON DELETE CASCADE;

-- Make rating nullable
ALTER TABLE public.feedback ALTER COLUMN rating DROP NOT NULL;

-- Recreate indexes for performance
CREATE INDEX idx_feedback_user_created ON public.feedback(user_id, created_at DESC);
CREATE INDEX idx_feedback_type ON public.feedback(type);
CREATE INDEX idx_feedback_message ON public.feedback(message_id) WHERE message_id IS NOT NULL;

-- Update column comments
COMMENT ON COLUMN public.feedback.user_id IS 'Reference to the user who provided feedback';
COMMENT ON COLUMN public.feedback.message_id IS 'Optional reference to the message being rated (text format)';
COMMENT ON COLUMN public.feedback.rating IS 'Thumbs up or down rating (nullable)';

-- Recreate RLS policies
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

-- Grant permissions (no anon role)
GRANT SELECT, INSERT ON public.feedback TO authenticated;
