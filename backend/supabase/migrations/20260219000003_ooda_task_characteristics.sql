-- Add computed risk score and task characteristics to action queue
-- Both nullable to preserve backward compatibility with existing rows

ALTER TABLE aria_action_queue
    ADD COLUMN IF NOT EXISTS risk_score FLOAT,
    ADD COLUMN IF NOT EXISTS task_characteristics JSONB;

CREATE INDEX IF NOT EXISTS idx_aria_action_queue_risk_score
    ON aria_action_queue(risk_score) WHERE risk_score IS NOT NULL;
