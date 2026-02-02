-- Migration: Create team_mappings table
-- Description: Team name and ID mappings across different APIs
-- Date: 2025-01-24

-- Create team_mappings table
CREATE TABLE IF NOT EXISTS team_mappings (
    id VARCHAR(36) PRIMARY KEY,
    nba_team_id INTEGER NOT NULL UNIQUE,
    nba_abbreviation VARCHAR(3) NOT NULL,
    nba_full_name VARCHAR(64) NOT NULL,
    nba_city VARCHAR(32) NOT NULL,
    odds_api_name VARCHAR(64),
    odds_api_key VARCHAR(32),
    alternate_names JSONB DEFAULT '[]',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_team_mappings_abbreviation ON team_mappings(nba_abbreviation);
CREATE INDEX IF NOT EXISTS idx_team_mappings_odds_key ON team_mappings(odds_api_key);

-- Add comments for documentation
COMMENT ON TABLE team_mappings IS 'Team name and ID mappings between nba_api and The Odds API';
COMMENT ON COLUMN team_mappings.nba_team_id IS 'Numeric team ID from nba_api';
COMMENT ON COLUMN team_mappings.nba_abbreviation IS '3-letter abbreviation (BOS, LAL, etc.)';
COMMENT ON COLUMN team_mappings.nba_full_name IS 'Full team name (Boston Celtics)';
COMMENT ON COLUMN team_mappings.nba_city IS 'City name (Boston, Los Angeles)';
COMMENT ON COLUMN team_mappings.odds_api_name IS 'Team name used by The Odds API';
COMMENT ON COLUMN team_mappings.odds_api_key IS 'Team identifier in The Odds API';
COMMENT ON COLUMN team_mappings.alternate_names IS 'JSONB array of alternate name variations';
