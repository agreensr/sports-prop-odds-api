-- Create player_injuries table
-- Migration: 003_add_injury_tables.sql
-- Description: Track player injury status and impact for injury-aware predictions
-- Date: 2025-01-21

CREATE TABLE IF NOT EXISTS player_injuries (
    id VARCHAR(36) PRIMARY KEY,
    player_id VARCHAR(36) NOT NULL,
    game_id VARCHAR(36),
    injury_type VARCHAR(100),
    status VARCHAR(50) NOT NULL,
    impact_description TEXT,
    days_since_return INTEGER,
    minutes_restriction INTEGER,
    games_played_since_return INTEGER,
    reported_date DATE NOT NULL,
    return_date DATE,
    external_source VARCHAR(100),
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE SET NULL
);

-- Create indexes for common query patterns
CREATE INDEX IF NOT EXISTS ix_player_injuries_player_id ON player_injuries(player_id);
CREATE INDEX IF NOT EXISTS ix_player_injuries_status ON player_injuries(status);
CREATE INDEX IF NOT EXISTS ix_player_injuries_reported_date ON player_injuries(reported_date);
CREATE INDEX IF NOT EXISTS ix_player_injuries_updated_at ON player_injuries(updated_at);
CREATE INDEX IF NOT EXISTS ix_player_injuries_game_id ON player_injuries(game_id);
CREATE INDEX IF NOT EXISTS ix_player_injuries_player_status ON player_injuries(player_id, status);
CREATE INDEX IF NOT EXISTS ix_player_injuries_return_date ON player_injuries(return_date);

-- Add comments for documentation
COMMENT ON TABLE player_injuries IS 'Track player injury status and impact for injury-aware predictions';
COMMENT ON COLUMN player_injuries.status IS 'Injury status: out, doubtful, questionable, day-to-day, returning, available';
COMMENT ON COLUMN player_injuries.days_since_return IS 'Days since returning from injury (for returning status)';
COMMENT ON COLUMN player_injuries.minutes_restriction IS 'Minutes cap for players returning from injury';
COMMENT ON COLUMN player_injuries.games_played_since_return IS 'Games played since return to track progression';
