-- Email scan log urgency consistency trigger
-- Defense-in-depth: Auto-correct category-urgency contradictions at the database level
-- This catches any cases where the application-level validation might be bypassed

-- Create trigger function to enforce category-urgency consistency
CREATE OR REPLACE FUNCTION enforce_email_urgency_consistency()
RETURNS TRIGGER AS $$
BEGIN
    -- Rule 1: SKIP emails cannot be urgent (not actionable = lowest priority)
    IF NEW.category = 'SKIP' AND NEW.urgency != 'LOW' THEN
        NEW.urgency := 'LOW';
    END IF;

    -- Rule 2: NEEDS_REPLY emails cannot be LOW (needs response = at least normal)
    IF NEW.category = 'NEEDS_REPLY' AND NEW.urgency = 'LOW' THEN
        NEW.urgency := 'NORMAL';
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION enforce_email_urgency_consistency() IS
'Defense-in-depth trigger that auto-corrects category-urgency contradictions. SKIP must be LOW urgency, NEEDS_REPLY must be at least NORMAL urgency.';

-- Create the trigger (drop if exists for idempotency)
DROP TRIGGER IF EXISTS trg_email_scan_log_urgency_consistency ON email_scan_log;
CREATE TRIGGER trg_email_scan_log_urgency_consistency
    BEFORE INSERT OR UPDATE ON email_scan_log
    FOR EACH ROW
    EXECUTE FUNCTION enforce_email_urgency_consistency();

-- Backfill existing contradictory data
-- Fix 1: SKIP emails with non-LOW urgency
UPDATE email_scan_log
SET urgency = 'LOW'
WHERE category = 'SKIP' AND urgency IN ('URGENT', 'NORMAL');

-- Fix 2: NEEDS_REPLY emails with LOW urgency
UPDATE email_scan_log
SET urgency = 'NORMAL'
WHERE category = 'NEEDS_REPLY' AND urgency = 'LOW';
