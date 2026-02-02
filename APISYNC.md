# Product Requirements Document: NBA Data Sync Service

## API Synchronization Layer for NBA.com & The Odds API

**Version:** 1.0  
**Date:** January 2025  
**Status:** Draft  
**Owner:** Engineering Team

---

## 1. Executive Summary

### Problem Statement
The current system pulls data from two independent sources (nba_api for stats, The Odds API for betting lines) without any correlation mechanism. This creates a critical data integrity issue where predictions may be based on mismatched or unvalidated data pairs.

### Solution Overview
Build a synchronization layer that maps, normalizes, and validates data between both APIs, ensuring predictions are always based on correctly correlated game and player data.

---

## 2. Goals & Success Metrics

### Primary Goals
| Goal | Description |
|------|-------------|
| **Data Integrity** | 100% of predictions use verified, matched data pairs |
| **Reliability** | Automated sync with failure detection and alerting |
| **Traceability** | Full audit trail of data lineage for any prediction |

### Success Metrics
- **Match Rate:** >98% of games successfully mapped between APIs
- **Player Match Rate:** >99% of player names resolved correctly
- **Sync Freshness:** Data updated within 5 minutes of source changes
- **Error Rate:** <0.1% undetected mismatches in production

---

## 3. Technical Architecture

### High-Level System Design

```
┌─────────────────────────────────────────────────────────────────────┐
│                        SYNC ORCHESTRATOR                            │
│                    (Scheduler + Coordinator)                        │
└─────────────────────┬───────────────────────────┬───────────────────┘
                      │                           │
                      ▼                           ▼
         ┌────────────────────┐       ┌────────────────────┐
         │    nba_api_sync    │       │   odds_api_sync    │
         │    (Stats Data)    │       │   (Betting Lines)  │
         └─────────┬──────────┘       └─────────┬──────────┘
                   │                            │
                   ▼                            ▼
         ┌────────────────────────────────────────────────┐
         │              MATCHING ENGINE                    │
         │  ┌──────────────┐  ┌────────────────────────┐  │
         │  │ Game Matcher │  │ Player Name Resolver   │  │
         │  └──────────────┘  └────────────────────────┘  │
         └────────────────────────┬───────────────────────┘
                                  │
                                  ▼
         ┌────────────────────────────────────────────────┐
         │              UNIFIED DATA STORE                 │
         │  ┌──────────────────┐  ┌────────────────────┐  │
         │  │  game_mappings   │  │  player_aliases    │  │
         │  ├──────────────────┤  ├────────────────────┤  │
         │  │  sync_metadata   │  │  match_audit_log   │  │
         │  └──────────────────┘  └────────────────────┘  │
         └────────────────────────────────────────────────┘
                                  │
                                  ▼
         ┌────────────────────────────────────────────────┐
         │            PREDICTION SERVICE                   │
         │         (Consumes validated data only)          │
         └────────────────────────────────────────────────┘
```

---

## 4. Database Schema Design

### 4.1 Game Mappings Table

```sql
CREATE TABLE game_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- NBA.com identifiers
    nba_game_id VARCHAR(20) NOT NULL,
    nba_home_team_id INTEGER NOT NULL,
    nba_away_team_id INTEGER NOT NULL,
    
    -- Odds API identifiers
    odds_event_id VARCHAR(64),
    odds_sport_key VARCHAR(32) DEFAULT 'basketball_nba',
    
    -- Matching metadata
    game_date DATE NOT NULL,
    game_time TIMESTAMP WITH TIME ZONE,
    match_confidence DECIMAL(5,4) NOT NULL, -- 0.0000 to 1.0000
    match_method VARCHAR(32) NOT NULL, -- 'exact', 'fuzzy', 'manual'
    
    -- Status tracking
    status VARCHAR(16) DEFAULT 'pending', -- pending, matched, unmatched, manual_review
    last_validated_at TIMESTAMP WITH TIME ZONE,
    
    -- Audit
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    
    UNIQUE(nba_game_id),
    UNIQUE(odds_event_id)
);

CREATE INDEX idx_game_mappings_date ON game_mappings(game_date);
CREATE INDEX idx_game_mappings_status ON game_mappings(status);
```

