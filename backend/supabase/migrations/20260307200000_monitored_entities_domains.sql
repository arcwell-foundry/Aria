-- Add domains column to monitored_entities for sender relationship resolution
-- This enables dynamic identification of strategic contacts based on sender email domain

ALTER TABLE monitored_entities
ADD COLUMN IF NOT EXISTS domains text[] DEFAULT '{}';

-- Add GIN index for efficient array containment queries
CREATE INDEX IF NOT EXISTS idx_monitored_entities_domains
ON monitored_entities USING GIN (domains);

-- Add comment for documentation
COMMENT ON COLUMN monitored_entities.domains IS 'Array of domain names associated with this entity (e.g., [''cytiva.com'', ''ge.com'']) for matching sender emails';

-- Seed .406 Ventures for the test user if not exists
INSERT INTO monitored_entities (user_id, entity_type, entity_name, domains, is_active, monitoring_config)
SELECT
    '41475700-c1fb-4f66-8c56-77bd90b73abb',
    'investor',
    '.406 Ventures',
    ARRAY['406ventures.com'],
    true,
    '{"source": "relationship_seed", "track_news": true}'::jsonb
WHERE NOT EXISTS (
    SELECT 1 FROM monitored_entities
    WHERE user_id = '41475700-c1fb-4f66-8c56-77bd90b73abb'
    AND entity_name ILIKE '%406%'
);
