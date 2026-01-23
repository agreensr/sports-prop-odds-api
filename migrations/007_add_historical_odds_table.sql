-- Migration: Add Historical Odds Snapshots Table
-- Purpose: Track historical bookmaker odds and calculate hit rates
--          for player prop predictions to improve confidence weighting

-- Create historical_odds_snapshots table
CREATE TABLE IF NOT EXISTS historical_odds_snapshots (
    id VARCHAR(36) PRIMARY KEY,
    game_id VARCHAR(36) NOT NULL,
    player_id VARCHAR(36) NOT NULL,
    stat_type VARCHAR(50) NOT NULL,
    bookmaker_name VARCHAR(100) NOT NULL,
    bookmaker_line FLOAT NOT NULL,
    over_price FLOAT,
    under_price FLOAT,
    snapshot_time TIMESTAMP NOT NULL,
    was_starter BOOLEAN DEFAULT FALSE NOT NULL,
    actual_value FLOAT,
    hit_result VARCHAR(10),
    resolved_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

-- Create indexes for efficient queries
CREATE INDEX IF NOT EXISTS ix_historical_odds_snapshots_game_id ON historical_odds_snapshots(game_id);
CREATE INDEX IF NOT EXISTS ix_historical_odds_snapshots_player_id ON historical_odds_snapshots(player_id);
CREATE INDEX IF NOT EXISTS ix_historical_odds_snapshots_stat_type ON historical_odds_snapshots(stat_type);
CREATE INDEX IF NOT EXISTS ix_historical_odds_snapshots_bookmaker_name ON historical_odds_snapshots(bookmaker_name);
CREATE INDEX IF NOT EXISTS ix_historical_odds_snapshots_snapshot_time ON historical_odds_snapshots(snapshot_time);
CREATE INDEX IF NOT EXISTS ix_historical_odds_snapshots_was_starter ON historical_odds_snapshots(was_starter);
CREATE INDEX IF NOT EXISTS ix_historical_odds_snapshots_hit_result ON historical_odds_snapshots(hit_result);
CREATE INDEX IF NOT EXISTS ix_historical_odds_snapshots_resolved_at ON historical_odds_snapshots(resolved_at);

-- Composite index for player stat lookup (most common query pattern)
CREATE INDEX IF NOT EXISTS ix_historical_odds_player_stat ON historical_odds_snapshots(player_id, stat_type);

-- Add comment for documentation
COMMENT ON TABLE historical_odds_snapshots IS 'Historical bookmaker odds snapshots for hit rate calculation. Captures point-in-time player prop odds and resolves against actual results.';
COMMENT ON COLUMN historical_odds_snapshots.hit_result IS 'Result after game resolution: OVER, UNDER, or PUSH (when actual equals line)';
COMMENT ON COLUMN historical_odds_snapshots.was_starter IS 'Filter flag for analyzing hit rates only when player was in starting lineup';
