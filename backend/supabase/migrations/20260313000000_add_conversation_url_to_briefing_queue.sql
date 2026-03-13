-- Add conversation_url column to memory_briefing_queue
-- This stores the Tavus video conversation URL when video briefing is delivered

ALTER TABLE memory_briefing_queue
ADD COLUMN IF NOT EXISTS conversation_url TEXT;

-- Add index for querying by conversation_url
CREATE INDEX IF NOT EXISTS idx_memory_briefing_queue_conversation_url
    ON memory_briefing_queue(user_id, conversation_url) WHERE conversation_url IS NOT NULL;
