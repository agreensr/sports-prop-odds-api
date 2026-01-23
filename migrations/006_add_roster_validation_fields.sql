-- Add roster validation tracking fields to players table
-- These fields track when a player's roster data was last validated
-- and where the data came from (improves data freshness)

ALTER TABLE players
ADD COLUMN IF NOT EXISTS last_roster_check TIMESTAMP,
ADD COLUMN IF NOT EXISTS data_source VARCHAR(50);

-- Add comment for documentation
COMMENT ON COLUMN players.last_roster_check IS 'Last time this player''s team assignment was validated against nba_api';
COMMENT ON COLUMN players.data_source IS 'Source of player data: nba_api, espn, manual, nba_api_auto, etc.';

-- Create index for players needing validation (checked more than 24h ago)
CREATE INDEX IF NOT EXISTS ix_players_last_roster_check ON players(last_roster_check)
WHERE last_roster_check < NOW() - INTERVAL '24 hours';

-- Add index for data source filtering
CREATE INDEX IF NOT EXISTS ix_players_data_source ON players(data_source);
