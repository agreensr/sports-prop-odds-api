# Phase 3: Single Bet Service - Implementation Status

**Status**: ✅ COMPLETE

**Last Updated**: 2026-01-27

---

## Overview

Phase 3 implements the **single bet service**, which is the primary output of the prediction system. This generates 10 daily single bets with minimum 60% confidence and 5% edge.

---

## Completed Files

### Core Service (1 file)

| File | Status | Description |
|------|--------|-------------|
| `app/services/core/single_bet_service.py` | ✅ Created | Single bet generation with edge/EV calculations |

### API Routes (1 file)

| File | Status | Description |
|------|--------|-------------|
| `app/api/routes/shared/single_bets.py` | ✅ Created | REST API endpoints for single bets |

### Scripts (1 file)

| File | Status | Description |
|------|--------|-------------|
| `scripts/generate_single_bets.py` | ✅ Created | Daily bet generation script |

### Modified Files (1 file)

| File | Changes |
|------|---------|
| `app/main.py` | Added single_bets router and endpoint documentation |

---

## Core Features

### Single Bet Service

**Purpose**: Generate daily single bet recommendations

**Business Rules**:
- **Max 10 bets per day** (manageable for betting)
- **Min 60% confidence** (win probability)
- **Min 5% edge** (positive expected value)
- **Max 3 bets per game** (diversification)
- **Ranked by**: EV × confidence

**Key Methods**:
| Method | Description |
|--------|-------------|
| `generate_daily_bets(date, sport_id)` | Generate bets for a date |
| `_fetch_qualifying_predictions()` | Get predictions meeting thresholds |
| `_prediction_to_bet()` | Convert prediction to bet with edge/EV |
| `_meets_thresholds()` | Check if bet meets minimums |
| `_apply_limits()` | Apply business limits (10 daily, 3 per game) |
| `format_bets_for_display()` | Format for human-readable output |

### Edge & EV Calculations

**Edge Calculation**:
```
edge = (our_probability - implied_probability) × 100

Where:
- our_probability = confidence (from prediction)
- implied_probability = 1 / decimal_odds
- decimal_odds = converted from American odds
```

**EV Calculation**:
```
EV = (win_probability × profit) - (lose_probability × stake)

Where:
- win_probability = confidence
- profit = decimal_odds - 1 (for a $1 stake)
- lose_probability = 1 - confidence
- stake = 1 (standardized)
```

**Priority Score** (for ranking):
```
priority = EV × confidence
```

### Example Bet

```
SingleBet(
    player_name: "Luka Doncic"
    team: "DAL"
    opponent: "LAL"
    stat_type: "points"
    predicted_value: 35.2
    bookmaker_line: 33.5
    recommendation: OVER
    odds_american: -110
    odds_decimal: 1.91
    confidence: 0.68  (68%)
    edge_percent: 7.2%  (our edge over market)
    ev_percent: 13.5%  (expected value)
    priority_score: 9.18  (ranking metric)
)
```

---

## API Endpoints

### GET /api/single-bets/daily
Get daily single bet recommendations

**Query Parameters**:
- `target_date`: YYYY-MM-DD format (default: today)
- `sport_id`: Filter by sport (nba, nfl, mlb, nhl)
- `limit`: Max bets to return (1-20, default: 10)

**Response**:
```json
{
  "date": "2026-01-27",
  "total_bets": 10,
  "bets": [
    {
      "id": "123e4567-e89b-12d3-a456-426614174000",
      "sport_id": "nba",
      "player_name": "Luka Doncic",
      "team": "DAL",
      "opponent": "LAL",
      "game_date": "2026-01-27T19:00:00",
      "stat_type": "points",
      "predicted_value": 35.2,
      "bookmaker_line": 33.5,
      "recommendation": "OVER",
      "bookmaker_name": "draftkings",
      "odds_american": -110,
      "odds_decimal": 1.91,
      "confidence": 0.68,
      "edge_percent": 7.2,
      "ev_percent": 13.5,
      "priority_score": 9.18,
      "created_at": "2026-01-27T10:00:00"
    }
  ],
  "summary": {
    "avg_confidence": 0.65,
    "avg_edge": 6.8,
    "avg_ev": 12.3,
    "by_sport": {
      "nba": {"count": 7, "avg_confidence": 0.64, "avg_edge": 6.5},
      "nfl": {"count": 3, "avg_confidence": 0.67, "avg_edge": 7.2}
    }
  }
}
```

