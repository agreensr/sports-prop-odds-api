-- Add nba_api_id column to players table
-- This stores the numeric ID used by the nba_api Python package
-- Separate from external_id which stores string-based IDs from other sources

-- Add the column (PostgreSQL doesn't support IF NOT EXISTS for ADD COLUMN)
-- Check if column exists first
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name='players' AND column_name='nba_api_id'
    ) THEN
        ALTER TABLE players ADD COLUMN nba_api_id INTEGER;
    END IF;
END
$$;

-- Create index for efficient lookups
CREATE INDEX IF NOT EXISTS ix_players_nba_api_id ON players(nba_api_id);

-- Add comment for documentation
COMMENT ON COLUMN players.nba_api_id IS 'Numeric ID for nba_api Python package (e.g., 1629029 for Luka Dončić)';
