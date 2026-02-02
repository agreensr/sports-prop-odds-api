-- =============================================================================
-- Rollback Migration 022: Remove Model Version Indexes
-- =============================================================================
-- This removes the indexes added for prediction versioning support.

BEGIN;

-- Drop the model_version indexes
DROP INDEX IF EXISTS ix_predictions_model_version_created;
DROP INDEX IF EXISTS ix_predictions_model_version;

-- Remove comments (optional)
COMMENT ON COLUMN predictions.model_version IS NULL;
COMMENT ON COLUMN predictions.created_at IS NULL;

COMMIT;
