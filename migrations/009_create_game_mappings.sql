-- Migration: Create game_mappings table
-- Description: Maps nba_api games to The Odds API events for data correlation
-- Date: 2025-01-24

-- Create game_mappings table
CREATE TABLE IF NOT EXISTS game_mappings (
    id VARCHAR(36) PRIMARY KEY,
    nba_game_id VARCHAR(20) NOT NULL,
    nba_home_team_id INTEGER NOT NULL,
    nba_away_team_id INTEGER NOT NULL,
    odds_event_id VARCHAR(64),
    odds_sport_key VARCHAR(32) DEFAULT 'basketball_nba',
    game_date DATE NOT NULL,
    game_time TIMESTAMP WITH TIME ZONE,
    match_confidence DECIMAL(5,4) NOT NULL,
    match_method VARCHAR(32) NOT NULL,
    status VARCHAR(16) DEFAULT 'pending',
    last_validated_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    UNIQUE(nba_game_id),
    UNIQUE(odds_event_id)
);

-- Create indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_game_mappings_date ON game_mappings(game_date);
CREATE INDEX IF NOT EXISTS idx_game_mappings_status ON game_mappings(status);
CREATE INDEX IF NOT EXISTS idx_game_mappings_confidence ON game_mappings(match_confidence);
CREATE INDEX IF NOT EXISTS idx_game_mappings_nba_id ON game_mappings(nba_game_id);

-- Add comments for documentation
COMMENT ON TABLE game_mappings IS 'Maps nba_api game IDs to The Odds API event IDs for data correlation';
COMMENT ON COLUMN game_mappings.nba_game_id IS 'Game ID from nba_api (e.g., 0022400001)';
COMMENT ON COLUMN game_mappings.odds_event_id IS 'Event ID from The Odds API';
COMMENT ON COLUMN game_mappings.match_confidence IS 'Confidence score 0.0-1.0 for the match quality';
COMMENT ON COLUMN game_mappings.match_method IS 'How the match was made: exact, fuzzy_time, fuzzy_team_name';
COMMENT ON COLUMN game_mappings.status IS 'pending, matched, failed, or manual_review';
COMMENT ON COLUMN game_mappings.last_validated_at IS 'Last time this mapping was verified';
