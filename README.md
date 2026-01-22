# NBA Player Prop Prediction API

AI-powered NBA player prop predictions with injury tracking, lineup projections,
and parlay generation. Official NBA.com data integration with betting odds from bookmakers.

## Tech Stack

- **Python 3.12** with FastAPI
- **NBA API** (nba_api) for official NBA.com data
- **The Odds API** for betting odds from bookmakers
- **Firecrawl** for web scraping (Rotowire lineups, injury reports)
- **PostgreSQL** for database with SQLAlchemy ORM
- **Automated cron jobs** for data fetching

## Project Features

### Core Features
- **Player Prop Predictions**: AI-powered predictions for points, rebounds, assists, threes
- **Injury Tracking**: Real-time injury status from ESPN and NBA official reports
- **Lineup Projections**: Projected starting lineups and minutes allocations
- **Parlay Generation**: Same-game and multi-game parlays with corrected EV calculation
- **Bet Tracking**: Track placed bets and verify results against predictions
- **Accuracy Tracking**: Monitor prediction accuracy and model performance

### Advanced Features
- **Per-36 Stats**: Uses actual player efficiency instead of position averages
- **Minutes-Based Predictions**: `predicted_value = per_36_stat × (projected_minutes / 36)`
- **Injury-Aware**: Adjusts predictions based on injury status and return progression
- **Correlation Analysis**: Accounts for stat correlations within parlay legs
- **Odds Integration**: Real-time odds from FanDuel, DraftKings, etc.

## Project Structure

```
sports-bet-ai-api/
├── app/
│   ├── api/routes/
│   │   ├── predictions.py      # Prediction endpoints
│   │   ├── players.py           # Player endpoints
│   │   ├── odds.py              # Odds endpoints
│   │   ├── injuries.py          # Injury tracking endpoints
│   │   ├── lineups.py           # Lineup projection endpoints
│   │   ├── parlays.py           # Parlay generation endpoints
│   │   ├── bets.py              # Bet tracking endpoints
│   │   └── accuracy.py          # Accuracy tracking endpoints
│   ├── core/
│   │   └── database.py          # Database session management
│   ├── models/
│   │   └── models.py             # SQLAlchemy models
│   ├── services/
│   │   ├── nba_service.py        # NBA API integration
│   │   ├── odds_api_service.py   # The Odds API client
│   │   ├── prediction_service.py # Prediction generation (injury-aware)
│   │   ├── injury_service.py    # Injury tracking (ESPN + Firecrawl)
│   │   ├── lineup_service.py     # Lineup projections (Rotowire)
│   │   ├── parlay_service.py     # Parlay generation
│   │   └── bet_tracking_service.py # Bet tracking
│   ├── utils/
│   │   └── timezone.py          # Timezone utilities
│   └── main.py                   # FastAPI application
├── scripts/
│   ├── daily_odds_fetch.py      # Daily odds automation
│   ├── injury_fetch.py          # Injury data fetching
│   ├── lineup_fetch.py           # Lineup data fetching
│   └── resolve_predictions.py    # Result verification
├── migrations/
│   ├── 001_add_parlay_tables.sql
│   ├── 002_add_placed_bets.sql
│   ├── 003_add_injury_tables.sql
│   └── 004_add_lineup_tables.sql
└── models/                         # ML model storage
```

## Database Schema

### Core Tables

#### Player
**Table:** `players`

**Columns:**
- `id` - Column
- `external_id` - Column
- `id_source` - Column
- `name` - Column
- `team` - Column

#### Game
**Table:** `games`

**Columns:**
- `id` - Column
- `external_id` - Column
- `id_source` - Column
- `game_date` - Column
- `away_team` - Column

#### Prediction
**Table:** `predictions`

**Columns:**
- `id` - Column
- `player_id` - Column
- `game_id` - Column
- `stat_type` - Column

#### NewsEvent
**Table:** `news_events`

**Columns:**
- `id` - Column
- `external_id` - Column
- `headline` - Column
- `description` - Column
- `event_type` - Column
- `source` - Column
- `published_at` - Column

#### Parlay
**Table:** `parlays`

**Columns:**
- `id` - Column
- `parlay_type` - Column
- `calculated_odds` - Column
- `implied_probability` - Column
- `expected_value` - Column

#### ParlayLeg
**Table:** `parlay_legs`

**Columns:**
- `id` - Column
- `parlay_id` - Column
- `prediction_id` - Column
- `leg_order` - Column
- `selection` - Column

#### PlacedBet
**Table:** `placed_bets`

**Columns:**
- `id` - Column
- `sportsbook` - Column
- `bet_id` - Column
- `bet_type` - Column

#### PlacedBetLeg
**Table:** `placed_bet_legs`

**Columns:**
- `id` - Column
- `bet_id` - Column
- `player_name` - Column
- `player_team` - Column
- `stat_type` - Column

#### PlayerInjury
**Table:** `player_injuries`

**Columns:**
- `id` - Column
- `player_id` - Column
- `game_id` - Column
- `injury_type` - Column

#### ExpectedLineup
**Table:** `expected_lineups`

**Columns:**
- `id` - Column
- `game_id` - Column
- `team` - Column
- `player_id` - Column

### Service Layer

| Service | Purpose |
|---------|---------|
| PredictionService | Injury-aware predictions using per-36 stats |
| InjuryService | ESPN + Firecrawl injury data fetching |
| LineupService | Rotowire lineup projections |
| ParlayService | Parlay generation with corrected EV calculation |
| BetTrackingService | Track and verify placed bets |
| OddsApiService | The Odds API integration |
| NBAService | Official NBA.com data |

