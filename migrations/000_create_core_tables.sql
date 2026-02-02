-- Create core tables for NBA data
-- These are the minimum tables needed to test the sync layer

-- Players table
CREATE TABLE IF NOT EXISTS players (
    id VARCHAR(36) PRIMARY KEY,
    external_id VARCHAR(100) UNIQUE NOT NULL,
    id_source VARCHAR(10) NOT NULL DEFAULT 'nba',
    nba_api_id INTEGER,
    name VARCHAR(255) NOT NULL,
    team VARCHAR(3) NOT NULL,
    position VARCHAR(10),
    active BOOLEAN NOT NULL DEFAULT TRUE,
    last_roster_check TIMESTAMP,
    data_source VARCHAR(50),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Games table
CREATE TABLE IF NOT EXISTS games (
    id VARCHAR(36) PRIMARY KEY,
    external_id VARCHAR(100) UNIQUE NOT NULL,
    id_source VARCHAR(10) NOT NULL DEFAULT 'nba',
    game_date TIMESTAMP NOT NULL,
    away_team VARCHAR(3) NOT NULL,
    home_team VARCHAR(3) NOT NULL,
    season INTEGER NOT NULL,
    status VARCHAR(50) NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- PlayerStats table
CREATE TABLE IF NOT EXISTS player_stats (
    id VARCHAR(36) PRIMARY KEY,
    player_id VARCHAR(36) NOT NULL,
    game_id VARCHAR(36) NOT NULL,
    points INTEGER,
    rebounds INTEGER,
    assists INTEGER,
    threes INTEGER,
    minutes INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS ix_players_external_id ON players(external_id);
CREATE INDEX IF NOT EXISTS ix_players_id_source ON players(id_source);
CREATE INDEX IF NOT EXISTS ix_players_nba_api_id ON players(nba_api_id);
CREATE INDEX IF NOT EXISTS ix_players_team ON players(team);
CREATE INDEX IF NOT EXISTS ix_players_active ON players(active);

CREATE INDEX IF NOT EXISTS ix_games_external_id ON games(external_id);
CREATE INDEX IF NOT EXISTS ix_games_game_date ON games(game_date);
CREATE INDEX IF NOT EXISTS ix_games_season ON games(season);
CREATE INDEX IF NOT EXISTS ix_games_status ON games(status);

CREATE INDEX IF NOT EXISTS ix_player_stats_player_id ON player_stats(player_id);
CREATE INDEX IF NOT EXISTS ix_player_stats_game_id ON player_stats(game_id);
