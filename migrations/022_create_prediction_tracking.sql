-- Track prediction accuracy for analysis
-- This table stores high-confidence predictions and their actual results

CREATE TABLE IF NOT EXISTS prediction_tracking (
    id VARCHAR(36) PRIMARY KEY,
    game_id VARCHAR(36) NOT NULL REFERENCES games(id) ON DELETE CASCADE,
    player_id VARCHAR(36) REFERENCES players(id) ON DELETE SET NULL,

    -- Game info
    game_date DATE NOT NULL,
    away_team VARCHAR(3) NOT NULL,
    home_team VARCHAR(3) NOT NULL,
    player_name VARCHAR(100) NOT NULL,
    player_team VARCHAR(3) NOT NULL,

    -- Prediction details
    stat_type VARCHAR(20) NOT NULL,
    predicted_value DECIMAL(10, 1) NOT NULL,
    bookmaker_line DECIMAL(10, 1) NOT NULL,
    bookmaker VARCHAR(20) NOT NULL,
    edge DECIMAL(10, 1) NOT NULL,
    recommendation VARCHAR(10) NOT NULL, -- OVER, UNDER, PASS
    confidence DECIMAL(4, 2) NOT NULL, -- 0.00 to 1.00

    -- Actual results (populated after game)
    actual_value DECIMAL(10, 1),

    -- Outcome
    is_correct BOOLEAN,
    difference DECIMAL(10, 1), -- actual - predicted

    -- Metadata
    prediction_generated_at TIMESTAMP NOT NULL,
    actual_resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Indexes for querying
CREATE INDEX IF NOT EXISTS ix_prediction_tracking_game_date ON prediction_tracking(game_date);
CREATE INDEX IF NOT EXISTS ix_prediction_tracking_game_id ON prediction_tracking(game_id);
CREATE INDEX IF NOT EXISTS ix_prediction_tracking_player ON prediction_tracking(player_name);
CREATE INDEX IF NOT EXISTS ix_prediction_tracking_confidence ON prediction_tracking(confidence);
CREATE INDEX IF NOT EXISTS ix_prediction_tracking_resolved ON prediction_tracking(actual_resolved_at) WHERE actual_resolved_at IS NULL;
CREATE INDEX IF NOT EXISTS ix_prediction_tracking_outcome ON prediction_tracking(is_correct) WHERE actual_resolved_at IS NOT NULL;

-- Comment
COMMENT ON TABLE prediction_tracking IS 'Tracks high-confidence predictions and their actual results for accuracy analysis';
