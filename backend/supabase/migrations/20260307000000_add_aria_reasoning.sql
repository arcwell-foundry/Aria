-- Add aria_reasoning column to email_drafts for LLM-generated strategic reasoning
ALTER TABLE email_drafts ADD COLUMN IF NOT EXISTS aria_reasoning TEXT;

-- Add aria_reasoning column to aria_action_queue for proposal reasoning
ALTER TABLE aria_action_queue ADD COLUMN IF NOT EXISTS aria_reasoning TEXT;

-- Add aria_reasoning column to proactive_proposals
ALTER TABLE proactive_proposals ADD COLUMN IF NOT EXISTS aria_reasoning TEXT;
