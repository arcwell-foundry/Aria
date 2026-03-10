-- Migration: Add pptx_url column to decks table for ARIA-owned PPTX storage
-- Created: 2026-03-10

ALTER TABLE decks ADD COLUMN IF NOT EXISTS pptx_url TEXT;

COMMENT ON COLUMN decks.pptx_url IS 'Signed URL to ARIA-owned PPTX file in Supabase Storage';
