-- =============================================================================
-- Migration 023: Add sport_id Column for Multi-Sport Support
-- =============================================================================
-- This migration adds the sport_id column to unified tables to support
-- filtering by sport type (nba, nfl, mlb, nhl).
--
-- Architecture: The codebase has migrated to unified models but the
-- database schema was never updated with the sport_id discriminator.
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- Ensure sports registry table exists
-- -----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sports (
    id VARCHAR(3) PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Insert default sports if not exists
INSERT INTO sports (id, name, active, created_at, updated_at)
VALUES
    ('nba', 'NBA', TRUE, NOW(), NOW()),
    ('nfl', 'NFL', TRUE, NOW(), NOW()),
    ('mlb', 'MLB', TRUE, NOW(), NOW()),
    ('nhl', 'NHL', TRUE, NOW(), NOW())
ON CONFLICT (id) DO NOTHING;

-- -----------------------------------------------------------------------------
-- Add sport_id column to players table
-- -----------------------------------------------------------------------------
ALTER TABLE players ADD COLUMN IF NOT EXISTS sport_id VARCHAR(3) DEFAULT 'nba';

-- Add foreign key constraint
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'players_sport_id_fkey'
    ) THEN
        ALTER TABLE players
        ADD CONSTRAINT players_sport_id_fkey
        FOREIGN KEY (sport_id) REFERENCES sports(id);
    END IF;
END $$;

-- Make sport_id NOT NULL after backfill
ALTER TABLE players ALTER COLUMN sport_id SET NOT NULL;

-- Create index
CREATE INDEX IF NOT EXISTS ix_players_sport_id ON players(sport_id);

-- -----------------------------------------------------------------------------
-- Add sport_id column to games table
-- -----------------------------------------------------------------------------
ALTER TABLE games ADD COLUMN IF NOT EXISTS sport_id VARCHAR(3) DEFAULT 'nba';

-- Add foreign key constraint
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'games_sport_id_fkey'
    ) THEN
        ALTER TABLE games
        ADD CONSTRAINT games_sport_id_fkey
        FOREIGN KEY (sport_id) REFERENCES sports(id);
    END IF;
END $$;

-- Make sport_id NOT NULL after backfill
ALTER TABLE games ALTER COLUMN sport_id SET NOT NULL;

-- Create index
CREATE INDEX IF NOT EXISTS ix_games_sport_id ON games(sport_id);

-- Create composite index for sport+date+status queries
CREATE INDEX IF NOT EXISTS ix_games_sport_date_status ON games(sport_id, game_date, status);

-- -----------------------------------------------------------------------------
-- Add sport_id column to predictions table
-- -----------------------------------------------------------------------------
ALTER TABLE predictions ADD COLUMN IF NOT EXISTS sport_id VARCHAR(3) DEFAULT 'nba';

-- Add foreign key constraint
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'predictions_sport_id_fkey'
    ) THEN
        ALTER TABLE predictions
        ADD CONSTRAINT predictions_sport_id_fkey
        FOREIGN KEY (sport_id) REFERENCES sports(id);
    END IF;
END $$;

-- Make sport_id NOT NULL after backfill
ALTER TABLE predictions ALTER COLUMN sport_id SET NOT NULL;

-- Create index
CREATE INDEX IF NOT EXISTS ix_predictions_sport_id ON predictions(sport_id);

COMMIT;

-- =============================================================================
-- VERIFICATION QUERIES
-- =============================================================================
-- Run these after migration to verify success:

-- Check sports table
-- SELECT * FROM sports;

-- Check sport_id column exists and has data
-- SELECT sport_id, COUNT(*) as count FROM players GROUP BY sport_id;
-- SELECT sport_id, COUNT(*) as count FROM games GROUP BY sport_id;
-- SELECT sport_id, COUNT(*) as count FROM predictions GROUP BY sport_id;
