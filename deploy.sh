#!/bin/bash
#####################################################################
# NBA Sports API - Deployment Script
# Deploys ESPN API integration fixes to remote server
#####################################################################

set -e  # Exit on error

# Configuration
REMOTE_HOST="sean-ubuntu-vps"
REMOTE_USER="sean"
REMOTE_PATH="/opt/sports-bet-ai-api"
SERVICE_NAME="sports-api"  # Service name stays the same (systemd)
BACKUP_DIR="/opt/sports-bet-ai-api-backup-$(date +%Y%m%d_%H%M%S)"
LOCAL_PATH="$(pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

#####################################################################
# Functions
#####################################################################

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

check_ssh() {
    log_info "Checking SSH connection to ${REMOTE_HOST}..."
    if ssh -o ConnectTimeout=10 "${REMOTE_USER}@${REMOTE_HOST}" "echo 'SSH OK'" > /dev/null 2>&1; then
        log_info "SSH connection successful"
        return 0
    else
        log_error "Cannot connect to ${REMOTE_HOST}"
        return 1
    fi
}

backup_remote_code() {
    log_info "Creating backup of remote code..."

    ssh "${REMOTE_USER}@${REMOTE_HOST}" << EOF
        # Stop the service
        systemctl --user stop ${SERVICE_NAME} 2>/dev/null || true
        systemctl stop ${SERVICE_NAME} 2>/dev/null || true

        # Create backup directory
        mkdir -p ${BACKUP_DIR}

        # Backup existing code
        if [ -d "${REMOTE_PATH}" ]; then
            cp -r ${REMOTE_PATH} ${BACKUP_DIR}/
            echo "Backup created at: ${BACKUP_DIR}"
        else
            echo "No existing code to backup"
            mkdir -p ${REMOTE_PATH}
        fi
EOF

    log_info "Backup completed"
}

deploy_files() {
    log_info "Deploying new files to remote server..."

    # Create remote directory structure
    ssh "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p ${REMOTE_PATH}/{app/{api/routes,core,models,services},clawdbot-skill/nba-api/scripts}"

    # Copy application files
    log_info "Copying application files..."
    scp app/main.py "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/app/main.py"
    scp app/core/config.py "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/app/core/config.py"
    scp app/core/database.py "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/app/core/database.py"
    scp app/models/models.py "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/app/models/models.py"

    # Copy service files
    log_info "Copying service files..."
    scp app/services/nba_service.py "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/app/services/nba_service.py"
    scp app/services/nfl_service.py "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/app/services/nfl_service.py"
    scp app/services/odds_api_service.py "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/app/services/odds_api_service.py"
    scp app/services/odds_mapper.py "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/app/services/odds_mapper.py"

    # Copy route files
    log_info "Copying route files..."
    scp app/api/routes/predictions.py "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/app/api/routes/predictions.py"
    scp app/api/routes/players.py "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/app/api/routes/players.py"
    scp app/api/routes/data.py "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/app/api/routes/data.py"
    scp app/api/routes/odds.py "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/app/api/routes/odds.py"
    scp app/api/routes/nfl.py "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/app/api/routes/nfl.py"

    # Copy __init__ files
    log_info "Copying package init files..."
    scp app/__init__.py "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/app/__init__.py"
    scp app/api/__init__.py "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/app/api/__init__.py"
    scp app/api/routes/__init__.py "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/app/api/routes/__init__.py"
    scp app/core/__init__.py "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/app/core/__init__.py"
    scp app/models/__init__.py "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/app/models/__init__.py"
    scp app/services/__init__.py "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/app/services/__init__.py"

    # Copy configuration files
    log_info "Copying configuration files..."
    scp requirements.txt "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/requirements.txt"
    scp .env.example "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/.env.example"

    # Copy Clawdbot skill
    log_info "Copying Clawdbot skill..."
    scp clawdbot-skill/nba-api/SKILL.md "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/clawdbot-skill/nba-api/SKILL.md"
    scp clawdbot-skill/nba-api/scripts/nba_client.py "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/clawdbot-skill/nba-api/scripts/nba_client.py"

    log_info "All files deployed"
}

install_dependencies() {
    log_info "Installing Python dependencies..."

    ssh "${REMOTE_USER}@${REMOTE_HOST}" << EOF
        cd ${REMOTE_PATH}

        # Create virtual environment if it doesn't exist
        if [ ! -d "venv" ]; then
            python3 -m venv venv
        fi

        # Activate virtual environment and install dependencies
        source venv/bin/activate
        pip install --upgrade pip
        pip install -r requirements.txt
EOF

    log_info "Dependencies installed"
}

check_env_file() {
    log_info "Checking environment file..."

    ssh "${REMOTE_USER}@${REMOTE_HOST}" << EOF
        cd ${REMOTE_PATH}

        if [ ! -f ".env" ]; then
            if [ -f ".env.example" ]; then
                cp .env.example .env
                echo "Created .env from .env.example"
                echo "Please update .env with your configuration"
            else
                echo "Warning: No .env file found"
            fi
        fi
EOF
}

