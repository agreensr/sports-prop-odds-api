-- Add index on model_version for efficient version-based queries
-- This supports P2 #21: Prediction Versioning
-- Allows for: 
-- - Finding all predictions from a specific model version
-- - Regenerating predictions when models improve
-- - Comparing performance between model versions

-- Add index on model_version column
CREATE INDEX IF NOT EXISTS ix_predictions_model_version ON predictions(model_version);

-- Add composite index for version + created_at (for chronological version queries)
CREATE INDEX IF NOT EXISTS ix_predictions_model_version_created ON predictions(model_version, created_at DESC);

-- Add comment for documentation
COMMENT ON COLUMN predictions.model_version IS 'Model version that generated this prediction (e.g., "1.0.0"). Used for tracking model performance and regenerating when models improve.';

COMMENT ON COLUMN predictions.created_at IS 'Timestamp when prediction was generated. Used for freshness checks and version comparisons.';