## API Endpoints

### Predictions
- `GET /api/predictions/player/{player_id}`
- `GET /api/predictions/player/nba/{nba_id}`
- `GET /api/predictions/game/{game_id}`
- `GET /api/predictions/game/nba/{nba_game_id}`
- `GET /api/predictions/top`
- `GET /api/predictions/recent`
- `GET /api/predictions/stat-types`
- `POST /api/predictions/generate/upcoming`
- `GET /api/nfl/predictions/player/{player_id}`
- `GET /api/nfl/predictions/top`

### Players
- `GET /api/players/search`
- `GET /api/players/{player_id}`
- `GET /api/players/nba/{nba_id}`
- `GET /api/players/nba/{nba_id}/predictions`
- `GET /api/players/`
- `GET /api/players/teams/list`

### Odds
- `GET /api/odds/quota`
- `POST /api/odds/fetch/game-odds`
- `POST /api/odds/fetch/player-props/{game_id}`
- `GET /api/odds/game/{game_id}`

### Injuries
- `GET /api/injuries/`
- `GET /api/injuries/player/{player_id}`
- `GET /api/injuries/context/{player_id}`
- `POST /api/injuries/fetch`
- `GET /api/injuries/stats/summary`

### Lineups
- `GET /api/lineups/game/{game_id}`
- `GET /api/lineups/player/{player_id}`
- `GET /api/lineups/player/{player_id}/minutes`
- `POST /api/lineups/fetch`
- `GET /api/lineups/team/{team}`
- `GET /api/lineups/stats/summary`

### Parlays
- `POST /api/parlays/generate/same-game/{game_id}`
- `POST /api/parlays/generate/multi-game`
- `GET /api/parlays/`
- `GET /api/parlays/top-ev`
- `GET /api/parlays/{parlay_id}`
- `GET /api/parlays/game/{game_id}`
- `DELETE /api/parlays/cleanup`
- `GET /api/parlays/stats/summary`

### Bets
- `POST /api/bets/`
- `GET /api/bets/`
- `GET /api/bets/summary`
- `GET /api/bets/{bet_id}`
- `PUT /api/bets/{bet_id}/result`

### Data
- `POST /api/nfl/data/fetch/players`
- `GET /api/nfl/data/status`
- `POST /api/data/fetch/upcoming`
- `POST /api/data/fetch/from-odds`
- `POST /api/data/fetch/players`
- `GET /api/data/status`
- `POST /api/data/clear-cache`
- `POST /api/data/fetch/single-game/{nba_game_id}`

### Accuracy
- `GET /api/accuracy/overall`
- `GET /api/accuracy/by-stat-type`
- `GET /api/accuracy/timeline`
- `GET /api/accuracy/drift-check`
- `GET /api/accuracy/best-worst`
- `GET /api/accuracy/by-player`
- `GET /api/accuracy/resolution-status`
- `GET /api/accuracy/unresolved-games`
- `POST /api/accuracy/resolve/{game_id}`
- `POST /api/accuracy/resolve-recent`

### Health
- `GET /api/nfl/health`


## VPS Setup

### SSH to VPS
```bash
ssh sean-ubuntu-vps
cd /opt/sports-bet-ai-api
```

### Environment Variables
Edit `.env` file:
```bash
THE_ODDS_API_KEY=your_api_key_here
DATABASE_URL=postgresql://postgres:password@localhost:5432/sports_betting
LOG_LEVEL=INFO
FIRECRAWL_API_KEY=your_key_here  # Optional, for Firecrawl
```

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

## Automated Systems

### Daily Odds Fetch (7:00 AM CST)
```bash
# Runs daily at 7:00 AM CST (1:00 PM UTC)
0 13 * * * cd /opt/sports-bet-ai-api && source venv/bin/activate && python scripts/daily_odds_fetch.py
```

### Injury Data Fetch (Every 2 hours)
```bash
# Even hours: 0, 2, 4, ...
0 */2 * * * cd /opt/sports-bet-ai-api && source venv/bin/activate && python scripts/injury_fetch.py
```

### Lineup Data Fetch (Every 4 hours)
```bash
# Every 4 hours: 0, 4, 8, ...
0 */4 * * * cd /opt/sports-bet-ai-api && source venv/bin/activate && python scripts/lineup_fetch.py
```

## Data Sources

| Source | Purpose | Rate Limit |
|--------|---------|------------|
| NBA API (nba_api) | Official NBA.com data | Can be strict with timeouts |
| The Odds API | Betting odds from bookmakers | 500 req/month free tier |
| ESPN API | Injury news and updates | ~1 req/sec recommended |
| Firecrawl | Web scraping (lineups, injuries) | Self-hosted |

## Bookmaker Priority

1. FanDuel (highest priority)
2. DraftKings
3. BetRivers
4. PointsBet
5. Unibet

## Recent Features

### Injury & Lineup Tracking (v2.1)
- Real-time injury status tracking from ESPN and NBA official reports
- Projected starting lineups from Rotowire
- Minutes projections for accurate predictions
- Injury-aware predictions that adjust for return-to-play status

### Parlay System (v2.2)
- Same-game and multi-game parlay generation
- Corrected EV calculation using odds-based probabilities
- Correlation analysis for parlay legs
- Multi-bookmaker parlay support

### Bet Tracking (v2.3)
- Track placed bets from FanDuel, DraftKings, etc.
- Result verification against predictions
- Profit/loss tracking
- Bet history and analytics

## API Documentation

Full API documentation available at: http://89.117.150.95:8001/docs

## License

MIT
