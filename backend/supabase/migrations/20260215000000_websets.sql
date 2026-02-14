-- Phase 3: Websets Integration for Bulk Lead Generation
-- Table for tracking Exa Webset jobs for asynchronous lead discovery

-- Webset Jobs: Track async bulk lead discovery jobs
CREATE TABLE webset_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    webset_id TEXT UNIQUE NOT NULL,  -- Exa Webset ID
    user_id UUID REFERENCES auth.users(id) NOT NULL,
    goal_id UUID,  -- Optional link to ooda_goals or goals table
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    entity_type TEXT NOT NULL CHECK (entity_type IN ('company', 'person')),
    search_query TEXT NOT NULL,
    items_imported INTEGER DEFAULT 0,
    error_message TEXT,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for common queries
CREATE INDEX idx_webset_jobs_user ON webset_jobs(user_id);
CREATE INDEX idx_webset_jobs_status ON webset_jobs(status);
CREATE INDEX idx_webset_jobs_webset_id ON webset_jobs(webset_id);
CREATE INDEX idx_webset_jobs_goal ON webset_jobs(goal_id) WHERE goal_id IS NOT NULL;

-- RLS Policies
ALTER TABLE webset_jobs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view their own webset jobs" ON webset_jobs
    FOR SELECT TO authenticated USING (user_id = auth.uid());

CREATE POLICY "Users can insert their own webset jobs" ON webset_jobs
    FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());

CREATE POLICY "Service role can manage all webset jobs" ON webset_jobs
    FOR ALL TO service_role USING (true) WITH CHECK (true);

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_webset_jobs_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER webset_jobs_updated_at
    BEFORE UPDATE ON webset_jobs
    FOR EACH ROW
    EXECUTE FUNCTION update_webset_jobs_updated_at();

-- Add source column to discovered_leads for tracking webset origin
ALTER TABLE discovered_leads
ADD COLUMN IF NOT EXISTS webset_job_id UUID REFERENCES webset_jobs(id);

CREATE INDEX IF NOT EXISTS idx_discovered_leads_webset_job
ON discovered_leads(webset_job_id) WHERE webset_job_id IS NOT NULL;