### 4.2 Player Aliases Table

```sql
CREATE TABLE player_aliases (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- Canonical reference (NBA.com is source of truth)
    nba_player_id INTEGER NOT NULL,
    canonical_name VARCHAR(128) NOT NULL,
    
    -- Alternate names from various sources
    alias_name VARCHAR(128) NOT NULL,
    alias_source VARCHAR(32) NOT NULL, -- 'odds_api', 'manual', 'auto_detected'
    
    -- Matching metadata
    match_confidence DECIMAL(5,4) NOT NULL,
    is_verified BOOLEAN DEFAULT FALSE,
    
    -- Audit
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    verified_by VARCHAR(64),
    verified_at TIMESTAMP WITH TIME ZONE,
    
    UNIQUE(alias_name, alias_source)
);

CREATE INDEX idx_player_aliases_canonical ON player_aliases(canonical_name);
CREATE INDEX idx_player_aliases_alias ON player_aliases(alias_name);
CREATE INDEX idx_player_aliases_nba_id ON player_aliases(nba_player_id);
```

### 4.3 Team Mappings Table

```sql
CREATE TABLE team_mappings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    -- NBA.com reference
    nba_team_id INTEGER NOT NULL UNIQUE,
    nba_abbreviation VARCHAR(3) NOT NULL,
    nba_full_name VARCHAR(64) NOT NULL,
    nba_city VARCHAR(32) NOT NULL,
    
    -- Odds API variations
    odds_api_name VARCHAR(64),
    odds_api_key VARCHAR(32),
    
    -- Common variations for fuzzy matching
    alternate_names JSONB DEFAULT '[]',
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### 4.4 Sync Metadata Table

```sql
CREATE TABLE sync_metadata (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    source VARCHAR(32) NOT NULL, -- 'nba_api', 'odds_api'
    data_type VARCHAR(32) NOT NULL, -- 'games', 'players', 'odds', 'stats'
    
    last_sync_started_at TIMESTAMP WITH TIME ZONE,
    last_sync_completed_at TIMESTAMP WITH TIME ZONE,
    last_sync_status VARCHAR(16), -- 'success', 'partial', 'failed'
    
    records_processed INTEGER DEFAULT 0,
    records_matched INTEGER DEFAULT 0,
    records_failed INTEGER DEFAULT 0,
    
    error_message TEXT,
    sync_duration_ms INTEGER,
    
    UNIQUE(source, data_type)
);
```

### 4.5 Match Audit Log Table

```sql
CREATE TABLE match_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    
    entity_type VARCHAR(16) NOT NULL, -- 'game', 'player'
    entity_id VARCHAR(64) NOT NULL,
    
    action VARCHAR(16) NOT NULL, -- 'auto_matched', 'manual_matched', 'unmatched', 'updated'
    previous_state JSONB,
    new_state JSONB,
    
    match_details JSONB, -- algorithm used, scores, etc.
    performed_by VARCHAR(64), -- 'system' or user ID
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX idx_audit_entity ON match_audit_log(entity_type, entity_id);
CREATE INDEX idx_audit_created ON match_audit_log(created_at);
```

---

## 5. Component Specifications

### 5.1 Game Matching Engine

**Purpose:** Match games between NBA.com and Odds API

**Matching Algorithm:**
```
PRIORITY 1: Exact Match
├── Same date (UTC adjusted)
├── Home team matches (via team_mappings)
└── Away team matches (via team_mappings)
    → Confidence: 1.0

PRIORITY 2: Fuzzy Time Match
├── Same date
├── Teams match
└── Start time within 2 hours
    → Confidence: 0.95

PRIORITY 3: Team Name Fuzzy Match
├── Same date
├── Levenshtein distance < 3 on team names
└── No conflicting games
    → Confidence: 0.85

PRIORITY 4: Manual Review Queue
├── Same date
├── Partial team match OR time conflict
    → Confidence: 0.0, status: manual_review
```

**Matching Rules:**
- Never auto-match with confidence < 0.85
- Flag duplicate potential matches for review
- Log all match attempts for audit

### 5.2 Player Name Resolver

**Purpose:** Normalize player names across data sources

**Normalization Pipeline:**
```
INPUT: "Robert Williams III" (Odds API)
                │
                ▼
