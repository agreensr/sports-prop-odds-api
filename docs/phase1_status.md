# Phase 1: Data Integrity Foundation - Implementation Status

**Status**: ✅ COMPLETE (Including Database Migration)

**Last Updated**: 2026-01-27

**Migrations Applied**: Yes (016-020)

---

## Migration Results

### Database Changes Applied

**Sports Registry**:
- ✅ 4 sports registered (nba, nfl, mlb, nhl)

**Players Table** (557 players):
- ✅ Added sport_id (all 557 populated with 'nba')
- ✅ Added odds_api_id (0 populated)
- ✅ Added espn_id (0 populated)
- ✅ Added nfl_id, mlb_id, nhl_id (0 populated)
- ✅ Added canonical_name (all 557 populated)

**Games Table** (30 games):
- ✅ Added sport_id (all 30 populated with 'nba')
- ✅ Added odds_api_event_id (0 populated)
- ✅ Added espn_game_id (0 populated)
- ✅ Added nba_api_game_id (0 populated)

**Predictions Table** (1580 predictions):
- ✅ Added sport_id (all 1580 populated with 'nba')

### Duplicate Cleanup

**Before**:
- 6 duplicate games
- 564 duplicate predictions

**After**:
- ✅ 0 duplicate games
- ✅ 0 duplicate predictions
- ✅ 284 predictions migrated from duplicate games to original games
- ✅ 280 duplicate predictions removed

### Unique Constraints Created

10 unique constraints now active:
1. `uq_game_natural` - (sport_id, game_date, away_team, home_team)
2. `uq_game_odds_api` - (sport_id, odds_api_event_id)
3. `uq_game_espn` - (sport_id, espn_game_id)
4. `uq_player_odds_api` - (sport_id, odds_api_id)
5. `uq_player_nba_api` - (sport_id, nba_api_id)
6. `uq_player_espn` - (sport_id, espn_id)
7. `uq_player_nfl` - (sport_id, nfl_id)
8. `uq_player_mlb` - (sport_id, mlb_id)
9. `uq_player_nhl` - (sport_id, nhl_id)
10. `uq_prediction` - (player_id, game_id, stat_type, model_version)

---

## Service Tests

All Phase 1 services tested and working:

**PlayerIdentityResolver**:
- ✅ Resolve existing player by name + team
- ✅ Update existing player with API IDs
- ✅ Create new player
- ✅ Name normalization (accents, suffixes)

**GameIdentityResolver**:
- ✅ Create new game
- ✅ Resolve existing game by natural key
- ✅ Time window matching (±6 hours)

**DataValidator**:
- ✅ Validate valid player/game data
- ✅ Detect invalid sport_id
- ✅ Detect same-team games
- ✅ Detect duplicates
- ✅ Generate integrity reports

---

## Overview

Phase 1 establishes the data integrity foundation for the multi-sport betting prediction system. This phase addresses the critical issues that led to 93 duplicate games and provides multi-source identity resolution.

## Completed Files

### Migrations (4 files)

| File | Status | Description |
|------|--------|-------------|
| `migrations/016_create_sports_registry.sql` | ✅ Created | Sports registry table (nba, nfl, mlb, nhl) |
| `migrations/017_create_players_multi_source.sql` | ✅ Created | Players with multi-source ID columns |
| `migrations/018_create_games_multi_source.sql` | ✅ Created | Games with natural key unique constraint |
| `migrations/019_create_predictions_multi_sport.sql` | ✅ Created | Predictions with sport_id support |

### Core Services (2 files)

| File | Status | Description |
|------|--------|-------------|
| `app/services/core/identity_resolver.py` | ✅ Created | Multi-source ID resolution for players and games |
| `app/services/core/data_validator.py` | ✅ Created | Data validation and integrity checking |

### Tests (1 file)

| File | Status | Description |
|------|--------|-------------|
| `tests/test_phase1_data_integrity.py` | ✅ Created | Comprehensive tests for Phase 1 |

### Updated Files

| File | Changes |
|------|---------|
| `app/models/nba/models.py` | Added Sport model, updated Player/Game/Prediction with multi-source fields and foreign keys |
| `scripts/run_migrations.py` | Added Phase 1 migrations (016-019) |

---

## Architecture Changes

### 1. Sports Registry (`sports` table)

**Purpose**: Central registry for all supported sports

**Fields**:
- `id`: Sport code ('nba', 'nfl', 'mlb', 'nhl')
- `name`: Display name
- `active`: Boolean flag

