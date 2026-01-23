-- Create player_season_stats table
-- Stores cached player season-averaged per-36 stats from nba_api
-- This table improves prediction accuracy by using actual player data
-- instead of position averages

CREATE TABLE IF NOT EXISTS player_season_stats (
    id VARCHAR(36) PRIMARY KEY,
    player_id VARCHAR(36) NOT NULL,
    season VARCHAR(10) NOT NULL,

    -- Averages from recent games (typically 10-20)
    games_count INTEGER NOT NULL,
    points_per_36 FLOAT NOT NULL,
    rebounds_per_36 FLOAT NOT NULL,
    assists_per_36 FLOAT NOT NULL,
    threes_per_36 FLOAT NOT NULL,
    avg_minutes FLOAT NOT NULL,

    -- Tracking
    last_game_date DATE,
    fetched_at TIMESTAMP NOT NULL,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,

    -- Foreign key
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,

    -- Unique constraint (one entry per player per season)
    CONSTRAINT uq_player_season UNIQUE (player_id, season)
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS ix_player_season_stats_player_id ON player_season_stats(player_id);
CREATE INDEX IF NOT EXISTS ix_player_season_stats_season ON player_season_stats(season);
CREATE INDEX IF NOT EXISTS ix_player_season_stats_fetched_at ON player_season_stats(fetched_at);
CREATE INDEX IF NOT EXISTS ix_player_season_stats_player_season ON player_season_stats(player_id, season);

-- Add comment for documentation
COMMENT ON TABLE player_season_stats IS 'Cached player season-averaged per-36 stats from nba_api. Improves prediction accuracy by using actual player data instead of position averages.';
COMMENT ON COLUMN player_season_stats.points_per_36 IS 'Player points per 36 minutes, averaged from recent games';
COMMENT ON COLUMN player_season_stats.rebounds_per_36 IS 'Player rebounds per 36 minutes, averaged from recent games';
COMMENT ON COLUMN player_season_stats.assists_per_36 IS 'Player assists per 36 minutes, averaged from recent games';
COMMENT ON COLUMN player_season_stats.threes_per_36 IS 'Player 3-pointers made per 36 minutes, averaged from recent games';
COMMENT ON COLUMN player_season_stats.fetched_at IS 'When this cache entry was created. Used for TTL (24-hour cache)';
