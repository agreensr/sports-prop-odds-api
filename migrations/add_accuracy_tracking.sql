-- Migration: Add Accuracy Tracking to Predictions Table
-- Description: Adds fields to track prediction accuracy vs actual game results
-- Version: 001
-- Date: 2025-01-21

-- =====================================================
-- IMPORTANT: Backup before running this migration!
-- =====================================================
-- Run this command before executing:
-- pg_dump -Fc sports_betting > /backups/pre_accuracy_$(date +%Y%m%d).dump

-- =====================================================
-- Add new columns to predictions table
-- =====================================================

-- actual_value: The actual stat value from the game (points, rebounds, etc.)
ALTER TABLE predictions
ADD COLUMN IF NOT EXISTS actual_value FLOAT;

-- difference: Absolute difference between predicted and actual (|predicted - actual|)
ALTER TABLE predictions
ADD COLUMN IF NOT EXISTS difference FLOAT;

-- was_correct: Whether the recommendation (OVER/UNDER) was correct
-- NULL for NONE recommendations
ALTER TABLE predictions
ADD COLUMN IF NOT EXISTS was_correct BOOLEAN;

-- actuals_resolved_at: Timestamp when actual values were populated
ALTER TABLE predictions
ADD COLUMN IF NOT EXISTS actuals_resolved_at TIMESTAMP;

-- =====================================================
-- Create indexes for accuracy queries
-- =====================================================

-- Index for querying resolved predictions by time
CREATE INDEX IF NOT EXISTS ix_predictions_actuals_resolved
ON predictions(actuals_resolved_at)
WHERE actuals_resolved_at IS NOT NULL;

-- Composite index for accuracy lookups by game and stat type
CREATE INDEX IF NOT EXISTS ix_predictions_accuracy_lookup
ON predictions(game_id, stat_type, actuals_resolved_at)
WHERE actuals_resolved_at IS NOT NULL;

-- =====================================================
-- Verification query (run after migration)
-- =====================================================

-- Check that columns were added successfully
/*
SELECT
    column_name,
    data_type,
    is_nullable,
    column_default
FROM information_schema.columns
WHERE table_name = 'predictions'
AND column_name IN ('actual_value', 'difference', 'was_correct', 'actuals_resolved_at')
ORDER BY ordinal_position;
*/

-- =====================================================
-- Rollback (if needed)
-- =====================================================
-- DROP INDEX IF EXISTS ix_predictions_accuracy_lookup;
-- DROP INDEX IF EXISTS ix_predictions_actuals_resolved;
-- ALTER TABLE predictions DROP COLUMN IF EXISTS actuals_resolved_at;
-- ALTER TABLE predictions DROP COLUMN IF EXISTS was_correct;
-- ALTER TABLE predictions DROP COLUMN IF EXISTS difference;
-- ALTER TABLE predictions DROP COLUMN IF EXISTS actual_value;
