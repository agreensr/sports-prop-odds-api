-- Migration: Create Enhanced Predictions Table
-- Purpose: Sport-agnostic predictions with multi-sport support
-- Phase: 1 - Data Integrity Foundation

-- First, add sport_id to existing predictions table if it exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'predictions') THEN
        ALTER TABLE predictions ADD COLUMN IF NOT EXISTS sport_id VARCHAR(3) DEFAULT 'nba';

        -- Add foreign key constraint to sports table
        ALTER TABLE predictions DROP CONSTRAINT IF EXISTS predictions_sport_id_fkey;
        ALTER TABLE predictions ADD CONSTRAINT predictions_sport_id_fkey
            FOREIGN KEY (sport_id) REFERENCES sports(id);

        -- Add index for sport_id
        CREATE INDEX IF NOT EXISTS ix_predictions_sport_id ON predictions(sport_id);
    END IF;
END $$;

-- Create unique constraint on predictions to prevent duplicates
-- (sport_id, player_id, game_id, stat_type, model_version) should be unique
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'predictions') THEN
        CREATE UNIQUE INDEX IF NOT EXISTS uq_prediction
        ON predictions(player_id, game_id, stat_type, model_version)
        WHERE model_version IS NOT NULL;
    END IF;
END $$;

-- Add index for resolved predictions tracking
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'predictions') THEN
        CREATE INDEX IF NOT EXISTS ix_predictions_resolved
        ON predictions(was_correct) WHERE was_correct IS NOT NULL;

        CREATE INDEX IF NOT EXISTS ix_predictions_created_at
        ON predictions(created_at DESC);

        CREATE INDEX IF NOT EXISTS ix_predictions_confidence
        ON predictions(confidence DESC) WHERE confidence >= 0.6;
    END IF;
END $$;

-- Comment the table for documentation
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'predictions') THEN
        COMMENT ON TABLE predictions IS 'AI-generated player prop predictions with multi-sport support';
        COMMENT ON COLUMN predictions.sport_id IS 'Foreign key to sports table (nba, nfl, mlb, nhl)';
        COMMENT ON INDEX uq_prediction IS 'Prevents duplicate predictions for same player/game/stat/model';
    END IF;
END $$;
