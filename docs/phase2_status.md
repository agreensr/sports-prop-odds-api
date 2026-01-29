# Phase 2: Data Source Integration - Implementation Status

**Status**: ✅ COMPLETE

**Last Updated**: 2026-01-27

---

## Overview

Phase 2 establishes the data source integration layer for the multi-sport betting prediction system. This phase focuses on integrating ESPN API and ensuring sport-specific adapters are in place for NFL, MLB, and NHL.

---

## Completed Files

### Core Services (1 file)

| File | Status | Description |
|------|--------|-------------|
| `app/services/core/espn_service.py` | ✅ Created | ESPN API client for news, scores, teams, rosters |

### Sport-Specific Adapters (3 files)

| File | Status | Description |
|------|--------|-------------|
| `app/services/nfl/nfl_adapter.py` | ✅ Created | NFL data adapter (32 teams, ESPN integration) |
| `app/services/mlb/mlb_adapter.py` | ✅ Created | MLB data adapter (30 teams, ESPN integration) |
| `app/services/nhl/nhl_adapter.py` | ✅ Created | NHL data adapter (32 teams, ESPN integration) |

### Existing Services

| Service | Status | Notes |
|---------|--------|-------|
| `app/services/nba/injury_service.py` | ✅ Already Hybrid | Uses ESPN API + Firecrawl for injury data |

---

## Architecture

### Data Source Hierarchy

```
┌─────────────────────────────────────────────────────────────┐
│                     DATA SOURCES                            │
├─────────────────────────────────────────────────────────────┤
│  PRIMARY:   The Odds API (games, odds, player props)       │
│  SECONDARY: ESPN API (news, scores, teams, rosters)         │
│  SECONDARY: Firecrawl (official injury reports, lineups)     │
│  TERTIARY:  Sport APIs (nba_api, nfl_data_py, etc.)         │
└─────────────────────────────────────────────────────────────┘
```

### ESPN API Service

**Endpoints Implemented**:
- `get_news(sport_id)` - Recent news articles
- `get_daily_injuries(sport_id)` - Injury-related news
- `get_scores(sport_id, date)` - Game scores for specific date
- `get_teams(sport_id)` - All teams for a sport
- `get_team_roster(sport_id, team_id)` - Team roster
- `get_player_stats(sport_id, player_id)` - Player statistics

**Sports Supported**:
- `nba` - basketball/nba
- `nfl` - football/nfl
- `mlb` - baseball/mlb
- `nhl` - hockey/nhl

**Features**:
- Async HTTP client with connection pooling
- 5-minute cache TTL (configurable)
- Error handling and logging
- Sport-agnostic interface

### Sport-Specific Adapters

All adapters follow the same pattern:
- `fetch_games(lookback_days, lookahead_days, season)` - Fetch games
- `fetch_teams()` - Fetch teams
- `fetch_roster(team_id, espn_team_id)` - Fetch roster
- `_normalize_game(game)` - Transform to standard format
- `_get_season_from_date(game_date)` - Sport-specific season logic
- `get_team_abbreviation(team_name)` - Team name → abbreviation

**NFL Adapter**:
- Season: Sept - Feb
- Teams: 32
- Season Logic: Jan/Feb games = previous year's season
- Example: Feb 2026 game = 2025 season

**MLB Adapter**:
- Season: Mar - Oct (Apr+ regular season)
- Teams: 30
- Season Logic: Apr+ = current year, Jan-Mar = current season
- Example: Mar 2026 game = 2026 season

**NHL Adapter**:
- Season: Oct - Jun
- Teams: 32
- Season Logic: Oct+ = current year, Jan-Sep = previous season
- Example: Jan 2026 game = 2025 season

### Hybrid Injury Service (Existing)

**Already Implemented** in `app/services/nba/injury_service.py`:

**ESPN API** (Structured):
- News articles with injury-related keywords
- Fast, reliable
- 30-minute cache TTL
- ~50 articles per fetch

**Firecrawl** (HTML Scrape):
- Official NBA injury report
- Full HTML page scraping
- 1-hour cache TTL
- Parses structured injury data

**Together**:
- ESPN provides rapid injury news
- Firecrawl provides official reports
- Data merged and stored in `player_injuries` table
- Used for prediction adjustments

---

## Usage Examples

### ESPN API Service

```python
from app.services.core.espn_service import ESPNApiService

service = ESPNApiService()

# Get news
news = await service.get_news('nba', limit=20)

# Get scores for a date
scores = await service.get_scores('nba', '20260127')

# Get teams
teams = await service.get_teams('nba')

# Get roster
roster = await service.get_team_roster('nba', team_id='1')

# Close client
await service.close()
```

