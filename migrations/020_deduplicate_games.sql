-- Migration: Remove Duplicate Games
-- Purpose: Clean up duplicate games found during Phase 1 migration
-- This migration safely removes duplicate games by migrating their
-- predictions to the non-duplicate game first.

BEGIN;

-- Create a temporary table to track duplicate games
CREATE TEMP TABLE duplicate_games AS
WITH ranked_games AS (
    SELECT
        id,
        game_date,
        away_team,
        home_team,
        external_id,
        id_source,
        ROW_NUMBER() OVER (
            PARTITION BY game_date, away_team, home_team
            ORDER BY created_at ASC, id ASC
        ) AS rn
    FROM games
)
SELECT
    id AS duplicate_id,
    (SELECT id FROM ranked_games g2
     WHERE g2.game_date = g1.game_date
     AND g2.away_team = g1.away_team
     AND g2.home_team = g1.home_team
     AND g2.rn = 1) AS original_id,
    game_date,
    away_team,
    home_team
FROM ranked_games g1
WHERE rn > 1;

-- Migrate predictions from duplicate games to original games
UPDATE predictions
SET game_id = dg.original_id
FROM duplicate_games dg
WHERE predictions.game_id = dg.duplicate_id;

-- Delete duplicate games
DELETE FROM games
WHERE id IN (SELECT duplicate_id FROM duplicate_games);

-- Report what was done
DO $$
DECLARE
    duplicate_count INTEGER;
    migrated_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO duplicate_count FROM duplicate_games;
    RAISE NOTICE 'Removed % duplicate games', duplicate_count;
    RAISE NOTICE 'Their predictions were migrated to the original games';
END $$;

-- Drop temporary table
DROP TABLE duplicate_games;

COMMIT;
