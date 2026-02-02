-- Migration: Create sync_metadata table
-- Description: Tracks sync job status and health metrics
-- Date: 2025-01-24

-- Create sync_metadata table
CREATE TABLE IF NOT EXISTS sync_metadata (
    id VARCHAR(36) PRIMARY KEY,
    source VARCHAR(32) NOT NULL,
    data_type VARCHAR(32) NOT NULL,
    last_sync_started_at TIMESTAMP WITH TIME ZONE,
    last_sync_completed_at TIMESTAMP WITH TIME ZONE,
    last_sync_status VARCHAR(16),
    records_processed INTEGER DEFAULT 0,
    records_matched INTEGER DEFAULT 0,
    records_failed INTEGER DEFAULT 0,
    error_message TEXT,
    sync_duration_ms INTEGER,
    UNIQUE(source, data_type)
);

-- Create indexes for monitoring queries
CREATE INDEX IF NOT EXISTS idx_sync_metadata_source_type ON sync_metadata(source, data_type);
CREATE INDEX IF NOT EXISTS idx_sync_metadata_status ON sync_metadata(last_sync_status);
CREATE INDEX IF NOT EXISTS idx_sync_metadata_completed ON sync_metadata(last_sync_completed_at);

-- Add comments for documentation
COMMENT ON TABLE sync_metadata IS 'Tracks sync job status and health metrics for all data sources';
COMMENT ON COLUMN sync_metadata.source IS 'Data source: nba_api, odds_api, espn, etc.';
COMMENT ON COLUMN sync_metadata.data_type IS 'Type of data: games, odds, player_stats, etc.';
COMMENT ON COLUMN sync_metadata.last_sync_status IS 'success, failed, in_progress, or partial';
COMMENT ON COLUMN sync_metadata.records_processed IS 'Total records processed in last sync';
COMMENT ON COLUMN sync_metadata.records_matched IS 'Records successfully matched';
COMMENT ON COLUMN sync_metadata.records_failed IS 'Records that failed to match';
COMMENT ON COLUMN sync_metadata.sync_duration_ms IS 'Duration of last sync in milliseconds';
