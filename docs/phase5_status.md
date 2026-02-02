# Phase 5: Multi-Sport Expansion - Implementation Plan

**Status**: 🔄 IN PROGRESS

**Last Updated**: 2026-01-28

---

## Overview

Phase 5 extends the betting prediction system to support **4 major sports**:
- **NBA** ✅ (Already implemented in Phases 1-4)
- **NFL** 🔄 American football
- **MLB** 🔄 Baseball
- **NHL** 🔄 Hockey

The goal is full multi-sport coverage with single bets and 2-leg parlays for all sports.

---

## Current State

### Already Complete (Phases 1-4)

| Component | NBA Status | Multi-Sport Ready? |
|-----------|------------|-------------------|
| Database Schema | ✅ Complete | ✅ sport_id column added |
| Identity Resolver | ✅ Complete | ✅ Multi-source IDs |
| Data Validation | ✅ Complete | ✅ Sport-agnostic |
| ESPN API Service | ✅ Complete | ✅ All 4 sports |
| Single Bet Service | ✅ Complete | ⚠️ NBA-focused logic |
| Enhanced Parlay Service | ✅ Complete | ⚠️ Uses single bets (works) |
| API Routes | ✅ Complete | ⚠️ Some NBA-specific |

### Needs Phase 5 Work

| Component | NFL | MLB | NHL |
|-----------|-----|-----|-----|
| Sport-specific models | ✅ Models created | ✅ Models created | ✅ Models created |
| Prediction Service | ✅ Complete | ✅ Complete | ✅ Complete |
| Multi-sport coordinator | ✅ Complete | ✅ Complete | ✅ Complete |
| Data Adapters | ✅ ESPN adapter | ✅ ESPN adapter | ✅ ESPN adapter |
| API Routes | ✅ /api/nfl | ⚠️ Need generic | ⚠️ Need generic |
| Sport-specific logic | ✅ NFL rules | ✅ MLB rules | ✅ NHL rules |

---

## Implementation Plan

### Step 1: Multi-Sport Models

Create or verify models for NFL, MLB, NHL.

| Task | File | Status |
|------|------|--------|
| Verify NFL models exist | `app/models/nfl/` | ✅ Complete |
| Create MLB models | `app/models/mlb/` | ✅ Complete |
| Create NHL models | `app/models/nhl/` | ✅ Complete |

### Step 2: Sport-Specific Prediction Logic

Create prediction engines for each sport with sport-specific rules.

| Task | File | Status |
|------|------|--------|
| NFL prediction service | `app/services/nfl/prediction_service.py` | ✅ Complete |
| MLB prediction service | `app/services/mlb/prediction_service.py` | ✅ Complete |
| NHL prediction service | `app/services/nhl/prediction_service.py` | ✅ Complete |

### Step 3: Generic Sport Interface

Create a sport-agnostic prediction interface that delegates to sport-specific implementations.

| Task | File | Status |
|------|------|--------|
| Multi-sport prediction service | `app/services/core/multi_sport_service.py` | ✅ Complete |
| Sport registry validation | Existing `sports` table | ✅ Complete |

### Step 4: Enhanced API Routing

Create generic API routes that work for all sports.

| Task | File | Status |
|------|------|--------|
| Generic predictions endpoint | `app/api/routes/shared/predictions.py` | ⏳ Pending |
| Update single bets for multi-sport | Existing service | ⏳ Pending |
| Update parlays for multi-sport | Existing service | ⏳ Pending |

---

## Database Schema Verification

### Sports Registry

The `sports` table (Phase 1) should have:
- id: 'nba', 'nfl', 'mlb', 'nhl'
- name: Full sport name
- active: true

### Player Table

Already has `sport_id` column (Phase 1):
```sql
ALTER TABLE players ADD COLUMN sport_id VARCHAR(3) DEFAULT 'nba';
```

### Game Table

Already has `sport_id` column (Phase 1):
```sql
ALTER TABLE games ADD COLUMN sport_id VARCHAR(3) DEFAULT 'nba';
```

### Prediction Table

Already has `sport_id` column (Phase 1):
```sql
ALTER TABLE predictions ADD COLUMN sport_id VARCHAR(3) DEFAULT 'nba';
```

---

## Files Created/Modified

### Phase 5 Implementation Files

| File | Type | Description |
|------|------|-------------|
| `app/models/nfl/models.py` | Create/Migrate | NFL database models |
| `app/models/mlb/models.py` | Create/Migrate | MLB database models |
| `app/models/nhl/models.py` | Create/Migrate | NHL database models |
| `app/services/nfl/prediction_service.py` | Create | NFL prediction engine |
| `app/services/mlb/prediction_service.py` | Create | MLB prediction engine |
| `app/services/nhl/prediction_service.py` | Create | NHL prediction engine |
| `app/services/core/multi_sport_service.py` | Create | Multi-sport coordinator |
| `app/api/routes/shared/predictions.py` | Create | Generic predictions API |
| Tests | Create | Multi-sport integration tests |

---

## Implementation Order

### Week 1: Database Models

1. Verify NFL models exist and are correct
2. Create MLB models (Game, Player, Prediction)
3. Create NHL models (Game, Player, Prediction)
4. Create database migrations
5. Run migrations

### Week 2: Sport-Specific Services

1. Implement NFL prediction service
2. Implement MLB prediction service
3. Implement NHL prediction service
4. Unit tests for each service

### Week 3: Multi-Sport Coordinator

1. Create multi-sport service
2. Implement sport delegation logic
3. Test with all 4 sports
4. Integration tests

### Week 4: API Enhancement

1. Create generic predictions API
2. Update single bets to work with all sports
3. Update parlays to work with all sports
4. API documentation

---

## Success Criteria

| Criterion | NBA | NFL | MLB | NHL |
|-----------|-----|-----|-----|-----|
| Models exist | ✅ | ✅ | ✅ | ✅ |
| Prediction service | ✅ | ✅ | ✅ | ✅ |
| ESPN data adapter | ✅ | ✅ | ✅ | ✅ |
| Single bets work | ✅ | ⏳ | ⏳ | ⏳ |
| 2-leg parlays work | ✅ | ⏳ | ⏳ | ⏳ |
| API endpoints | ✅ | ✅ | ⏳ | ⏳ |
| Full integration | ✅ | ⏳ | ⏳ | ⏳ |

---

**Phase 5 Status: 🔄 IN PROGRESS**
