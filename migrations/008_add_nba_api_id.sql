-- Add nba_api_id column to players table
-- This stores the numeric ID used by the nba_api Python package
-- Separate from external_id which stores string-based IDs from other sources

-- Add the column
ALTER TABLE players ADD COLUMN IF NOT EXISTS nba_api_id INTEGER;

-- Create index for efficient lookups
CREATE INDEX IF NOT EXISTS ix_players_nba_api_id ON players(nba_api_id);

-- Add comment for documentation
COMMENT ON COLUMN players.nba_api_id IS 'Numeric ID for nba_api Python package (e.g., 1629029 for Luka Dončić)';
