#!/bin/bash
#####################################################################
# NBA Sports API - Rollback Script
# Rolls back to a previous backup if deployment fails
#####################################################################

set -e

# Configuration
REMOTE_HOST="89.117.150.95"
REMOTE_USER="root"
REMOTE_PATH="/opt/sports-bet-ai-api"
SERVICE_NAME="sports-api"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# List available backups
list_backups() {
    log_info "Available backups on remote server:"
    echo ""

    ssh "${REMOTE_USER}@${REMOTE_HOST}" << 'EOF'
        backups=$(ls -dt /opt/sports-bet-ai-api-backup-* 2>/dev/null || true)
        if [ -z "$backups" ]; then
            echo "No backups found"
        else
            i=1
            for backup in $backups; do
                echo "[$i] $backup"
                i=$((i+1))
            done
        fi
EOF
    echo ""
}

# Perform rollback
rollback() {
    local backup_path=$1

    log_info "Starting rollback to: ${backup_path}"

    ssh "${REMOTE_USER}@${REMOTE_HOST}" << EOF
        set -e

        echo "Stopping service..."
        systemctl --user stop ${SERVICE_NAME} 2>/dev/null || true
        systemctl stop ${SERVICE_NAME} 2>/dev/null || true

        echo "Removing current deployment..."
        rm -rf ${REMOTE_PATH}

        echo "Restoring from backup..."
        cp -r ${backup_path}/sports-bet-ai-api ${REMOTE_PATH}

        echo "Starting service..."
        cd ${REMOTE_PATH}
        source venv/bin/activate || python3 -m venv venv && source venv/bin/activate

        # Try to restart as service
        if systemctl --user list-units | grep -q ${SERVICE_NAME}; then
            systemctl --user start ${SERVICE_NAME}
        elif systemctl list-units | grep -q ${SERVICE_NAME}; then
            systemctl start ${SERVICE_NAME}
        else
            # Manual start
            nohup uvicorn app.main:app --host 0.0.0.0 --port 8001 > /var/log/sports-api.log 2>&1 &
        fi

        echo "Rollback completed!"
EOF

    log_info "Rollback completed successfully"
}

# Verify rollback
verify_rollback() {
    log_info "Verifying rollback..."

    sleep 3

    if curl -s --max-time 10 "http://${REMOTE_HOST}:8001/api/health" | grep -q "healthy"; then
        log_info "✅ API is healthy after rollback"
    else
        log_warn "⚠️ API health check failed"
    fi
}

main() {
    log_info "Rollback Script for NBA Sports API"
    echo ""

    # List available backups
    list_backups

    # Get backup path from user
    if [ -z "$1" ]; then
        read -p "Enter backup path to restore (or full path): " backup_path
    else
        backup_path=$1
    fi

    if [ -z "$backup_path" ]; then
        log_error "No backup path specified"
        exit 1
    fi

    # Confirm rollback
    echo ""
    log_warn "This will rollback to: ${backup_path}"
    read -p "Continue? (y/N): " -n 1 -r
    echo ""

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Rollback cancelled"
        exit 0
    fi

    # Perform rollback
    rollback "$backup_path"
    verify_rollback

    echo ""
    log_info "Rollback completed!"
}

main "$@"
