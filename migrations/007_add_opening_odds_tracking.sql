-- Migration: Add opening odds tracking to historical_odds_snapshots
-- This enables tracking opening lines vs current lines to find value opportunities

-- Add is_opening_line column to identify opening odds snapshots
ALTER TABLE historical_odds_snapshots
ADD COLUMN is_opening_line BOOLEAN DEFAULT FALSE NOT NULL;

-- Add index for efficient querying of opening lines
CREATE INDEX ix_historical_odds_snapshots_is_opening_line
ON historical_odds_snapshots(is_opening_line)
WHERE is_opening_line = TRUE;

-- Add composite index for finding opening vs current line comparisons
CREATE INDEX ix_historical_odds_snapshots_opening_comparison
ON historical_odds_snapshots(game_id, player_id, stat_type, bookmaker_name, snapshot_time);

-- Add column to track line movement
ALTER TABLE historical_odds_snapshots
ADD COLUMN line_movement FLOAT DEFAULT 0.0;

-- line_movement = current_line - opening_line (positive = line moved up, negative = moved down)

-- Add comment for documentation
COMMENT ON COLUMN historical_odds_snapshots.is_opening_line IS 'TRUE if this is the opening line snapshot (first odds captured)';
COMMENT ON COLUMN historical_odds_snapshots.line_movement IS 'Difference from opening line: current_line - opening_line';