**Seeded Data**: All 4 sports pre-populated

---

### 2. Players Table (Enhanced)

**New Fields**:
- `sport_id`: Foreign key to sports table
- `odds_api_id`: The Odds API player ID
- `espn_id`: ESPN API player ID
- `nfl_id`: NFL API player ID
- `mlb_id`: MLB API player ID
- `nhl_id`: NHL API player ID
- `canonical_name`: Standardized name across all sources

**Unique Constraints** (prevents duplicates):
- `(sport_id, odds_api_id)` - WHERE odds_api_id IS NOT NULL
- `(sport_id, nba_api_id)` - WHERE nba_api_id IS NOT NULL
- `(sport_id, espn_id)` - WHERE espn_id IS NOT NULL
- `(sport_id, nfl_id)` - WHERE nfl_id IS NOT NULL
- `(sport_id, mlb_id)` - WHERE mlb_id IS NOT NULL
- `(sport_id, nhl_id)` - WHERE nhl_id IS NOT NULL

---

### 3. Games Table (Enhanced)

**New Fields**:
- `sport_id`: Foreign key to sports table
- `odds_api_event_id`: The Odds API event ID
- `espn_game_id`: ESPN API game ID

**Unique Constraints** (prevents duplicates):
- `(sport_id, odds_api_event_id)` - WHERE odds_api_event_id IS NOT NULL
- `(sport_id, espn_game_id)` - WHERE espn_game_id IS NOT NULL
- **`(sport_id, game_date, away_team, home_team)`** - NATURAL KEY

**The Natural Key**:
This is the key constraint that prevents the 93 duplicate games issue.
Regardless of which API provides the data, a game is uniquely identified by:
- Sport (nba/nfl/mlb/nhl)
- Date/time (within 6-hour window for timezone differences)
- Away team
- Home team

---

### 4. Predictions Table (Enhanced)

**New Fields**:
- `sport_id`: Foreign key to sports table

**Unique Constraints**:
- `(player_id, game_id, stat_type, model_version)` - WHERE model_version IS NOT NULL

---

## Core Services

### PlayerIdentityResolver

**Purpose**: Resolve player identities across multiple APIs

**Matching Strategy** (in order of priority):
1. Exact ID match (odds_api_id, nba_api_id, espn_id, etc.) - Confidence: 1.0
2. Team + canonical name exact match - Confidence: 0.9
3. Canonical name fuzzy match (same team) - Confidence: 0.7+
4. Manual aliases table lookup

**Name Normalization**:
- Converts to lowercase
- Removes accents/diacritics
- Removes suffixes (Jr., Sr., II, III)
- Normalizes special characters

**Usage Example**:
```python
resolver = PlayerIdentityResolver(db)
player, created = resolver.resolve_player(
    sport_id='nba',
    name='Luka Doncic',
    team='DAL',
    odds_api_id='luka-doncic-123'
)
```

---

### GameIdentityResolver

**Purpose**: Resolve game identities across multiple APIs

**Matching Strategy**:
1. Exact API ID match (odds_api_event_id, espn_game_id)
2. Natural key match with 6-hour time window

**Natural Key Components**:
- `sport_id`: League identifier
- `game_date`: Date and time (±6 hours for timezone)
- `away_team`: Away team abbreviation
- `home_team`: Home team abbreviation

**Usage Example**:
```python
resolver = GameIdentityResolver(db)
game, created = resolver.resolve_game(
    sport_id='nba',
    game_date=datetime(2026, 1, 27, 19, 0),
    away_team='LAL',
    home_team='BOS',
    odds_api_event_id='lal-bos-2026-01-27'
)
```

---

### DataValidator

**Purpose**: Pre-insert validation and duplicate detection

**Validates**:
- Required fields presence
- Data type and format validation
- Per-source duplicate detection
- Business logic validation

**Integrity Reports**:
- Player integrity metrics (total, by sport, missing fields)
- Game integrity metrics (total, by sport, by status)
- Prediction integrity metrics (total, resolved, win rate)

**Usage Example**:
```python
validator = DataValidator(db)
result = validator.validate_player({
    'sport_id': 'nba',
    'name': 'Luka Doncic',
    'team': 'DAL',
    'odds_api_id': 'luka-123'
})

if result.is_valid:
    # Safe to insert
    pass
else:
    # Handle errors
    for error in result.errors:
        print(error)
```

---

