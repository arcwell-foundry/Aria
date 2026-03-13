-- Add search_trigger_company column to market_signals
-- Preserves the original search entity name that triggered the Exa search,
-- separate from company_name which now reflects the actual article subject.
ALTER TABLE market_signals ADD COLUMN IF NOT EXISTS search_trigger_company TEXT;

-- Backfill: set search_trigger_company = company_name for existing rows
-- (since they were all set to the search trigger before this fix)
UPDATE market_signals
SET search_trigger_company = company_name
WHERE search_trigger_company IS NULL;
