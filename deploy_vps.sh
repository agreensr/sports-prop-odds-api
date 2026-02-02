#!/bin/bash
#####################################################################
# NBA Sports API - Updated Deployment Script
# Matches current codebase structure
#####################################################################

set -e

REMOTE_HOST="sean-ubuntu-vps"
REMOTE_USER="sean"
REMOTE_PATH="sports-bet-ai-api"  # Relative to home directory
SERVICE_NAME="sports-api"

echo "========================================"
echo "  Deploying to VPS"
echo "========================================"
echo "Host: $REMOTE_HOST"
echo "Path: $REMOTE_PATH"
echo ""

# Step 1: Stop existing service
echo "Stopping existing service..."
ssh "${REMOTE_USER}@${REMOTE_HOST}" << 'ENDSSH'
pkill -9 -f "uvicorn app.main:app" 2>/dev/null || true
sleep 2
echo "Service stopped"
ENDSSH

# Step 2: Create remote directory
echo "Creating remote directory..."
ssh "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p ~/$REMOTE_PATH"

# Step 3: Deploy files
echo "Deploying files..."

# Core files
rsync -avz --exclude='__pycache__' --exclude='*.pyc' --exclude='.pytest_cache' \
  app/ "${REMOTE_USER}@${REMOTE_HOST}:~/${REMOTE_PATH}/app/"

# Scripts
rsync -avz scripts/ "${REMOTE_USER}@${REMOTE_HOST}:~/${REMOTE_PATH}/scripts/"

# Migrations
rsync -avz migrations/ "${REMOTE_USER}@${REMOTE_HOST}:~/${REMOTE_PATH}/migrations/"

# Config files
scp requirements.txt "${REMOTE_USER}@${REMOTE_HOST}:~/${REMOTE_PATH}/"
scp pytest.ini "${REMOTE_USER}@${REMOTE_HOST}:~/${REMOTE_PATH}/" 2>/dev/null || true

echo "Files deployed"

# Step 4: Install dependencies
echo "Installing dependencies..."
ssh "${REMOTE_USER}@${REMOTE_HOST}" << 'ENDSSH'
cd ~/sports-bet-ai-api

# Create virtual environment if needed
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi

# Activate and install
source venv/bin/activate
pip install --upgrade pip >/dev/null 2>&1
pip install -r requirements.txt
echo "Dependencies installed"
ENDSSH

# Step 5: Create startup script and start service
echo "Creating startup script..."
ssh "${REMOTE_USER}@${REMOTE_HOST}" << 'ENDSSH'
cat > ~/sports-bet-ai-api/start_api.sh << 'EOF'
#!/bin/bash
cd ~/sports-bet-ai-api
source venv/bin/activate

# Load .env file if it exists
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
fi

# Start uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
EOF

chmod +x ~/sports-bet-ai-api/start_api.sh

# Kill existing processes
pkill -9 -f "uvicorn app.main:app" 2>/dev/null || true
sudo lsof -ti:8001 2>/dev/null | xargs -r sudo kill -9 2>/dev/null || true
sleep 2

# Start service via script
nohup bash ~/sports-bet-ai-api/start_api.sh > ~/sports-bet-ai-api/uvicorn.log 2>&1 &
echo "Service started (PID: $!)"
ENDSSH

# Step 6: Wait and verify
echo ""
echo "Waiting for service to start..."
sleep 5

echo ""
echo "========================================"
echo "  Deployment Complete!"
echo "========================================"
echo ""
echo "Service URL: http://${REMOTE_HOST}:8001"
echo "Docs URL: http://${REMOTE_HOST}:8001/docs"
echo ""
echo "Checking health..."
sleep 3
curl -s --max-time 10 "http://${REMOTE_HOST}:8001/docs" >/dev/null 2>&1 && echo "✅ Service is responding!" || echo "⚠️ Service may not be responding yet"
echo ""
echo "To view logs:"
echo "  ssh ${REMOTE_USER}@${REMOTE_HOST} 'tail -f ~/sports-bet-ai-api/uvicorn.log'"
