-- Add context_sources column to draft_context table
-- This stores conversational descriptions of context used for drafting
-- Example: ["your last 3 emails with Sarah", "your upcoming meeting with Sarah on Thursday"]

ALTER TABLE draft_context
ADD COLUMN IF NOT EXISTS context_sources TEXT[] DEFAULT '{}';

-- Add comment for documentation
COMMENT ON COLUMN draft_context.context_sources IS
    'Conversational descriptions of context sources used for drafting (for frontend display). Example: ["your last 3 emails with Sarah", "your upcoming meeting on Thursday"]';