restart_service() {
    log_info "Restarting service..."

    ssh "${REMOTE_USER}@${REMOTE_HOST}" << 'EOF'
        # Try user service first
        if systemctl --user is-active --quiet sports-api; then
            systemctl --user restart sports-api
            echo "User service restarted"
        # Try system service
        elif systemctl is-active --quiet sports-api; then
            systemctl restart sports-api
            echo "System service restarted"
        # Not running as service, try manual start
        else
            cd /opt/sports-bet-ai-api
            source venv/bin/activate
            nohup uvicorn app.main:app --host 0.0.0.0 --port 8001 > /var/log/sports-api.log 2>&1 &
            echo "Started manually (PID: $!)"
        fi
EOF

    # Wait for service to start
    log_info "Waiting for service to start..."
    sleep 5
}

verify_deployment() {
    log_info "Verifying deployment..."

    # Check health endpoint
    if curl -s --max-time 10 "http://${REMOTE_HOST}:8001/api/health" | grep -q "healthy"; then
        log_info "✅ API Health: OK"
    else
        log_warn "⚠️ API Health check failed or timeout"
    fi

    # Check odds endpoints
    log_info "Checking odds endpoints..."

    # Odds quota endpoint
    if curl -s --max-time 10 "http://${REMOTE_HOST}:8001/api/odds/quota" > /dev/null 2>&1; then
        log_info "✅ Odds quota endpoint: Available"
    else
        log_warn "⚠️ Odds quota endpoint: Not responding (may need API key)"
    fi

    # Predictions with odds endpoint
    if curl -s --max-time 10 "http://${REMOTE_HOST}:8001/api/odds/predictions/with-odds" > /dev/null 2>&1; then
        log_info "✅ Predictions with odds endpoint: Available"
    else
        log_warn "⚠️ Predictions with odds endpoint: Not responding"
    fi

    # Get endpoint list
    log_info "Fetching available endpoints..."
    curl -s --max-time 10 "http://${REMOTE_HOST}:8001/openapi.json" 2>/dev/null | \
        python3 -c "import sys, json; data = json.load(sys.stdin); paths = data.get('paths', {}); odds_paths = [p for p in paths.keys() if 'odds' in p]; print('\\n'.join(odds_paths))" 2>/dev/null || \
        echo "Could not fetch endpoint list"
}

print_summary() {
    echo ""
    echo "============================================"
    log_info "Deployment Summary"
    echo "============================================"
    echo ""
    echo "Remote Host: ${REMOTE_HOST}"
    echo "Remote Path: ${REMOTE_PATH}"
    echo "Backup Location: ${BACKUP_DIR}"
    echo ""
    echo "New Endpoints:"
    echo "  GET  /api/odds/quota"
    echo "  POST /api/odds/fetch/game-odds"
    echo "  POST /api/odds/fetch/player-props/{game_id}"
    echo "  POST /api/odds/predictions/update-odds"
    echo "  GET  /api/odds/game/{game_id}"
    echo "  GET  /api/odds/predictions/with-odds"
    echo ""
    echo "Test Commands:"
    echo "  curl \"http://${REMOTE_HOST}:8001/api/odds/quota\""
    echo "  curl -X POST \"http://${REMOTE_HOST}:8001/api/odds/fetch/game-odds?days_ahead=7\""
    echo "  curl \"http://${REMOTE_HOST}:8001/api/odds/predictions/with-odds?has_odds_only=true\""
    echo ""
    echo "To rollback if needed:"
    echo "  systemctl stop ${SERVICE_NAME}"
    echo "  rm -rf ${REMOTE_PATH}"
    echo "  cp -r ${BACKUP_DIR}/sports-bet-ai-api ${REMOTE_PATH}"
    echo "  systemctl start ${SERVICE_NAME}"
    echo ""
}

#####################################################################
# Main Deployment Flow
#####################################################################

main() {
    log_info "Starting deployment of NBA Sports API fixes..."

    # Check prerequisites
    if ! check_ssh; then
        log_error "Deployment aborted: Cannot connect to remote server"
        exit 1
    fi

    # Ask for confirmation
    echo ""
    log_warn "This will deploy code to ${REMOTE_HOST}:${REMOTE_PATH}"
    echo "A backup will be created at: ${BACKUP_DIR}"
    echo ""
    read -p "Continue? (y/N): " -n 1 -r
    echo ""

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Deployment cancelled"
        exit 0
    fi

    # Deployment steps
    backup_remote_code
    deploy_files
    install_dependencies
    check_env_file
    restart_service
    verify_deployment
    print_summary

    log_info "Deployment completed!"
}

# Run main function
main
