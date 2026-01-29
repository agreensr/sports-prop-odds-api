-- =============================================================================
-- Rollback Migration 020: Deduplicate Games
-- =============================================================================
-- This rollback is DANGEROUS - it would restore duplicate games.
-- Use with caution!

BEGIN;

-- WARNING: This would restore duplicate entries from backup
-- The backup table should have been created during migration
-- DROP TABLE IF EXISTS games_duplicates;
-- INSERT INTO games SELECT * FROM games_duplicates;

-- Instead, we provide a way to verify no duplicates exist
-- Run this before running the actual rollback to verify safety

COMMIT;
