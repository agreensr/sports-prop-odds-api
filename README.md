# NBA Player Prop Prediction API - ESPN Integration Fixes

> Fixed version with ESPN ID lookup, timeout handling, and caching.

## 🏀 Overview

This API provides AI-powered NBA player prop predictions with ESPN data integration. This version includes critical fixes for player lookup errors and timeout issues.

## 📋 Fixes Implemented

| Issue | Fix | Status |
|-------|-----|--------|
| Player 404 error | Added `/api/predictions/player/espn/{espn_id}` endpoint | ✅ Fixed |
| fetch_upcoming timeout | 15s timeout with cached data fallback | ✅ Fixed |
| Player data missing | Player search endpoint with name matching | ✅ Fixed |
| No ESPN caching | 5-minute TTL cache for scoreboard data | ✅ Fixed |

## 🚀 Quick Start

### Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env

# Run the API
uvicorn app.main:app --host 0.0.0.0 --port 8001 --reload
```

### Docker Deployment

```bash
# Build image
docker build -t sports-api .

# Run container
docker run -p 8001:8001 --env-file .env sports-api
```

## 📡 API Endpoints

### Health & Status

```bash
# Basic health check
GET /health

# Detailed status with database counts
GET /api/health

# Data statistics
GET /api/data/status
```

### Player Endpoints (NEW)

```bash
# Search players by name (NEW - fixes 404 error)
GET /api/players/search?name=lebron

# Get player by ESPN ID (NEW)
GET /api/players/espn/2544

# Get player predictions by ESPN ID (NEW)
GET /api/predictions/player/espn/2544

# List all players with filters
GET /api/players?team=LAL&position=SF
```

### Prediction Endpoints

```bash
# Get predictions by database UUID
GET /api/predictions/player/{uuid}

# Get predictions by ESPN ID (NEW)
GET /api/predictions/player/espn/{espn_id}

# Get game predictions
GET /api/predictions/game/espn/{game_id}

# Get top picks by confidence
GET /api/predictions/top?min_confidence=0.7
```

### Data Fetching (FIXED)

```bash
# Fetch upcoming games with timeout protection (FIXED)
POST /api/data/fetch/upcoming
{
  "days_ahead": 7,
  "use_cache": true
}

# Fetch players from ESPN
POST /api/data/fetch/players?limit=1000
```

## 🔧 Clawdbot Skill

### Installation

```bash
# Copy skill to Clawdbot directory
cp -r clawdbot-skill/sports-api ~/.clawdbot/skills/

# Set environment variable
export SPORTS_API_URL="http://89.117.150.95:8001"

# Enable in clawdbot.json
# Add "sports-api": {"enabled": true} to skills.entries

# Restart Clawdbot
clawdbot gateway restart
```

### Usage

```bash
# Check API health
~/.clawdbot/skills/sports-api/scripts/sports_client.py health

# Search for player by name
~/.clawdbot/skills/sports-api/scripts/sports_client.py search lebron

# Get predictions by ESPN ID (NEW)
~/.clawdbot/skills/sports-api/scripts/sports_client.py player_espn 2544

# Fetch upcoming games (with timeout fix)
~/.clawdbot/skills/sports-api/scripts/sports_client.py fetch_upcoming 7
```

## 🧪 Testing

### Test ESPN Player Lookup

```bash
# Should return LeBron's predictions
curl "http://89.117.150.95:8001/api/predictions/player/espn/2544"
```

### Test fetch_upcoming Timeout

```bash
# Should complete within 15 seconds
curl -X POST "http://89.117.150.95:8001/api/data/fetch/upcoming" \
  -H "Content-Type: application/json" \
  -d '{"days_ahead": 7}'
```

### Test Player Search

```bash
# Should return player with ESPN ID
curl "http://89.117.150.95:8001/api/players/search?name=lebron"
```

## 📁 Project Structure

```
sports-bet-ai-api/
├── app/
│   ├── api/
│   │   └── routes/
│   │       ├── predictions.py    # ESPN ID lookup endpoint
│   │       ├── players.py        # Player search endpoint
│   │       └── data.py           # Timeout-fixed fetch_upcoming
│   ├── core/
│   │   ├── config.py             # Configuration settings
│   │   └── database.py           # Database session management
│   ├── models/
│   │   └── models.py             # SQLAlchemy models
│   ├── services/
│   │   └── espn_service.py       # ESPN API with caching
│   └── main.py                   # FastAPI application
├── clawdbot-skill/
│   └── sports-api/
│       ├── SKILL.md              # Skill metadata
│       └── scripts/
│           └── sports_client.py  # Updated CLI client
├── requirements.txt
├── .env.example
└── README.md
```

## 🗄️ Database Models

### Player
- `id`: UUID (primary key)
- `external_id`: ESPN player ID (indexed) - **Key for fixes**
- `name`, `team`, `position`

### Game
- `id`: UUID (primary key)
- `external_id`: ESPN event ID
- `game_date`, `away_team`, `home_team`, `status`

### Prediction
- `id`: UUID (primary key)
- `player_id`, `game_id` (foreign keys)
- `stat_type`, `predicted_value`, `recommendation`, `confidence`

## 🔒 Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | postgresql://... |
| `SPORTS_API_URL` | API base URL for Clawdbot | http://localhost:8001 |
| `ESPN_CACHE_TTL` | Cache time-to-live (seconds) | 300 |
| `ESPN_TIMEOUT` | ESPN API timeout (seconds) | 15.0 |
| `LOG_LEVEL` | Logging verbosity | INFO |

## 📊 ESPN API Endpoints Used

| Endpoint | Purpose | Cached |
|----------|---------|--------|
| `/apis/site/v2/sports/basketball/nba/scoreboard?dates=YYYYMMDD` | Get games | ✅ 5 min |
| `/apis/site/v2/sports/basketball/nba/summary?event={game_id}` | Box score | ✅ 5 min |
| `/apis/site/v3/sports/basketball/nba/athletes?limit=1000` | All players | ✅ 30 min |

## 🔄 Rollback Plan

If changes cause issues:

```bash
# Revert predictions.py changes
git checkout HEAD -- app/api/routes/predictions.py

# Remove new players endpoint
rm app/api/routes/players.py

# Restore original espn_service.py
git checkout HEAD -- app/services/espn_service.py

# Restart API
systemctl --user restart sports-api
```

## 📝 License

MIT
