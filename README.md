# Sports Betting AI API

AI-powered player prop predictions for NBA, NFL, and more with injury tracking, lineup projections,
and parlay generation. Official league API integration with betting odds from bookmakers.

**🔔 IMPORTANT: Multi-Sport Architecture**

This codebase uses a **sport-specific directory structure** to support multiple sports. When adding new features, **ALWAYS** follow the sport-specific naming conventions documented below.

## Tech Stack

- **Python 3.11+** with FastAPI (modern `datetime.UTC` syntax)
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

**Multi-Sport Architecture:**

```
sports-bet-ai-api/
├── app/
│   ├── models/
│   │   ├── nba/models.py         # NBA-specific database models
│   │   ├── nfl/models.py         # NFL-specific models (future)
│   │   ├── mlb/models.py         # MLB-specific models (future)
│   │   └── nhl/models.py         # NHL-specific models (future)
│   │
│   ├── services/
│   │   ├── core/                 # Sport-agnostic services
│   │   │   ├── accuracy_service.py
│   │   │   ├── bet_tracking_service.py
│   │   │   ├── parlay_service.py
│   │   │   └── odds_api_service.py
│   │   ├── data_sources/         # External API clients
│   │   │   └── odds_mapper.py
│   │   ├── nba/                  # NBA-specific services
│   │   │   ├── nba_service.py
│   │   │   ├── prediction_service.py
│   │   │   ├── injury_service.py
│   │   │   ├── lineup_service.py
│   │   │   ├── nba_api_service.py
│   │   │   ├── historical_odds_service.py
│   │   │   └── boxscore_import_service.py
│   │   ├── nfl/                  # NFL-specific services
│   │   └── mlb/, nhl/            # Future sports
│   │
│   ├── api/routes/
│   │   ├── nba/                  # NBA endpoints
│   │   │   ├── predictions.py
│   │   │   ├── players.py
│   │   │   ├── data.py
│   │   │   ├── odds.py
│   │   │   ├── injuries.py
│   │   │   ├── lineups.py
│   │   │   ├── parlays.py
│   │   │   └── historical_odds.py
│   │   ├── nfl/                  # NFL endpoints
│   │   ├── shared/               # Sport-agnostic endpoints
│   │   │   ├── accuracy.py
│   │   │   └── bets.py
│   │   └── mlb/, nhl/            # Future sports
│   │
│   ├── core/
│   │   ├── database.py           # Database session management
│   │   └── config.py             # Configuration settings
│   ├── utils/
│   │   └── timezone.py           # Timezone utilities
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

### NBA Endpoints (`/api/nba/*`)

#### Predictions
- `GET /api/nba/predictions/player/{player_id}`
- `GET /api/nba/predictions/player/nba/{nba_id}`
- `GET /api/nba/predictions/game/{game_id}`
- `GET /api/nba/predictions/game/nba/{nba_game_id}`
- `GET /api/nba/predictions/top`
- `GET /api/nba/predictions/recent`
- `GET /api/nba/predictions/stat-types`
- `POST /api/nba/predictions/generate/upcoming`

#### Players
- `GET /api/nba/players/search`
- `GET /api/nba/players/{player_id}`
- `GET /api/nba/players/nba/{nba_id}`
- `GET /api/nba/players/nba/{nba_id}/predictions`
- `GET /api/nba/players/`
- `GET /api/nba/players/teams/list`

#### Odds
- `GET /api/nba/odds/quota`
- `POST /api/nba/odds/fetch/game-odds`
- `POST /api/nba/odds/fetch/player-props/{game_id}`
- `GET /api/nba/odds/game/{game_id}`

#### Injuries
- `GET /api/nba/injuries/`
- `GET /api/nba/injuries/player/{player_id}`
- `GET /api/nba/injuries/context/{player_id}`
- `POST /api/nba/injuries/fetch`
- `GET /api/nba/injuries/stats/summary`

#### Lineups
- `GET /api/nba/lineups/game/{game_id}`
- `GET /api/nba/lineups/player/{player_id}`
- `GET /api/nba/lineups/player/{player_id}/minutes`
- `POST /api/nba/lineups/fetch`
- `GET /api/nba/lineups/team/{team}`
- `GET /api/nba/lineups/stats/summary`

#### Parlays
- `POST /api/nba/parlays/generate/same-game/{game_id}`
- `POST /api/nba/parlays/generate/multi-game`
- `GET /api/nba/parlays/`
- `GET /api/nba/parlays/top-ev`
- `GET /api/nba/parlays/{parlay_id}`
- `GET /api/nba/parlays/game/{game_id}`
- `DELETE /api/nba/parlays/cleanup`
- `GET /api/nba/parlays/stats/summary`

#### Historical Odds
- `POST /api/nba/historical-odds/backfill`
- `GET /api/nba/historical-odds/stats`
- `POST /api/nba/historical-odds/capture/{game_id}`
- `POST /api/nba/historical-odds/resolve/{game_id}`

#### Data
- `POST /api/nba/data/fetch/upcoming`
- `POST /api/nba/data/fetch/from-odds`
- `POST /api/nba/data/fetch/players`
- `GET /api/nba/data/status`
- `POST /api/nba/data/clear-cache`
- `POST /api/nba/data/fetch/single-game/{nba_game_id}`

### NFL Endpoints (`/api/nfl/*`)
- `POST /api/nfl/api/nfl/data/fetch/players`
- `GET /api/nfl/api/nfl/data/status`
- `GET /api/nfl/api/nfl/health`
- `GET /api/nfl/api/nfl/predictions/player/{player_id}`
- `GET /api/nfl/api/nfl/predictions/top`

### Shared Endpoints (Sport-Agnostic)

#### Accuracy
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

#### Bets
- `POST /api/bets/`
- `GET /api/bets/`
- `GET /api/bets/summary`
- `GET /api/bets/{bet_id}`
- `PUT /api/bets/{bet_id}/result`

### Health
- `GET /health` - Basic health check
- `GET /api/health` - Detailed health with database stats

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
- `GET /health` - Basic health check
- `GET /api/health` - Detailed health with database stats

---

## 🚀 Development Guidelines

### **CRITICAL: Always Use Sport-Specific Naming**

This codebase is designed for **multi-sport support**. When adding new features, **NEVER** create sport-agnostic code in sport-specific areas.

### 📁 Decision Tree: Where Should My Code Go?

```
Is your feature specific to ONE sport (NBA, NFL, MLB, etc.)?
│
├─ YES → Put it in the sport's directory:
│   ├─ Models:     app/models/{sport}/models.py
│   ├─ Services:   app/services/{sport}/{feature}_service.py
│   └─ Routes:     app/api/routes/{sport}/{feature}.py
│
└─ NO → Put it in shared/core directories:
    ├─ Services:   app/services/core/{feature}_service.py
    └─ Routes:     app/api/routes/shared/{feature}.py
```

### ✅ DO: Sport-Specific Examples

**Adding NBA player prop feature:**
```python
# app/services/nba/player_prop_service.py  ✅ CORRECT
class NBAPlayerPropService:
    def get_nba_player_props(self, player_id: str):
        # NBA-specific logic here
        pass

# app/api/routes/nba/player_props.py  ✅ CORRECT
router = APIRouter(prefix="/player-props")
@router.get("/{player_id}")
async def get_player_props(player_id: str):
    pass
```

**Resulting URL:** `/api/nba/player-props/{player_id}`

### ❌ DON'T: Common Mistakes

```python
# app/services/player_prop_service.py  ❌ WRONG - Which sport?
# app/api/routes/player_props.py        ❌ WRONG - Ambiguous!

# app/services/nba/nba_player_prop_service.py  ❌ WRONG - Redundant "nba"
# app/services/nba_service.py                   ❌ WRONG - If not NBA-specific
```

### 📋 Import Convention

**Always use fully-qualified imports:**

```python
# ✅ CORRECT - Clear and explicit
from app.models.nba.models import Player, Game, Prediction
from app.services.nba.prediction_service import PredictionService
from app.services.core.accuracy_service import AccuracyService
from app.api.routes.nba import predictions as nba_predictions

# ❌ AVOID - Vague about which sport
from app.models.models import Player  # Old pattern, deprecated
from app.services.prediction_service import PredictionService
```

### 🏗️ Adding a New Sport

When adding support for MLB, NHL, or another sport:

1. **Create model directory:**
   ```bash
   mkdir -p app/models/mlb
   touch app/models/mlb/__init__.py
   touch app/models/mlb/models.py
   ```

2. **Create service directory:**
   ```bash
   mkdir -p app/services/mlb
   touch app/services/mlb/__init__.py
   # Add sport-specific services
   ```

3. **Create route directory:**
   ```bash
   mkdir -p app/api/routes/mlb
   touch app/api/routes/mlb/__init__.py
   # Add route files with prefix="/resource-name"
   ```

4. **Update main.py:**
   ```python
   from app.api.routes.mlb import predictions as mlb_predictions
   app.include_router(mlb_predictions.router, prefix="/api/mlb")
   ```

5. **Result:** URLs like `/api/mlb/predictions/top`

### 🎯 Examples by Category

| Feature Type | Sport-Specific? | Location | URL Pattern |
|--------------|-----------------|----------|-------------|
| NBA predictions | ✅ Yes | `app/api/routes/nba/predictions.py` | `/api/nba/predictions/*` |
| NFL injury tracking | ✅ Yes | `app/api/routes/nfl/injuries.py` | `/api/nfl/injuries/*` |
| Accuracy calculation | ❌ No | `app/api/routes/shared/accuracy.py` | `/api/accuracy/*` |
| Bet placement | ❌ No | `app/api/routes/shared/bets.py` | `/api/bets/*` |
| Odds API client | ❌ No | `app/services/core/odds_api_service.py` | N/A |
| MLB lineup projections | ✅ Yes | `app/services/mlb/lineup_service.py` | N/A |

### ⚠️ Before Committing

Ask yourself:
1. **Is this feature sport-specific?** → If yes, use sport directory
2. **Can this work for ANY sport?** → If yes, use shared/core
3. **Are my imports sport-qualified?** → Use `app.models.nba.models`, not `app.models.models`

---

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
DATABASE_URL=postgresql://postgres:nba_secure_pass_2026@localhost:5433/nba_props
LOG_LEVEL=INFO
FIRECRAWL_API_KEY=your_key_here  # Optional, for Firecrawl
```

### Database Access (pgAdmin)
Web-based database administration is available at:
- **URL**: http://89.117.150.95:5050
- **Email**: admin@example.com
- **Password**: nba_pgadmin_2026

To connect in pgAdmin:
1. Login with the credentials above
2. Click "Add New Server"
3. Name: "NBA Production"
4. Host: `nba-postgres` (Docker network) or `localhost:5433`
5. Username: `postgres`
6. Password: `nba_secure_pass_2026`
7. Database: `nba_props`

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
