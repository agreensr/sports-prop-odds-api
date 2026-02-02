-- Migration: Create player_aliases table
-- Description: Canonical player name mappings across different data sources
-- Date: 2025-01-24

-- Create player_aliases table
CREATE TABLE IF NOT EXISTS player_aliases (
    id VARCHAR(36) PRIMARY KEY,
    nba_player_id INTEGER NOT NULL,
    canonical_name VARCHAR(128) NOT NULL,
    alias_name VARCHAR(128) NOT NULL,
    alias_source VARCHAR(32) NOT NULL,
    match_confidence DECIMAL(5,4) NOT NULL,
    is_verified BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    verified_by VARCHAR(64),
    verified_at TIMESTAMP WITH TIME ZONE,
    UNIQUE(alias_name, alias_source)
);

-- Create indexes for efficient lookups
CREATE INDEX IF NOT EXISTS idx_player_aliases_canonical ON player_aliases(canonical_name);
CREATE INDEX IF NOT EXISTS idx_player_aliases_alias ON player_aliases(alias_name);
CREATE INDEX IF NOT EXISTS idx_player_aliases_nba_id ON player_aliases(nba_player_id);
CREATE INDEX IF NOT EXISTS idx_player_aliases_source ON player_aliases(alias_source);
CREATE INDEX IF NOT EXISTS idx_player_aliases_verified ON player_aliases(is_verified);

-- Add comments for documentation
COMMENT ON TABLE player_aliases IS 'Canonical player name mappings across data sources (nba_api, odds_api, espn)';
COMMENT ON COLUMN player_aliases.nba_player_id IS 'Canonical nba_api player ID';
COMMENT ON COLUMN player_aliases.canonical_name IS 'Official player name from nba_api';
COMMENT ON COLUMN player_aliases.alias_name IS 'Alternate name from other sources';
COMMENT ON COLUMN player_aliases.alias_source IS 'Source of alias: nba_api, odds_api, espn, etc.';
COMMENT ON COLUMN player_aliases.match_confidence IS 'Confidence 0.0-1.0 that alias is correct';
COMMENT ON COLUMN player_aliases.is_verified IS 'TRUE if manually verified by a human';