┌─────────────────────────────────────┐
│ Step 1: Exact Lookup                │
│ SELECT * FROM player_aliases       │
│ WHERE alias_name = input            │
└─────────────────┬───────────────────┘
                  │ Not Found
                  ▼
┌─────────────────────────────────────┐
│ Step 2: Normalized Comparison       │
│ - Remove suffixes (Jr, Sr, III)     │
│ - Lowercase                         │
│ - Remove punctuation (P.J. → PJ)    │
│ - Remove accents (é → e)            │
└─────────────────┬───────────────────┘
                  │ Not Found
                  ▼
┌─────────────────────────────────────┐
│ Step 3: Fuzzy Match                 │
│ - Levenshtein distance              │
│ - Jaro-Winkler similarity           │
│ - Phonetic matching (Soundex)       │
│ - Threshold: 0.90 similarity        │
└─────────────────┬───────────────────┘
                  │ Not Found
                  ▼
┌─────────────────────────────────────┐
│ Step 4: Team Context Match          │
│ - Same team + similar name          │
│ - Position + similar name           │
└─────────────────┬───────────────────┘
                  │ Not Found
                  ▼
        Flag for Manual Review

OUTPUT: nba_player_id: 1629057 (canonical)
```

**Pre-seeded Aliases (Known Issues):**
```json
[
  {"canonical": "Robert Williams III", "aliases": ["Robert Williams", "Rob Williams"]},
  {"canonical": "P.J. Washington", "aliases": ["PJ Washington", "P.J. Washington Jr."]},
  {"canonical": "Nicolas Claxton", "aliases": ["Nic Claxton"]},
  {"canonical": "Kentavious Caldwell-Pope", "aliases": ["KCP", "K. Caldwell-Pope"]},
  {"canonical": "Shai Gilgeous-Alexander", "aliases": ["SGA", "Shai Gilgeous Alexander"]},
  {"canonical": "Jaren Jackson Jr.", "aliases": ["Jaren Jackson", "JJJ"]},
  {"canonical": "Michael Porter Jr.", "aliases": ["Michael Porter", "MPJ"]},
  {"canonical": "Gary Trent Jr.", "aliases": ["Gary Trent"]},
  {"canonical": "Kelly Oubre Jr.", "aliases": ["Kelly Oubre"]},
  {"canonical": "Jabari Smith Jr.", "aliases": ["Jabari Smith"]},
  {"canonical": "Marcus Morris Sr.", "aliases": ["Marcus Morris"]},
  {"canonical": "Derrick Jones Jr.", "aliases": ["Derrick Jones"]},
  {"canonical": "Tim Hardaway Jr.", "aliases": ["Tim Hardaway"]},
  {"canonical": "Larry Nance Jr.", "aliases": ["Larry Nance"]},
  {"canonical": "Wendell Carter Jr.", "aliases": ["Wendell Carter"]},
  {"canonical": "Otto Porter Jr.", "aliases": ["Otto Porter"]}
]
```

### 5.3 Sync Orchestrator

**Purpose:** Coordinate sync jobs and ensure data freshness

**Sync Schedule:**
```yaml
schedules:
  # Full game sync - twice daily
  nba_games_full:
    cron: "0 6,18 * * *"
    source: nba_api
    data_type: games
    lookback_days: 7
    lookahead_days: 14

  # Odds sync - every 5 minutes during active hours
  odds_current:
    cron: "*/5 10-23 * * *"
    source: odds_api
    data_type: odds
    filter: upcoming_games

  # Player stats sync - hourly
  nba_player_stats:
    cron: "0 * * * *"
    source: nba_api
    data_type: player_stats
    filter: active_players

  # Matching reconciliation - every 15 minutes
  game_matching:
    cron: "*/15 * * * *"
    type: internal
    action: reconcile_unmatched_games

  # Stale data cleanup - daily
  cleanup:
    cron: "0 4 * * *"
    type: internal
    action: archive_old_data
    retention_days: 90
