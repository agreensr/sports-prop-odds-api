-- Migration 015: Drop top_50_players table
-- The Top 50 system has been removed in favor of using all active players
-- with injury filtering. This table is no longer needed.

-- Drop the table and all dependent records (CASCADE handles foreign keys)
DROP TABLE IF EXISTS top_50_players CASCADE;

-- Verify table dropped (should return 0 rows)
-- SELECT * FROM information_schema.tables WHERE table_name = 'top_50_players';