### GET /api/single-bets/bets
Get recent bets with filters

**Query Parameters**:
- `sport_id`: Filter by sport
- `days`: Days to look back (1-30, default: 7)
- `min_confidence`: Min confidence (0-1, default: 0.60)
- `min_edge`: Min edge % (default: 5.0)
- `limit`: Max results (1-100, default: 50)

**Response**: Array of SingleBetResponse

### GET /api/single-bets/stats
Get statistics for recent bets

**Query Parameters**:
- `days`: Days to look back (1-30, default: 7)

**Response**:
```json
{
  "total_bets": 47,
  "by_sport": {
    "nba": {"count": 30, "avg_confidence": 0.642, "avg_edge": 6.8, "avg_ev": 12.1},
    "nfl": {"count": 12, "avg_confidence": 0.675, "avg_edge": 7.2, "avg_ev": 14.3},
    "mlb": {"count": 5, "avg_confidence": 0.620, "avg_edge": 5.5, "avg_ev": 9.8}
  },
  "avg_confidence": 0.648,
  "avg_edge": 6.7,
  "avg_ev": 12.2
}
```

### GET /api/single-bets/display
Get bets in display format

**Query Parameters**:
- `target_date`: YYYY-MM-DD format
- `sport_id`: Filter by sport

**Response**:
```json
{
  "date": "2026-01-27",
  "sport": "all",
  "count": 10,
  "display": "🎯 TOP 10 SINGLE BETS - 2026-01-27\n\n1. Luka Doncic..."
}
```

---

## Daily Generation Script

### Usage

```bash
# Generate for today
python scripts/generate_single_bets.py

# Generate for specific date
python scripts/generate_single_bets.py --date 2026-01-27

# Generate for specific sport
python scripts/generate_single_bets.py --sport nba

# Display format (human-readable)
python scripts/generate_single_bets.py --display

# Dry run (no storage)
python scripts/generate_single_bets.py --dry-run

# Write to file
python scripts/generate_single_bets.py --output bets.json
```

### Output Format (Display)

```
🎯 TOP 10 SINGLE BETS - 2026-01-27

1. Luka Doncic (DAL) - Points OVER 33.5
   Confidence: 68% | Edge: +7.2% | EV: +13.5% | Odds: -110

2. LeBron James (LAL) - Assists OVER 6.5
   Confidence: 65% | Edge: +5.8% | EV: +10.2% | Odds: +105

3. Lamar Jackson (BAL) - Passing Yards UNDER 240
   Confidence: 71% | Edge: +8.1% | EV: +15.3% | Odds: -108

...
```

---

## Bet Selection Logic

### Step 1: Fetch Qualifying Predictions

Fetch predictions where:
- Game is within target date range
- Game status is scheduled/pending
- Confidence ≥ 60%
- Has valid odds (over_price or under_price)
- Not already resolved

### Step 2: Convert to Bets

For each prediction:
1. Determine side (OVER if predicted_value > line, else UNDER)
2. Get odds for that side
3. Convert American odds to decimal
4. Calculate implied probability from odds
5. Calculate edge = (our_prob - implied_prob) × 100
6. Calculate EV = (win_prob × profit) - (lose_prob × stake)
7. Calculate priority = EV × confidence

### Step 3: Filter by Thresholds

Keep bets where:
- confidence ≥ 60%
- edge ≥ 5%

### Step 4: Rank and Limit

1. Sort by priority_score (descending)
2. Take top 10 bets total
3. Max 3 bets per game

---

## Integration with Previous Phases

```
Phase 1 → Phase 2 → Phase 3
─────────────────────────────
Identity  →  ESPN API  →  Single Bets
Resolver     Adapters     Service
Validation   Data       Generation
```

