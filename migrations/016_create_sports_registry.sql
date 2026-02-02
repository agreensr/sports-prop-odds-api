-- Migration: Create Sports Registry
-- Purpose: Central registry for all supported sports
-- Phase: 1 - Data Integrity Foundation

-- Sports registry table
CREATE TABLE IF NOT EXISTS sports (
    id VARCHAR(3) PRIMARY KEY,  -- 'nba', 'nfl', 'mlb', 'nhl'
    name VARCHAR(50) NOT NULL,
    active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Seed initial sports
INSERT INTO sports (id, name, active) VALUES
    ('nba', 'National Basketball Association', TRUE),
    ('nfl', 'National Football League', TRUE),
    ('mlb', 'Major League Baseball', TRUE),
    ('nhl', 'National Hockey League', TRUE)
ON CONFLICT (id) DO NOTHING;

-- Index for active sports lookup
CREATE INDEX IF NOT EXISTS ix_sports_active ON sports(active);
