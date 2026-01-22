-- Migration: Add Parlay and ParlayLeg tables
-- Description: Creates tables for storing generated parlay bets combining multiple player prop predictions
-- Date: 2025-01-21

-- Create parlays table
CREATE TABLE IF NOT EXISTS parlays (
    id VARCHAR(36) PRIMARY KEY,
    parlay_type VARCHAR(20) NOT NULL,
    calculated_odds FLOAT NOT NULL,
    implied_probability FLOAT NOT NULL,
    expected_value FLOAT NOT NULL,
    confidence_score FLOAT NOT NULL,
    total_legs INTEGER NOT NULL,
    correlation_score FLOAT,
    created_at TIMESTAMP NOT NULL
);

-- Create indexes for parlays table
CREATE INDEX IF NOT EXISTS ix_parlays_type ON parlays(parlay_type);
CREATE INDEX IF NOT EXISTS ix_parlays_ev ON parlays(expected_value);
CREATE INDEX IF NOT EXISTS ix_parlays_created ON parlays(created_at);

-- Create parlay_legs table
CREATE TABLE IF NOT EXISTS parlay_legs (
    id VARCHAR(36) PRIMARY KEY,
    parlay_id VARCHAR(36) NOT NULL,
    prediction_id VARCHAR(36) NOT NULL,
    leg_order INTEGER NOT NULL,
    selection VARCHAR(10) NOT NULL,
    leg_odds FLOAT NOT NULL,
    leg_confidence FLOAT NOT NULL,
    correlation_with_parlay FLOAT,
    created_at TIMESTAMP NOT NULL,
    FOREIGN KEY (parlay_id) REFERENCES parlays(id) ON DELETE CASCADE,
    FOREIGN KEY (prediction_id) REFERENCES predictions(id) ON DELETE CASCADE
);

-- Create indexes for parlay_legs table
CREATE INDEX IF NOT EXISTS ix_parlay_legs_parlay_id ON parlay_legs(parlay_id);
CREATE INDEX IF NOT EXISTS ix_parlay_legs_prediction_id ON parlay_legs(prediction_id);

-- Add comments for documentation
COMMENT ON TABLE parlays IS 'Generated parlay bets combining multiple player prop predictions';
COMMENT ON COLUMN parlays.parlay_type IS 'Type of parlay: same_game or multi_game';
COMMENT ON COLUMN parlays.calculated_odds IS 'American odds (e.g., +350, -110)';
COMMENT ON COLUMN parlays.expected_value IS 'Expected value as decimal (0.05 = +5% EV)';

COMMENT ON TABLE parlay_legs IS 'Individual legs within a parlay bet';
COMMENT ON COLUMN parlay_legs.selection IS 'OVER or UNDER selection';
COMMENT ON COLUMN parlay_legs.correlation_with_parlay IS 'Correlation coefficient with other legs in parlay';
