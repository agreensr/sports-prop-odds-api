-- =============================================================================
-- Migration 021: Add Sport-Specific Columns for Full Model Unification
-- =============================================================================
-- This migration adds nullable sport-specific columns to unified tables
-- to support all sports (NBA, NFL, MLB, NHL) in a single table structure.
--
-- Architecture Decision (P1 #5): Full Unification
-- - Single set of tables for all sports
-- - Sport-specific fields are nullable (sparse column approach)
-- - Filter by sport_id for sport-specific queries
-- =============================================================================

BEGIN;

-- -----------------------------------------------------------------------------
-- PLAYERS TABLE: Add sport-specific columns
-- -----------------------------------------------------------------------------

-- Basketball fields (NBA, WNBA, NCAA)
ALTER TABLE players ADD COLUMN IF NOT EXISTS height VARCHAR(10);
ALTER TABLE players ADD COLUMN IF NOT EXISTS weight INTEGER;

-- Football fields (NFL, NCAA)
ALTER TABLE players ADD COLUMN IF NOT EXISTS college VARCHAR(100);
ALTER TABLE players ADD COLUMN IF NOT EXISTS draft_year INTEGER;
ALTER TABLE players ADD COLUMN IF NOT EXISTS draft_round INTEGER;
ALTER TABLE players ADD COLUMN IF NOT EXISTS jersey_number INTEGER;

-- Hockey fields (NHL)
ALTER TABLE players ADD COLUMN IF NOT EXISTS catches VARCHAR(1);
ALTER TABLE players ADD COLUMN IF NOT EXISTS birth_date DATE;
ALTER TABLE players ADD COLUMN IF NOT EXISTS shoots VARCHAR(1);

-- Baseball fields (MLB)
ALTER TABLE players ADD COLUMN IF NOT EXISTS bats VARCHAR(5);
ALTER TABLE players ADD COLUMN IF NOT EXISTS throws VARCHAR(1);

-- Add comments for documentation
COMMENT ON COLUMN players.height IS 'Player height (format: "6-4") - NBA/NFL/MLB';
COMMENT ON COLUMN players.weight IS 'Player weight in pounds - NBA/NFL/MLB';
COMMENT ON COLUMN players.college IS 'College - NFL only';
COMMENT ON COLUMN players.draft_year IS 'Year drafted - NFL only';
COMMENT ON COLUMN players.draft_round IS 'Draft round - NFL only';
COMMENT ON COLUMN players.jersey_number IS 'Uniform number - All sports';
COMMENT ON COLUMN players.catches IS 'Shooting hand L/R - NHL only';
COMMENT ON COLUMN players.birth_date IS 'Date of birth - NHL only';
COMMENT ON COLUMN players.shoots IS 'Shooting hand L/R - NHL only';
COMMENT ON COLUMN players.bats IS 'Batting side L/R/Switch - MLB only';
COMMENT ON COLUMN players.throws IS 'Throwing hand L/R - MLB only';

-- -----------------------------------------------------------------------------
-- GAMES TABLE: Add sport-specific columns
-- -----------------------------------------------------------------------------

-- Football fields (NFL)
ALTER TABLE games ADD COLUMN IF NOT EXISTS week INTEGER;
ALTER TABLE games ADD COLUMN IF NOT EXISTS season_type VARCHAR(10);

-- Hockey fields (NHL)
ALTER TABLE games ADD COLUMN IF NOT EXISTS shootout BOOLEAN;

-- Baseball fields (MLB)
ALTER TABLE games ADD COLUMN IF NOT EXISTS double_header BOOLEAN;
ALTER TABLE games ADD COLUMN IF NOT EXISTS game_number INTEGER;
ALTER TABLE games ADD COLUMN IF NOT EXISTS inning VARCHAR(10);

-- Add comments
COMMENT ON COLUMN games.week IS 'Week number (1-18) - NFL only';
COMMENT ON COLUMN games.season_type IS 'Season type: REG, POST, PRE - NFL only';
COMMENT ON COLUMN games.shootout IS 'Game decided by shootout - NHL only';
COMMENT ON COLUMN games.double_header IS 'Part of doubleheader - MLB only';
COMMENT ON COLUMN games.game_number IS '1 or 2 for doubleheaders - MLB only';
COMMENT ON COLUMN games.inning IS 'Current/final inning - MLB only';

-- -----------------------------------------------------------------------------
-- PLAYER_STATS TABLE: Add sport-specific stat columns
-- -----------------------------------------------------------------------------

-- Common stats (already exist: points, rebounds, assists, threes, minutes)
-- Adding sport-specific stats:

-- Football stats
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS passing_yards INTEGER;
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS rushing_yards INTEGER;
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS receptions INTEGER;
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS touchdowns INTEGER;
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS interceptions INTEGER;

-- Hockey stats
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS goals INTEGER;
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS shots INTEGER;
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS plus_minus INTEGER;
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS saves INTEGER;

-- Baseball stats
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS hits INTEGER;
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS home_runs INTEGER;
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS rbi INTEGER;
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS strikeouts INTEGER;
ALTER TABLE player_stats ADD COLUMN IF NOT EXISTS at_bats INTEGER;

-- -----------------------------------------------------------------------------
-- INDEXES for sport-specific queries
-- -----------------------------------------------------------------------------

-- Player indexes for sport-specific lookups
CREATE INDEX IF NOT EXISTS ix_players_jersey_number ON players(jersey_number) WHERE jersey_number IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_players_college ON players(college) WHERE college IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_players_draft_year ON players(draft_year) WHERE draft_year IS NOT NULL;

-- Game indexes for sport-specific queries
CREATE INDEX IF NOT EXISTS ix_games_week ON games(week) WHERE week IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_games_season_type ON games(season_type) WHERE season_type IS NOT NULL;

-- Player stats indexes for sport-specific queries
CREATE INDEX IF NOT EXISTS ix_player_stats_passing_yards ON player_stats(passing_yards) WHERE passing_yards IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_player_stats_goals ON player_stats(goals) WHERE goals IS NOT NULL;
CREATE INDEX IF NOT EXISTS ix_player_stats_home_runs ON player_stats(home_runs) WHERE home_runs IS NOT NULL;

-- -----------------------------------------------------------------------------
-- GRANT PERMISSIONS (adjust for your environment)
-- -----------------------------------------------------------------------------
-- GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO your_app_user;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO your_app_user;

COMMIT;

-- =============================================================================
-- VERIFICATION QUERIES
-- =============================================================================
-- Run these after migration to verify success:

-- Check new columns exist
-- SELECT column_name, data_type, is_nullable
-- FROM information_schema.columns
-- WHERE table_name = 'players'
-- AND column_name IN ('height', 'weight', 'college', 'draft_year', 'jersey_number',
--                     'catches', 'bats', 'throws')
-- ORDER BY column_name;

-- Verify sport_id data
-- SELECT sport_id, COUNT(*) as count
-- FROM players
-- GROUP BY sport_id;

-- Test multi-sport query
-- SELECT sport_id, COUNT(*) as player_count
-- FROM players
-- WHERE sport_id IN ('nba', 'nfl', 'mlb', 'nhl')
-- GROUP BY sport_id;
