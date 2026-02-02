-- Migration: Create Games with Natural Key Unique Constraint
-- Purpose: Prevent duplicate games with natural key constraint
-- Phase: 1 - Data Integrity Foundation

-- First, add sport_id to existing games table (for backward compatibility)
ALTER TABLE games ADD COLUMN IF NOT EXISTS sport_id VARCHAR(3) DEFAULT 'nba';

-- Add foreign key constraint to sports table
ALTER TABLE games DROP CONSTRAINT IF EXISTS games_sport_id_fkey;
ALTER TABLE games ADD CONSTRAINT games_sport_id_fkey
    FOREIGN KEY (sport_id) REFERENCES sports(id);

-- Add multi-source ID columns to games table
ALTER TABLE games ADD COLUMN IF NOT EXISTS odds_api_event_id VARCHAR(100);
ALTER TABLE games ADD COLUMN IF NOT EXISTS espn_game_id INTEGER;

-- Create unique indexes for multi-source IDs
CREATE UNIQUE INDEX IF NOT EXISTS uq_game_odds_api ON games(sport_id, odds_api_event_id)
    WHERE odds_api_event_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_game_espn ON games(sport_id, espn_game_id)
    WHERE espn_game_id IS NOT NULL;

-- Create NATURAL KEY unique constraint to prevent duplicates
-- This is the KEY constraint that prevents duplicate games
CREATE UNIQUE INDEX IF NOT EXISTS uq_game_natural ON games(sport_id, game_date, away_team, home_team);

-- Add indexes for multi-source ID lookups
CREATE INDEX IF NOT EXISTS ix_games_odds_api_event_id ON games(odds_api_event_id);
CREATE INDEX IF NOT EXISTS ix_games_espn_game_id ON games(espn_game_id);
CREATE INDEX IF NOT EXISTS ix_games_sport_id ON games(sport_id);

-- Add composite index for common queries
CREATE INDEX IF NOT EXISTS ix_games_sport_date_status ON games(sport_id, game_date, status);

-- Comment the table for documentation
COMMENT ON TABLE games IS 'Game registry with multi-source ID support and natural key duplicate prevention';
COMMENT ON COLUMN games.sport_id IS 'Foreign key to sports table (nba, nfl, mlb, nhl)';
COMMENT ON COLUMN games.odds_api_event_id IS 'Event ID from The Odds API';
COMMENT ON COLUMN games.espn_game_id IS 'Game ID from ESPN API';
COMMENT ON INDEX uq_game_natural IS 'Natural key constraint to prevent duplicate games across all sources';
