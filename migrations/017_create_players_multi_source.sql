-- Migration: Create Players with Multi-Source ID Support
-- Purpose: Track players across all APIs with dedicated columns per source
-- Phase: 1 - Data Integrity Foundation

-- First, add sport_id to existing players table (for backward compatibility)
ALTER TABLE players ADD COLUMN IF NOT EXISTS sport_id VARCHAR(3) DEFAULT 'nba';

-- Add foreign key constraint to sports table
ALTER TABLE players DROP CONSTRAINT IF EXISTS players_sport_id_fkey;
ALTER TABLE players ADD CONSTRAINT players_sport_id_fkey
    FOREIGN KEY (sport_id) REFERENCES sports(id);

-- Add the missing multi-source ID columns to existing players table
ALTER TABLE players ADD COLUMN IF NOT EXISTS odds_api_id VARCHAR(100);
ALTER TABLE players ADD COLUMN IF NOT EXISTS espn_id INTEGER;
ALTER TABLE players add COLUMN IF NOT EXISTS nfl_id INTEGER;
ALTER TABLE players ADD COLUMN IF NOT EXISTS mlb_id INTEGER;
ALTER TABLE players ADD COLUMN IF NOT EXISTS nhl_id INTEGER;

-- Rename external_id to odds_api_id if it contains odds API data
-- (This is a data migration step - run manually after review)
-- UPDATE players SET odds_api_id = external_id WHERE id_source = 'odds_api';

-- Add canonical_name column for standardized naming
ALTER TABLE players ADD COLUMN IF NOT EXISTS canonical_name VARCHAR(255);

-- Populate canonical_name from existing name if null
UPDATE players SET canonical_name = name WHERE canonical_name IS NULL;

-- Add unique constraints per API source (prevents duplicates)
CREATE UNIQUE INDEX IF NOT EXISTS uq_player_odds_api ON players(sport_id, odds_api_id)
    WHERE odds_api_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_player_nba_api ON players(sport_id, nba_api_id)
    WHERE nba_api_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_player_espn ON players(sport_id, espn_id)
    WHERE espn_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_player_nfl ON players(sport_id, nfl_id)
    WHERE nfl_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_player_mlb ON players(sport_id, mlb_id)
    WHERE mlb_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_player_nhl ON players(sport_id, nhl_id)
    WHERE nhl_id IS NOT NULL;

-- Make canonical_name NOT NULL after data migration
-- ALTER TABLE players ALTER COLUMN canonical_name SET NOT NULL;

-- Add index for canonical name lookups
CREATE INDEX IF NOT EXISTS ix_players_canonical_name ON players(canonical_name);
CREATE INDEX IF NOT EXISTS ix_players_sport_id ON players(sport_id);

-- Comment the table for documentation
COMMENT ON TABLE players IS 'Player registry with multi-source ID support across all sports';
COMMENT ON COLUMN players.sport_id IS 'Foreign key to sports table (nba, nfl, mlb, nhl)';
COMMENT ON COLUMN players.odds_api_id IS 'Player ID from The Odds API';
COMMENT ON COLUMN players.nba_api_id IS 'Player ID from NBA.com API';
COMMENT ON COLUMN players.espn_id IS 'Player ID from ESPN API';
COMMENT ON COLUMN players.nfl_id IS 'Player ID from NFL API';
COMMENT ON COLUMN players.mlb_id IS 'Player ID from MLB API';
COMMENT ON COLUMN players.nhl_id IS 'Player ID from NHL API';
COMMENT ON COLUMN players.canonical_name IS 'Standardized player name across all sources';
