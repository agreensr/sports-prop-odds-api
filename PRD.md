# Sports Betting AI API - Product Requirements Document

## 📋 Document Information

| Field | Value |
|-------|-------|
| **Version** | 2.0 |
| **Last Updated** | 2026-01-20 |
| **Status** | Active Development |
| **Product Focus** | Multi-Sport AI Betting Predictions |

---

## 🎯 Product Vision

**Sports Betting AI API** provides AI-powered player prop predictions for multiple sports with official league data integration. The API delivers betting insights with confidence scoring, odds pricing, and multi-league support through a unified REST interface and Telegram bot integration.

---

## 🏀 Core Features

### 1. Multi-Sport Support

| Sport | Status | Data Source | Features |
|-------|--------|-------------|----------|
| **NBA** | ✅ Production | NBA API (nba_api) | Player props, game predictions, odds |
| **NFL** | ✅ Implemented | nfl_data_py | Player props, game predictions, odds |
| **Future** | 🚧 Planned | MLB, NHL, Soccer | TBD |

### 2. AI-Powered Predictions

- **Player Props**: Points, rebounds, assists, threes (NBA), rushing, receiving, passing (NFL)
- **Confidence Scoring**: 0.0 - 1.0 scale with configurable thresholds
- **Recommendations**: Over/Under with reasoning
- **Odds Integration**: Bookmaker lines, pricing, implied probability

### 3. Data Integration

| Data Type | Source | Update Frequency |
|-----------|--------|-------------------|
| Player Data | Official League APIs | Daily |
| Game Schedule | Official League APIs | Hourly |
| Box Scores | Official League APIs | Live |
| Betting Odds | The Odds API | 10-15 minutes |

### 4. Bot Integration

**Platform**: Telegram (@seangai_bot)
- Natural language queries
- Sport-aware routing (NBA vs NFL)
- Quick predictions display
- Player search functionality

---

## 📡 API Architecture

### REST Endpoints

#### Health & Status
```
GET /health                              # Basic health check
GET /api/health                          # Detailed status with counts
GET /api/nfl/health                      # NFL service health
```

#### Players
```
GET /api/players                          # List all players
GET /api/players/search?name={name}      # Search by name
GET /api/predictions/player/{id}         # By database UUID
GET /api/nfl/players?season={year}       # NFL players
```

#### Predictions
```
GET /api/predictions/top                  # Top picks by confidence
GET /api/nfl/predictions/top             # NFL top picks
```

#### Data Management
```
POST /api/data/fetch/upcoming            # Fetch upcoming games
POST /api/nfl/data/fetch/players          # Fetch NFL players
GET /api/data/status                       # Database statistics
GET /api/nfl/data/status                   # NFL data status
```

#### Odds (Planned)
```
GET /api/odds/game/{game_id}             # Game odds
POST /api/odds/fetch/player-props         # Fetch player props
POST /api/predictions/update-odds         # Update predictions with odds
```

### Database Schema

```sql
-- Players (multi-sport)
CREATE TABLE players (
    id UUID PRIMARY KEY,
    external_id VARCHAR(50),               -- League player ID
    id_source VARCHAR(10) DEFAULT 'nba',   -- 'nba', 'nfl', etc.
    name VARCHAR(100),
    team VARCHAR(10),
    position VARCHAR(10),
    active BOOLEAN DEFAULT TRUE
);

-- Games (multi-sport)
CREATE TABLE games (
    id UUID PRIMARY KEY,
    external_id VARCHAR(50),
    id_source VARCHAR(10) DEFAULT 'nba',
    game_date TIMESTAMP,
    away_team VARCHAR(10),
    home_team VARCHAR(10),
    status VARCHAR(20)
);

-- Predictions
CREATE TABLE predictions (
    id UUID PRIMARY KEY,
    player_id UUID REFERENCES players(id),
    game_id UUID REFERENCES games(id),
    stat_type VARCHAR(20),
    predicted_value FLOAT,
    bookmaker_line FLOAT,
    bookmaker_name VARCHAR(50),
    recommendation VARCHAR(10),
    confidence FLOAT,
    model_version VARCHAR(20),
    over_price FLOAT,
    under_price FLOAT,
    implied_probability FLOAT
);
```

---

## 🤖 Telegram Bot Integration

### Architecture

