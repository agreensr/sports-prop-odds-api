-- Migration: Create match_audit_log table
-- Description: Audit trail for all matches and changes to mapping data
-- Date: 2025-01-24

-- Create match_audit_log table
CREATE TABLE IF NOT EXISTS match_audit_log (
    id VARCHAR(36) PRIMARY KEY,
    entity_type VARCHAR(16) NOT NULL,
    entity_id VARCHAR(64) NOT NULL,
    action VARCHAR(16) NOT NULL,
    previous_state JSONB,
    new_state JSONB,
    match_details JSONB,
    performed_by VARCHAR(64),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for audit queries
CREATE INDEX IF NOT EXISTS idx_audit_entity ON match_audit_log(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_audit_created ON match_audit_log(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_action ON match_audit_log(action);
CREATE INDEX IF NOT EXISTS idx_audit_performed_by ON match_audit_log(performed_by);

-- Add comments for documentation
COMMENT ON TABLE match_audit_log IS 'Audit trail for all matches and changes to mapping data';
COMMENT ON COLUMN match_audit_log.entity_type IS 'Type of entity: game, player, team';
COMMENT ON COLUMN match_audit_log.entity_id IS 'ID of the entity that was changed';
COMMENT ON COLUMN match_audit_log.action IS 'Action performed: created, updated, deleted, matched, unmapped';
COMMENT ON COLUMN match_audit_log.previous_state IS 'JSONB of entity state before change';
COMMENT ON COLUMN match_audit_log.new_state IS 'JSONB of entity state after change';
COMMENT ON COLUMN match_audit_log.match_details IS 'JSONB with confidence, method, etc.';
COMMENT ON COLUMN match_audit_log.performed_by IS 'System or user who performed the action';