### Sport-Specific Adapters

```python
from app.services.nfl.nfl_adapter import get_nfl_adapter

adapter = get_nfl_adapter(db)

# Fetch games
games = await adapter.fetch_games(lookback_days=7, lookahead_days=14)

# Fetch teams
teams = await adapter.fetch_teams()

# Fetch roster
roster = await adapter.fetch_roster(team_id='DAL', espn_team_id='1')
```

---

## Key Design Decisions

### 1. ESPN as Secondary Source

**Rationale**:
- The Odds API is primary for betting data (games, odds, props)
- ESPN fills gaps (news, scores, teams, rosters)
- ESPN is reliable, well-documented, and stable

### 2. Async Pattern

**Rationale**:
- Network I/O is async-friendly
- Allows concurrent requests
- Better performance for batch operations

### 3. Caching Strategy

**Rationale**:
- ESPN API has no official rate limits, but be respectful
- 5-minute TTL for fast-changing data (news, scores)
- 1-hour TTL for slow-changing data (teams, rosters)
- Reduces API calls and improves response time

### 4. Sport-Specific Season Logic

**Rationale**:
- Each sport has different season boundaries
- NFL: Jan/Feb = previous season
- MLB: Jan-Mar = current season (spring training)
- NHL: Jan-Sep = previous season
- Important for accurate data organization

---

## Testing

### ESPN API Service Tests

```bash
# Test ESPN service
python tests/test_espn_service.py
```

Expected coverage:
- Fetch news for each sport
- Fetch scores for specific date
- Fetch teams for each sport
- Fetch rosters
- Test error handling

### Sport Adapter Tests

```bash
# Test NFL adapter
python tests/test_nfl_adapter.py

# Test MLB adapter
python tests/test_mlb_adapter.py

# Test NHL adapter
python tests/test_nhl_adapter.py
```

Expected coverage:
- Fetch games (normalized format)
- Fetch teams (normalized format)
- Fetch rosters (normalized format)
- Team abbreviation lookup
- Season date calculation

---

## Data Flow

### News + Injuries

```
1. ESPN API → News articles (structured JSON)
2. Filter for injury keywords
3. Store in player_injuries table
4. Firecrawl → Official injury report (HTML)
5. Parse and merge with ESPN data
6. Used for prediction adjustments
```

### Games + Teams

```
1. Sport Adapter → ESPN API → Games/Teams
2. Normalize to standard format
3. Resolve identity via IdentityResolver (Phase 1)
4. Store in games/players tables
5. Used for predictions
```

---

## Next Steps (Phase 3)

Phase 2 establishes data source integration. Phase 3 will focus on:

| Task | File | Status |
|------|------|--------|
| Single Bet Service | `app/services/core/single_bet_service.py` | ⏳ Pending |
| Single Bets API | `app/api/routes/shared/single_bets.py` | ⏳ Pending |
| Daily Generation Script | `scripts/generate_single_bets.py` | ⏳ Pending |

**Target**: 10 single bets daily with min 60% confidence, min 5% edge

---

## Success Criteria

| Criterion | Status |
|-----------|--------|
| ESPN API service implemented | ✅ Complete |
| NFL adapter implemented | ✅ Complete |
| MLB adapter implemented | ✅ Complete |
| NHL adapter implemented | ✅ Complete |
| Hybrid injury service verified | ✅ Already Complete |
| All adapters follow same pattern | ✅ Complete |
| Team abbreviation mappings | ✅ Complete (all 4 sports) |

---

## Performance Considerations

### ESPN API Rate Limits

- No official limits, but be respectful
- Use caching to minimize requests
- Batch requests when possible
- Handle errors gracefully

### Concurrent Requests

- Async client allows concurrent requests
- Connection pooling (5 keepalive, 10 max)
- Timeout: 30 seconds
- Appropriate for batch operations

### Cache Strategy

- News/Scores: 5 minutes (fast-changing)
- Teams/Rosters: 1 hour (slow-changing)
- Reduces API load
- Improves response time

---

## Files Modified/Created Summary

**Created**: 4 files
- 1 core service (ESPN API)
- 3 sport adapters (NFL, MLB, NHL)

**Modified**: 0 files (verified existing injury service)

**Total Lines Added**: ~1,500 lines

---

**Phase 2 Status: ✅ COMPLETE**

Ready to proceed to Phase 3: Single Bet Service