```

**Sync State Machine:**
```
                    ┌─────────────┐
                    │   IDLE      │
                    └──────┬──────┘
                           │ trigger (scheduled/manual)
                           ▼
                    ┌─────────────┐
           ┌────────│   SYNCING   │────────┐
           │        └──────┬──────┘        │
           │               │               │
      timeout/error    complete       partial
           │               │               │
           ▼               ▼               ▼
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │   FAILED    │ │  MATCHING   │ │   PARTIAL   │
    └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
           │               │               │
           │               ▼               │
           │        ┌─────────────┐        │
           └───────►│   IDLE      │◄───────┘
                    └─────────────┘
```

---

## 6. API Contracts

### 6.1 Internal Service API

```yaml
# Get matched game data for prediction service
GET /api/v1/matched-games/{date}
Response:
  - nba_game_id: string
  - odds_event_id: string
  - home_team: TeamData
  - away_team: TeamData
  - game_time: datetime
  - odds: OddsData
  - stats: GameStatsData
  - match_confidence: float
  - last_synced: datetime

# Get player with resolved identity
GET /api/v1/players/{identifier}
Query Params:
  - source: 'nba' | 'odds' | 'any'
Response:
  - nba_player_id: int
  - canonical_name: string
  - current_team: TeamData
  - known_aliases: string[]
  - active_odds: PlayerOddsData[]
  - recent_stats: PlayerStatsData

# Force sync for a specific game
POST /api/v1/sync/game
Body:
  - nba_game_id: string (optional)
  - odds_event_id: string (optional)
  - date: date (optional)
Response:
  - status: 'matched' | 'pending' | 'failed'
  - match_confidence: float
  - details: MatchDetails

# Get sync health status
GET /api/v1/sync/status
Response:
  - overall_health: 'healthy' | 'degraded' | 'unhealthy'
  - sources:
      nba_api:
        last_sync: datetime
        status: string
        records_synced: int
      odds_api:
        last_sync: datetime
        status: string
        records_synced: int
  - matching:
      games_matched: int
      games_pending: int
      games_failed: int
      players_resolved: int
      players_pending: int
```

---

## 7. Implementation Phases

### Phase 1: Foundation (Week 1-2)
**Goal:** Database schema and basic sync infrastructure

| Task | Priority | Estimate |
|------|----------|----------|
| Create database migrations | P0 | 2 days |
| Seed team_mappings with all 30 NBA teams | P0 | 1 day |
| Seed known player_aliases (top 50 problematic) | P0 | 1 day |
| Build sync_metadata tracking | P0 | 2 days |
| Basic sync orchestrator skeleton | P0 | 2 days |

**Deliverables:**
- [ ] All tables created in database
- [ ] Team mappings seeded
- [ ] Initial player aliases seeded
- [ ] Sync tracking operational

---

### Phase 2: Matching Engine (Week 3-4)
**Goal:** Core matching logic for games and players

| Task | Priority | Estimate |
|------|----------|----------|
| Game matching algorithm (exact + fuzzy) | P0 | 3 days |
| Player name resolver | P0 | 3 days |
| Manual review queue/dashboard | P1 | 2 days |
| Match confidence scoring | P0 | 1 day |
| Audit logging | P1 | 1 day |

**Deliverables:**
- [ ] >95% automatic game matching
- [ ] >98% automatic player resolution
- [ ] Admin UI for manual review queue

---

### Phase 3: Integration (Week 5-6)
**Goal:** Connect to existing services

| Task | Priority | Estimate |
|------|----------|----------|
| Integrate with nba_api_service.py | P0 | 2 days |
| Integrate with odds_api_service.py | P0 | 2 days |
| Update prediction service to use matched data | P0 | 3 days |
| Add validation layer (reject unmatched) | P0 | 1 day |
| API endpoints for matched data | P1 | 2 days |

**Deliverables:**
- [ ] Prediction service only uses validated data
- [ ] Clear error handling for unmatched scenarios
- [ ] API endpoints documented and tested

---

### Phase 4: Automation & Monitoring (Week 7-8)
**Goal:** Production-ready reliability

| Task | Priority | Estimate |
|------|----------|----------|
| Scheduled sync jobs (cron) | P0 | 2 days |
| Health monitoring dashboard | P1 | 2 days |
| Alerting for sync failures | P0 | 1 day |
| Alerting for low match rates | P0 | 1 day |
| Performance optimization | P2 | 2 days |
| Documentation | P1 | 2 days |

**Deliverables:**
- [ ] Fully automated sync pipeline
- [ ] Monitoring dashboard
- [ ] PagerDuty/Slack alerts configured
- [ ] Runbook for common issues

---

## 8. Risk Mitigation

### Risk Matrix

| Risk | Probability | Impact | Mitigation |
|------|-------------|--------|------------|
| Odds API format changes | Medium | High | Version tracking, schema validation, alerts |
| NBA.com API rate limiting | High | Medium | Exponential backoff, caching, off-peak sync |
| Player trade mid-season | Certain | Low | Daily player roster sync, team change detection |
| New player (rookie/trade) not in aliases | High | Medium | Auto-flag unknown players, weekly alias review |
| Game postponement/cancellation | Medium | Medium | Status field sync, event-driven updates |
| Timezone inconsistencies | Medium | High | All times stored as UTC, explicit timezone handling |

### Fallback Strategies

```
IF game_match_confidence < 0.85:
    → Exclude from predictions
    → Add to manual review queue
    → Alert if >5% of games unmatched

