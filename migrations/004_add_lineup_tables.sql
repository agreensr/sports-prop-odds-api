-- Create expected_lineups table
-- Migration: 004_add_lineup_tables.sql
-- Description: Track projected starting lineups and minutes allocations
-- Date: 2025-01-21

CREATE TABLE IF NOT EXISTS expected_lineups (
    id VARCHAR(36) PRIMARY KEY,
    game_id VARCHAR(36),
    team VARCHAR(3) NOT NULL,
    player_id VARCHAR(36) NOT NULL,
    starter_position VARCHAR(10),
    is_confirmed BOOLEAN DEFAULT FALSE NOT NULL,
    minutes_projection INTEGER,
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    FOREIGN KEY (game_id) REFERENCES games(id) ON DELETE CASCADE,
    FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE
);

-- Create indexes for common query patterns
CREATE INDEX IF NOT EXISTS ix_expected_lineups_game_id ON expected_lineups(game_id);
CREATE INDEX IF NOT EXISTS ix_expected_lineups_player_id ON expected_lineups(player_id);
CREATE INDEX IF NOT EXISTS ix_expected_lineups_created_at ON expected_lineups(created_at);
CREATE INDEX IF NOT EXISTS ix_expected_lineups_game_team ON expected_lineups(game_id, team);

-- Add comments for documentation
COMMENT ON TABLE expected_lineups IS 'Projected starting lineups and minutes allocations';
COMMENT ON COLUMN expected_lineups.starter_position IS 'PG, SG, SF, PF, C, or None for bench players';
COMMENT ON COLUMN expected_lineups.is_confirmed IS 'True = official confirmed lineup, False = projected';
COMMENT ON COLUMN expected_lineups.minutes_projection IS 'Expected minutes for the player';