```
User Query → @seangai_bot → Clawdbot Gateway
                                    ↓
                         Skill Router (ML-based)
                                    ↓
                    ┌───────────────┴───────────────┐
                    ↓                               ↓
              nba-api                        nfl-api
              (NBA only)                     (NFL only)
                    ↓                               ↓
            nba_client.py                 nfl_client.py
                    ↓                               ↓
              Sports API                    Sports API
              (Port 8001)                   (Port 8001)
```

### Skill Configuration

**nba-api**: NBA basketball predictions
- Commands: `bets`, `player <name>`, `search <name>`, `health`
- Description: "**NBA ONLY** - For NBA basketball predictions"

**nfl-api**: NFL football predictions
- Commands: `bets`, `player <name>`, `search <name>`, `status`
- Description: "**NFL FOOTBALL** - When user says NFL, football, etc."

### Model Configuration

| Setting | Value |
|---------|-------|
| **Primary Model** | `openrouter/z-ai/glm-4.5-air:free` |
| **Fallback Model** | `openrouter/moonshotai/kimi-k2:free` |
| **API Key** | Not required (free tier) |

---

## 🔧 Technical Stack

### Backend
- **Framework**: FastAPI 0.109+
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Python**: 3.10+
- **API Docs**: Auto-generated Swagger UI

### Data Sources
- **NBA**: `nba_api` Python library
- **NFL**: `nfl_data_py` with pandas
- **Odds**: The Odds API (planned)

### Bot Platform
- **Framework**: Clawdbot
- **Channel**: Telegram
- **AI Model**: OpenRouter (GLM-4.5, Kimi-K2)

### Deployment
- **Server**: Ubuntu VPS (89.117.150.95)
- **Port**: 8001
- **Process Manager**: systemd

---

## 📊 Success Metrics

### Technical Metrics
- API Response Time: < 500ms (p95)
- Error Rate: < 1%
- Bot Response Time: < 10 seconds
- Uptime: > 99%

### Business Metrics
- Prediction Accuracy: Track vs actual game results
- User Engagement: Telegram bot interactions
- Data Freshness: < 15 minutes for odds
- Sport Coverage: 2 sports (NBA, NFL)

---

## 🚧 Development Roadmap

### Phase 1: Foundation ✅ COMPLETE
- [x] NBA API integration
- [x] Player prop predictions
- [x] Database schema with multi-sport support
- [x] Basic bot integration
- [x] ESPN → NBA API migration

### Phase 2: NFL Support ✅ COMPLETE
- [x] NFL data service (nfl_data_py)
- [x] NFL API endpoints
- [x] nfl-api bot skill
- [x] Sport-aware routing
- [x] Script symlinks for path resolution

### Phase 3: Odds Integration 🚧 IN PROGRESS
- [ ] The Odds API integration
- [ ] Game odds endpoints
- [ ] Player props odds
- [ ] Odds update automation
- [ ] Bookmaker line tracking

### Phase 4: Enhanced Features 📋 PLANNED
- [ ] ML model training pipeline
- [ ] Historical accuracy tracking
- [ ] User predictions tracking
- [ ] Notification system
- [ ] Web dashboard

### Phase 5: Expansion 📋 FUTURE
- [ ] MLB integration
- [ ] NHL integration
- [ ] Soccer integration
- [ ] College sports
- [ ] Premium tier with advanced analytics

---

## 🔒 Security & Privacy

### Data Protection
- No personal data collection
- Anonymous usage analytics (planned)
- API key rotation support
- Rate limiting per endpoint

### API Security
- CORS configuration
- Input validation
- SQL injection prevention (ORM)
- Error handling without sensitive data leakage

---

## 📝 Change Log

### v2.0 (2026-01-20)
- ✅ Added NFL football support
- ✅ Created nfl-api bot skill
- ✅ Implemented sport-aware routing
- ✅ Added script symlinks for path resolution
- ✅ Configured model fallback (GLM-4.5 → Kimi-K2)

### v1.5 (2026-01-19)
- ✅ Migrated from ESPN to NBA API
- ✅ Fixed player lookup endpoints
- ✅ Added timeout handling
- ✅ Improved caching strategy

### v1.0 (2025-12-XX)
- ✅ Initial NBA API release
- ✅ Basic bot integration
- ✅ Core prediction endpoints

---

## 📞 Support & Contact

### Documentation
- API Docs: http://89.117.150.95:8001/docs
- Source Code: [GitHub Repository]

### Issues & Feature Requests
- Track issues in project repository
- Label: `enhancement` for features
- Label: `bug` for issues

---

## 📄 License

MIT License - See LICENSE file for details