IF player_not_found:
    → Log warning with source data
    → Exclude player prop from prediction
    → Continue with game-level prediction
    → Batch review unknown players daily

IF sync_fails:
    → Retry with exponential backoff (max 3)
    → Use cached data if <1 hour old
    → Alert on-call if data >1 hour stale
    → Mark predictions as "stale data" if served
```

---

## 9. Success Criteria for Launch

### Minimum Viable Sync (MVP)
- [ ] All games from past 7 days matched or flagged
- [ ] All upcoming 7-day games matched or flagged  
- [ ] Top 200 active players resolved
- [ ] Sync runs every 15 minutes without failure
- [ ] Prediction service validates data before use

### Production Ready
- [ ] 30-day match rate >98%
- [ ] Player resolution >99%
- [ ] <5 minute data staleness during games
- [ ] Zero silent data mismatches
- [ ] Monitoring and alerting operational
- [ ] Runbook documented

---

## 10. Open Questions

| Question | Owner | Status |
|----------|-------|--------|
| What is acceptable match confidence threshold for auto-approval? | Product | **Proposed: 0.85** |
| Should we expose match confidence in prediction API? | Product | Open |
| Historical data backfill - how far back? | Engineering | **Proposed: Current season** |
| Manual review SLA - how quickly must matches be resolved? | Operations | Open |
| Should predictions fail hard or soft when data unmatched? | Product | **Proposed: Fail hard with clear error** |

---

## Appendix A: Team Mapping Seed Data

```json
{
  "teams": [
    {"nba_id": 1610612737, "abbrev": "ATL", "name": "Atlanta Hawks", "odds_key": "atlanta-hawks"},
    {"nba_id": 1610612738, "abbrev": "BOS", "name": "Boston Celtics", "odds_key": "boston-celtics"},
    {"nba_id": 1610612751, "abbrev": "BKN", "name": "Brooklyn Nets", "odds_key": "brooklyn-nets"},
    {"nba_id": 1610612766, "abbrev": "CHA", "name": "Charlotte Hornets", "odds_key": "charlotte-hornets"},
    {"nba_id": 1610612741, "abbrev": "CHI", "name": "Chicago Bulls", "odds_key": "chicago-bulls"},
    {"nba_id": 1610612739, "abbrev": "CLE", "name": "Cleveland Cavaliers", "odds_key": "cleveland-cavaliers"},
    {"nba_id": 1610612742, "abbrev": "DAL", "name": "Dallas Mavericks", "odds_key": "dallas-mavericks"},
    {"nba_id": 1610612743, "abbrev": "DEN", "name": "Denver Nuggets", "odds_key": "denver-nuggets"},
    {"nba_id": 1610612765, "abbrev": "DET", "name": "Detroit Pistons", "odds_key": "detroit-pistons"},
    {"nba_id": 1610612744, "abbrev": "GSW", "name": "Golden State Warriors", "odds_key": "golden-state-warriors"},
    {"nba_id": 1610612745, "abbrev": "HOU", "name": "Houston Rockets", "odds_key": "houston-rockets"},
    {"nba_id": 1610612754, "abbrev": "IND", "name": "Indiana Pacers", "odds_key": "indiana-pacers"},
    {"nba_id": 1610612746, "abbrev": "LAC", "name": "Los Angeles Clippers", "odds_key": "los-angeles-clippers"},
    {"nba_id": 1610612747, "abbrev": "LAL", "name": "Los Angeles Lakers", "odds_key": "los-angeles-lakers"},
    {"nba_id": 1610612763, "abbrev": "MEM", "name": "Memphis Grizzlies", "odds_key": "memphis-grizzlies"},
    {"nba_id": 1610612748, "abbrev": "MIA", "name": "Miami Heat", "odds_key": "miami-heat"},
    {"nba_id": 1610612749, "abbrev": "MIL", "name": "Milwaukee Bucks", "odds_key": "milwaukee-bucks"},
    {"nba_id": 1610612750, "abbrev": "MIN", "name": "Minnesota Timberwolves", "odds_key": "minnesota-timberwolves"},
    {"nba_id": 1610612740, "abbrev": "NOP", "name": "New Orleans Pelicans", "odds_key": "new-orleans-pelicans"},
    {"nba_id": 1610612752, "abbrev": "NYK", "name": "New York Knicks", "odds_key": "new-york-knicks"},
    {"nba_id": 1610612760, "abbrev": "OKC", "name": "Oklahoma City Thunder", "odds_key": "oklahoma-city-thunder"},
    {"nba_id": 1610612753, "abbrev": "ORL", "name": "Orlando Magic", "odds_key": "orlando-magic"},
    {"nba_id": 1610612755, "abbrev": "PHI", "name": "Philadelphia 76ers", "odds_key": "philadelphia-76ers"},
    {"nba_id": 1610612756, "abbrev": "PHX", "name": "Phoenix Suns", "odds_key": "phoenix-suns"},
    {"nba_id": 1610612757, "abbrev": "POR", "name": "Portland Trail Blazers", "odds_key": "portland-trail-blazers"},
    {"nba_id": 1610612758, "abbrev": "SAC", "name": "Sacramento Kings", "odds_key": "sacramento-kings"},
    {"nba_id": 1610612759, "abbrev": "SAS", "name": "San Antonio Spurs", "odds_key": "san-antonio-spurs"},
    {"nba_id": 1610612761, "abbrev": "TOR", "name": "Toronto Raptors", "odds_key": "toronto-raptors"},
    {"nba_id": 1610612762, "abbrev": "UTA", "name": "Utah Jazz", "odds_key": "utah-jazz"},
    {"nba_id": 1610612764, "abbrev": "WAS", "name": "Washington Wizards", "odds_key": "washington-wizards"}
  ]
}
```

---

## Appendix B: File Structure

```
/sync_service
├── __init__.py
├── orchestrator.py           # Main sync coordinator
├── matchers/
│   ├── __init__.py
│   ├── game_matcher.py       # Game matching logic
│   └── player_resolver.py    # Player name resolution
├── adapters/
│   ├── __init__.py
│   ├── nba_api_adapter.py    # Wraps nba_api_service
│   └── odds_api_adapter.py   # Wraps odds_api_service
├── models/
│   ├── __init__.py
│   ├── game_mapping.py
│   ├── player_alias.py
│   ├── team_mapping.py
│   └── sync_metadata.py
├── repositories/
│   ├── __init__.py
│   └── sync_repository.py    # Database operations
├── jobs/
│   ├── __init__.py
│   ├── game_sync_job.py
│   ├── odds_sync_job.py
│   └── matching_job.py
├── api/
│   ├── __init__.py
│   └── routes.py             # API endpoints
└── utils/
    ├── __init__.py
    ├── name_normalizer.py    # String normalization
    └── confidence_scorer.py  # Match confidence calc

/migrations
├── 001_create_game_mappings.sql
├── 002_create_player_aliases.sql
├── 003_create_team_mappings.sql
├── 004_create_sync_metadata.sql
└── 005_create_audit_log.sql

/seeds
├── team_mappings.json
└── player_aliases.json
```

---

*Document Version History:*
| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | Jan 2025 | Engineering | Initial draft |
