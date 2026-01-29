-- Migration 022: Add game results storage
--
-- This migration adds:
-- 1. scheduled_start, home_score, away_score columns to games table
-- 2. New game_results table for sport-specific period scoring
--
-- Author: Claude
-- Date: 2025-01-29

BEGIN;

-- =============================================================================
-- PART 1: Add columns to games table
-- =============================================================================

-- Add scheduled start time for tipoffs/kickoffs
ALTER TABLE games
ADD COLUMN IF NOT EXISTS scheduled_start TIMESTAMP;

-- Add final score columns (updated when game completes)
ALTER TABLE games
ADD COLUMN IF NOT EXISTS home_score INTEGER;

ALTER TABLE games
ADD COLUMN IF NOT EXISTS away_score INTEGER;

-- Add indexes for efficient querying
CREATE INDEX IF NOT EXISTS ix_games_scheduled_start
ON games(scheduled_start);

CREATE INDEX IF NOT EXISTS ix_games_final_scores
ON games(home_score, away_score)
WHERE home_score IS NOT NULL AND away_score IS NOT NULL;

-- =============================================================================
-- PART 2: Create game_results table for sport-specific scoring
-- =============================================================================

CREATE TABLE IF NOT EXISTS game_results (
    -- Primary key
    id VARCHAR(36) PRIMARY KEY,

    -- Foreign key to games (one-to-one relationship)
    game_id VARCHAR(36) NOT NULL UNIQUE REFERENCES games(id) ON DELETE CASCADE,

    -- -------------------------------------------------------------------------
    -- BASKETBALL SCORING (NBA, WNBA, NFL)
    -- -------------------------------------------------------------------------
    -- Quarter 1
    q1_home INTEGER,
    q1_away INTEGER,
    -- Quarter 2
    q2_home INTEGER,
    q2_away INTEGER,
    -- Quarter 3
    q3_home INTEGER,
    q3_away INTEGER,
    -- Quarter 4
    q4_home INTEGER,
    q4_away INTEGER,

    -- Overtime periods (NBA/NFL can have multiple OTs)
    ot_home INTEGER,   -- First OT
    ot_away INTEGER,
    ot2_home INTEGER,  -- Second OT (rare)
    ot2_away INTEGER,
    ot3_home INTEGER,  -- Third OT (very rare)
    ot3_away INTEGER,

    -- -------------------------------------------------------------------------
    -- HOCKEY SCORING (NHL)
    -- -------------------------------------------------------------------------
    -- Period 1
    p1_home INTEGER,
    p1_away INTEGER,
    -- Period 2
    p2_home INTEGER,
    p2_away INTEGER,
    -- Period 3
    p3_home INTEGER,
    p3_away INTEGER,
    -- Note: ot_home/ot_away columns are shared with basketball

    -- Shootout (NHL-specific)
    shootout_home INTEGER,
    shootout_away INTEGER,

    -- -------------------------------------------------------------------------
    -- BASEBALL SCORING (MLB)
    -- -------------------------------------------------------------------------
    -- Store innings as JSON array: [{"inning": 1, "away": 0, "home": 1}, ...]
    -- This handles variable length games (extra innings)
    innings JSONB,

    -- -------------------------------------------------------------------------
    -- BETTING OUTCOMES
    -- -------------------------------------------------------------------------
    -- Game winner ('home' or 'away')
    winner VARCHAR(10),

    -- Spread result ('home', 'away', 'push')
    cover_spread VARCHAR(10),

    -- Total over/under result
    total_over BOOLEAN,  -- TRUE if over hit, FALSE if under hit
    total_line FLOAT,    -- The closing total line
    spread_line FLOAT,   -- The closing spread (from home team perspective)

    -- -------------------------------------------------------------------------
    -- METADATA
    -- -------------------------------------------------------------------------
    -- ESPN game ID for result data
    espn_id INTEGER,

    -- Data source identifier
    data_source VARCHAR(50),

    -- Stadium attendance
    attendance INTEGER,

    -- Game duration in minutes
    duration INTEGER,

    -- Audit timestamps
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- -------------------------------------------------------------------------
-- INDEXES
-- -------------------------------------------------------------------------

-- Primary index for game lookups
CREATE UNIQUE INDEX ix_game_results_game_id ON game_results(game_id);

-- Index for ESPN lookups
CREATE INDEX ix_game_results_espn_id ON game_results(espn_id);

-- Index for completed games with results
CREATE INDEX ix_game_results_completed
ON game_results(winner)
WHERE winner IS NOT NULL;

-- Index for betting analysis
CREATE INDEX ix_game_results_betting
ON game_results(cover_spread, total_over)
WHERE cover_spread IS NOT NULL;

-- -------------------------------------------------------------------------
-- TRIGGERS
-- -------------------------------------------------------------------------

-- Update updated_at timestamp on row modification
CREATE OR REPLACE FUNCTION update_game_results_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_game_results_updated_at
BEFORE UPDATE ON game_results
FOR EACH ROW
EXECUTE FUNCTION update_game_results_updated_at();

-- -------------------------------------------------------------------------
-- COMMENTS
-- -------------------------------------------------------------------------

COMMENT ON TABLE game_results IS 'Sport-specific game results with period-by-period scoring breakdown';
COMMENT ON COLUMN game_results.game_id IS 'Foreign key to games table (one-to-one)';
COMMENT ON COLUMN game_results.q1_home IS 'Basketball: Quarter 1 home score';
COMMENT ON COLUMN game_results.p1_home IS 'Hockey: Period 1 home score';
COMMENT ON COLUMN game_results.innings IS 'Baseball: JSON array of inning scores [{"inning": 1, "away": 0, "home": 1}]';
COMMENT ON COLUMN game_results.winner IS 'Game winner: "home" or "away"';
COMMENT ON COLUMN game_results.cover_spread IS 'Spread result: "home", "away", or "push"';
COMMENT ON COLUMN game_results.total_over IS 'Total result: TRUE if over hit, FALSE if under hit';

COMMIT;

-- =============================================================================
-- ROLLBACK
-- =============================================================================
-- To rollback this migration, run:
--
-- BEGIN;
-- DROP TABLE IF EXISTS game_results CASCADE;
-- DROP INDEX IF EXISTS ix_games_scheduled_start;
-- DROP INDEX IF EXISTS ix_games_final_scores;
-- ALTER TABLE games DROP COLUMN IF EXISTS scheduled_start;
-- ALTER TABLE games DROP COLUMN IF EXISTS home_score;
-- ALTER TABLE games DROP COLUMN IF EXISTS away_score;
-- DROP FUNCTION IF EXISTS update_game_results_updated_at CASCADE;
-- COMMIT;