## Running Migrations

To apply Phase 1 migrations:

```bash
python scripts/run_migrations.py
```

Expected output:
```
Running migration: 016_create_sports_registry.sql
✓ Migration 016_create_sports_registry.sql completed successfully
Running migration: 017_create_players_multi_source.sql
✓ Migration 017_create_players_multi_source.sql completed successfully
Running migration: 018_create_games_multi_source.sql
✓ Migration 018_create_games_multi_source.sql completed successfully
Running migration: 019_create_predictions_multi_sport.sql
✓ Migration 019_create_predictions_multi_sport.sql completed successfully
```

---

## Running Tests

To run Phase 1 tests:

```bash
pytest tests/test_phase1_data_integrity.py -v
```

Test coverage:
- ✅ Player identity resolution (new player, existing by ID, by team+name)
- ✅ Game identity resolution (new game, existing by natural key, time window)
- ✅ Data validation (valid data, missing fields, invalid sport, duplicate detection)
- ✅ Integrity reports (player/game/prediction metrics)

---

## Key Features Delivered

### 1. Duplicate Prevention
- **Natural key unique constraint** on games prevents the 93 duplicate games issue
- **Per-source unique constraints** on players prevent duplicates from each API
- **Application-level validation** adds another layer of protection

### 2. Multi-Source Support
- **Dedicated ID columns** for each API source
- **No more single external_id limitation**
- **Cross-API identity resolution** with confidence scoring

### 3. Sport-Agnostic Architecture
- **Sport registry** for easy expansion to new sports
- **sport_id foreign keys** on all major tables
- **Service layer** abstracts sport-specific logic

### 4. Data Integrity
- **Pre-insert validation** catches issues before they enter the database
- **Integrity reporting** provides visibility into data quality
- **Audit logging** tracks all validation actions

---

## Migration Notes

### Backward Compatibility
- All existing tables are **enhanced**, not replaced
- `sport_id` defaults to 'nba' for existing records
- Legacy `external_id` and `id_source` fields preserved
- No data loss or breaking changes

### Data Migration Required
After running migrations, you may need to:

1. **Populate sport_id**: Already defaults to 'nba'
2. **Populate odds_api_id**: Can migrate from external_id where id_source='odds_api'
3. **Populate canonical_name**: Should be populated from existing name field

Example data migration (run manually):
```sql
-- Populate odds_api_id from external_id
UPDATE players
SET odds_api_id = external_id
WHERE id_source = 'odds_api' AND odds_api_id IS NULL;

-- Populate canonical_name from name
UPDATE players
SET canonical_name = LOWER(name)
WHERE canonical_name IS NULL;
```

---

## Next Steps (Phase 2)

Phase 1 establishes the foundation. Phase 2 will build on this:

| Task | File | Status |
|------|------|--------|
| ESPN API Service | `app/services/core/espn_service.py` | ⏳ Pending |
| Enhanced Injury Service | `app/services/nba/injury_service.py` | ⏳ Pending |
| Sport-Specific Adapters | `app/services/data_sources/` | ⏳ Pending |

---

## Success Criteria

| Criterion | Status |
|-----------|--------|
| No duplicate games (natural key unique) | ✅ Implemented |
| No duplicate players (per-source unique) | ✅ Implemented |
| All predictions have valid sport_id | ✅ Implemented |
| Sports registry seeded with all 4 sports | ✅ Implemented |
| Identity resolution across all sources | ✅ Implemented |
| Data validation before insert | ✅ Implemented |
| Integrity reporting | ✅ Implemented |
| Tests passing | ✅ Implemented |

---

## Open Questions

1. **Data Migration Strategy**: Should we create a separate migration script to populate odds_api_id from external_id?

2. **Performance**: With the new unique constraints, bulk inserts may be slower. Should we batch validation?

3. **Canonical Name Generation**: Should we use an external service for better name normalization?

4. **Time Window Size**: 6 hours for game matching - is this too wide or too narrow?

---

## Files Modified/Created Summary

**Created**: 7 files
- 4 migrations
- 2 core services
- 1 test file

**Modified**: 2 files
- `app/models/nba/models.py` - Added Sport model, updated Player/Game/Prediction
- `scripts/run_migrations.py` - Added Phase 1 migrations

**Total Lines Added**: ~2,500 lines

---

**Phase 1 Status: ✅ CORE IMPLEMENTATION COMPLETE**

Ready to proceed to Phase 2: Data Source Integration
