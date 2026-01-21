# NBA Player Prop Prediction API

AI-powered NBA player prop predictions using recent game averages with betting odds integration.

## Tech Stack

- **Python 3.12** with FastAPI
- **NBA API** (nba_api) for official NBA.com data
- **The Odds API** for betting odds from bookmakers
- **PostgreSQL** for database
- **Automated cron jobs** for daily data fetching

## Project Structure

```
sports-bet-ai-api/
├── app/
│   ├── api/
│   │   └── routes/
│   │       ├── predictions.py    # Prediction endpoints
│   │       ├── players.py        # Player endpoints
│   │       ├── data.py           # Data fetching endpoints
│   │       └── odds.py           # Odds endpoints
│   ├── core/
│   │   └── database.py            # Database session management
│   ├── ml/
│   │   ├── features.py            # Feature engineering
│   │   └── training.py            # Training pipeline
│   ├── models/
│   │   └── models.py             # SQLAlchemy models (Game, Player, Prediction, PlayerStats, GameOdds)
│   ├── services/
│   │   ├── nba_service.py        # NBA API integration
│   │   ├── odds_api_service.py   # The Odds API client
│   │   ├── odds_mapper.py        # Data transformation
│   │   └── prediction_service.py # Prediction generation
│   └── main.py                    # FastAPI application
├── scripts/
│   ├── daily_odds_fetch.py      # Daily automation (7am CST)
│   ├── automated_stat_import.py # Stat import automation
│   └── export_training_data.py  # Data export
└── models/                         # ML model storage
```

## VPS Setup

### SSH to VPS
```bash
ssh sean-ubuntu-vps
cd /opt/sports-bet-ai-api
```

### Environment Variables
Edit `.env` file:
```
THE_ODDS_API_KEY=your_api_key_here
DATABASE_URL=postgresql://postgres:password@localhost:5432/sports_betting
LOG_LEVEL=INFO
```

## Automated Systems

### Daily Odds Fetch (7:00 AM CST)

Automated script that:
1. Fetches upcoming games from The Odds API (next 2-3 days)
2. Generates predictions for games without them
3. Fetches player props odds for games within 2 hours of start

**Cron Schedule:**
```bash
# Runs daily at 7:00 AM CST (1:00 PM UTC)
0 13 * * * cd /opt/sports-bet-ai-api && source venv/bin/activate && python scripts/daily_odds_fetch.py
```

**API Usage:** ~20 requests/day (well within 1500 request free tier)

### Stat Import Automation

**Cron Jobs:**
```bash
# Daily stat import at 6 AM UTC (previous day's games)
0 6 * * * cd /opt/sports-bet-ai-api && source venv/bin/activate && python scripts/automated_stat_import.py --daily

# Weekly roster update (Sundays at 7 AM UTC)
0 7 * * 0 cd /opt/sports-bet-ai-api && source venv/bin/activate && python scripts/automated_stat_import.py --roster --limit 500

# Recent game logs refresh (Tuesdays at 8 AM UTC)
0 8 * * 2 cd /opt/sports-bet-ai-api && source venv/bin/activate && python scripts/automated_stat_import.py --recent 7 --limit 200
```

## Data Sources

### NBA API (nba_api)
- **Purpose:** Official NBA.com data (players, games, stats)
- **Usage:** Player rosters, game schedules, box scores
- **Rate Limit:** Can be strict with 30s timeouts

### The Odds API
- **Purpose:** Betting odds from bookmakers
- **Bookmakers:** FanDuel, DraftKings, BetRivers, PointsBet, Unibet
- **Player Props:** points, rebounds, assists, threes
- **Free Tier:** 500 requests/month (~16/day)

**Important Notes:**
- The Odds API has a 10-minute offset bug - corrected automatically
- Player props only posted 12-24 hours before game time
- Odds fetched within 2 hours of game start to ensure availability

## Bookmaker Priority

1. FanDuel (highest priority)
2. DraftKings
3. BetRivers
4. PointsBet
5. Unibet

## Running the API

### Development Server
```bash
cd /opt/sports-bet-ai-api
source venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

### Production
```bash
# Run with environment variables
export THE_ODDS_API_KEY=your_key
uvicorn app.main:app --host 0.0.0.0 --port 8001
```

## API Endpoints

### Predictions
- `POST /api/predictions/generate` - Generate predictions for a game
- `GET /api/predictions/game/{game_id}` - Get predictions for a game
- `GET /api/predictions/player/nba/{nba_id}` - Get predictions by NBA ID
- `GET /api/predictions/with-odds` - Get predictions with odds pricing

### Data
- `POST /api/data/fetch/upcoming` - Fetch upcoming games from NBA API
- `POST /api/data/fetch/from-odds` - Fetch games from The Odds API
- `GET /api/data/status` - Get system status

### Odds
- `POST /api/odds/fetch/game-odds` - Fetch game odds (moneyline, spread, totals)
- `POST /api/odds/fetch/player-props/{game_id}` - Fetch player props for a game
- `POST /api/odds/predictions/update-odds` - Update predictions with odds
- `GET /api/odds/quota` - Check remaining API quota

### Health Check
- `GET /api/health` - System health and statistics

## Prediction Model

**Current Approach:** Recent game averages with position-based fallback

- **Primary:** Average of last 10 games (minimum 3 games required)
- **Fallback:** Position-based averages (PG, SG, SF, PF, C)
- **Variation:** ±3% on recent averages for realism

**Model Versions:**
- `recent_avg_v2.0` - Actual recent stats
- `position_average_v1.0` - Position fallback

## Database Schema

### Games Table
- `id` - Internal UUID
- `external_id` - NBA.com or Odds API game ID
- `id_source` - Data source (nba, odds_api)
- `game_date` - Game time (UTC)
- `away_team`, `home_team` - 3-letter abbreviations
- `season` - NBA season year
- `status` - scheduled, in_progress, final

### Players Table
- `id` - Internal UUID
- `external_id` - NBA.com player ID
- `name` - Full name
- `team` - 3-letter abbreviation
- `position` - PG, SG, SF, PF, C, G, F
- `active` - Boolean

### Predictions Table
- `predicted_value` - AI prediction
- `bookmaker_line` - Bookmaker over/under line
- `bookmaker_name` - FanDuel, DraftKings, etc.
- `over_price`, `under_price` - American odds
- `confidence` - Confidence score (0.35-0.75)
- `recommendation` - OVER, UNDER, or NONE

## Time Zone Notes

- **Database Storage:** UTC
- **Display:** Central Time (CST, UTC-6)
- **The Odds API Correction:** -10 minutes applied to fix API bug

## License

MIT
