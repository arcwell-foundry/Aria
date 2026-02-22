-- Add formatting_patterns column to digital_twin_profiles
-- Stores structural formatting preferences extracted from user's sent emails
-- (paragraph count, bullet usage, signature block, etc.)
-- Used by the autonomous draft engine to generate HTML drafts that match
-- the user's natural email formatting style.

ALTER TABLE digital_twin_profiles
ADD COLUMN IF NOT EXISTS formatting_patterns JSONB DEFAULT '{}';

COMMENT ON COLUMN digital_twin_profiles.formatting_patterns IS
    'Structural formatting patterns extracted from sent emails (paragraph count, bullet usage, signature, etc.)';
