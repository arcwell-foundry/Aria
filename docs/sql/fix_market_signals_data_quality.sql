-- ============================================================================
-- FIX: Market Signals Data Quality Issues
-- Date: 2026-03-06
-- Purpose: Fix people stored as companies, normalize company names, deduplicate
-- ============================================================================

-- ============================================================================
-- PART A1: Fix company_name for people (should be their company)
-- ============================================================================

-- Fix Olivier Loeillot -> Repligen (8 signals)
UPDATE market_signals
SET company_name = 'Repligen'
WHERE company_name = 'Olivier Loeillot';

-- Fix Tony J. Hunt -> Repligen (2 signals)
UPDATE market_signals
SET company_name = 'Repligen'
WHERE company_name = 'Tony J. Hunt';

-- ============================================================================
-- PART A2: Normalize company name variants to canonical form
-- ============================================================================

-- Repligen Corporation -> Repligen (3 signals)
UPDATE market_signals
SET company_name = 'Repligen'
WHERE company_name = 'Repligen Corporation';

-- Pall Danaher -> Pall Corporation (15 signals)
-- This matches the battle_cards canonical name
UPDATE market_signals
SET company_name = 'Pall Corporation'
WHERE company_name = 'Pall Danaher';

-- Thermo Fisher Scientific -> Thermo Fisher (21 signals)
-- battle_cards uses "Thermo Fisher" as canonical
UPDATE market_signals
SET company_name = 'Thermo Fisher'
WHERE company_name = 'Thermo Fisher Scientific';

-- ============================================================================
-- PART A3: Fix truncated headline
-- ============================================================================

-- Fix "Tony J." -> "Tony J. Hunt — Former Repligen CEO"
UPDATE market_signals
SET headline = 'Tony J. Hunt — Former Repligen CEO'
WHERE headline = 'Tony J.';

-- ============================================================================
-- PART A4: Deduplicate signals
-- Keep the earliest detected_at for each (company_name, headline) pair
-- ============================================================================

-- First, see how many duplicates we have
SELECT
    company_name,
    headline,
    COUNT(*) as duplicate_count
FROM market_signals
GROUP BY company_name, headline
HAVING COUNT(*) > 1
ORDER BY duplicate_count DESC;

-- Delete duplicates, keeping the earliest detected_at
DELETE FROM market_signals
WHERE id IN (
    SELECT id FROM (
        SELECT
            id,
            ROW_NUMBER() OVER (
                PARTITION BY company_name, headline
                ORDER BY detected_at ASC
            ) as row_num
        FROM market_signals
    ) AS duplicates
    WHERE row_num > 1
);

-- ============================================================================
-- VERIFICATION QUERIES
-- Run these after the fixes to confirm success
-- ============================================================================

-- Verify no more people-as-companies
SELECT company_name, COUNT(*) as cnt
FROM market_signals
WHERE company_name IN ('Olivier Loeillot', 'Tony J. Hunt')
GROUP BY company_name;
-- Expected: 0 rows

-- Verify no more variant company names
SELECT company_name, COUNT(*) as cnt
FROM market_signals
WHERE company_name IN ('Repligen Corporation', 'Pall Danaher', 'Thermo Fisher Scientific')
GROUP BY company_name;
-- Expected: 0 rows

-- Verify canonical names exist
SELECT company_name, COUNT(*) as cnt
FROM market_signals
WHERE company_name IN ('Repligen', 'Pall Corporation', 'Thermo Fisher')
GROUP BY company_name
ORDER BY cnt DESC;
-- Expected: Should show counts for these canonical names

-- Verify no duplicate headlines per company
SELECT headline, COUNT(*) as cnt
FROM market_signals
GROUP BY headline
HAVING COUNT(*) > 1;
-- Expected: 0 rows (or very few if legitimate same-headline different-company)

-- Full company distribution
SELECT company_name, COUNT(*) as cnt
FROM market_signals
GROUP BY company_name
ORDER BY cnt DESC
LIMIT 20;