**Example Flow**:
1. **Phase 1**: Player/Game resolved via IdentityResolver
2. **Phase 2**: Data fetched via ESPN API adapters
3. **Phase 3**: Predictions → Single bets with edge/EV

---

## Key Design Decisions

### 1. Single Bets as Primary Output

**Rationale**:
- Easier to track and verify than parlays
- More manageable (10 bets vs unlimited parlays)
- Better for bankroll management
- Higher confidence per bet

### 2. Confidence Threshold (60%)

**Rationale**:
- Breakeven is ~52.4% (with -110 vigorish)
- 60% gives 7.6% margin for error
- Realistic but selective

### 3. Edge Threshold (5%)

**Rationale**:
- Ensures positive expected value
- Filters out marginal bets
- Accounts for model uncertainty

### 4. Max 3 Bets Per Game

**Rationale**:
- Diversification
- Reduces correlation risk
- Prevents overexposure

### 5. Priority = EV × Confidence

**Rationale**:
- Balves profitability (EV) and certainty (confidence)
- High EV + low confidence is risky
- Low EV + high confidence is less profitable
- Product prioritizes both

---

## Performance Considerations

### Database Queries

- Indexed queries on game_date, status, confidence
- Efficient filtering and sorting
- No N+1 query problems

### Calculation Speed

- Edge/EV calculations are O(1) per prediction
- No external API calls (uses cached odds)
- Fast enough for real-time generation

### Caching

- Predictions already cached by prediction service
- Odds cached in predictions table
- No additional caching needed for single bets

---

## Testing

### Unit Tests

Test coverage should include:
- Edge calculation accuracy
- EV calculation accuracy
- American to decimal odds conversion
- Threshold filtering
- Per-game limiting
- Priority ranking

### Integration Tests

Test coverage should include:
- End-to-end bet generation
- API endpoint responses
- Database queries
- Error handling

---

## Next Steps (Phase 4)

Phase 3 establishes single bet generation. Phase 4 will focus on:

| Task | File | Status |
|------|------|--------|
| Enhance Parlay Service | `app/services/core/parlay_service.py` | ⏳ Pending |
| 2-Leg Parlay Generation | From top 10 single bets | ⏳ Pending |
| Parlay API Endpoints | Update existing routes | ⏳ Pending |

**Target**: 3-5 parlays daily from top 10 singles

---

## Success Criteria

| Criterion | Status |
|-----------|--------|
| Single bet service implemented | ✅ Complete |
| Min 60% confidence threshold | ✅ Complete |
| Min 5% edge threshold | ✅ Complete |
| Max 10 bets per day | ✅ Complete |
| Max 3 bets per game | ✅ Complete |
| Ranked by EV × confidence | ✅ Complete |
| API endpoint created | ✅ Complete |
| Daily generation script | ✅ Complete |
| Integration with main app | ✅ Complete |

---

## Files Modified/Created Summary

**Created**: 4 files
- 1 core service (single_bet_service.py)
- 1 API route (single_bets.py)
- 1 script (generate_single_bets.py)
- 1 timezone utility (app/core/timezone.py)

**Modified**: 2 files
- app/main.py (router registration)
- app/services/core/espn_service.py (timezone support)

**Total Lines Added**: ~1,400 lines

---

## Timezone Handling

All datetimes are stored in **UTC** in the database but displayed to users in **Central Time (CST/CDT)**.

**Central Time Conversion:**
- **CST** (UTC-6): Standard time, November - March
- **CDT** (UTC-5): Daylight saving time, March - November
- Automatic DST handling: Second Sunday in March → First Sunday in November

**Example:**
```
UTC: 2025-01-28 19:00:00 → Central: 2025-01-28 13:00:00 (1:00 PM CST)
UTC: 2025-07-15 18:00:00 → Central: 2025-07-15 13:00:00 (1:00 PM CDT)
```

**Affected Fields:**
- `game_date`: Game time in Central Time
- `created_at`: Bet creation timestamp in Central Time

---

**Phase 3 Status: ✅ COMPLETE**

Ready to proceed to Phase 4: Enhanced Parlay Service
