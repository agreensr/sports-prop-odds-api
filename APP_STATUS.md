# App Status - 2026-01-27

## Critical Issues Discovered

### 1. Duplicate Game Entries (FIXED ✅)
**Issue:** 93 duplicate game entries caused by NBA API and TheOddsAPI creating separate games for same matchups

**Fix Applied:**
- Created `scripts/deduplicate_games.py`
- Removed all 93 duplicate entries
- Moved 780+ predictions to correct games
- Kept NBA API games as source of truth

**Before:** 2161 games, 93 duplicate matchups
**After:** 2068 games, 0 duplicate matchups

**Critical duplicates fixed:**
- CHI@MIN: 168 predictions moved
- GSW@MIN: 316 predictions moved
- LAL@CHI: 319 predictions moved (USER'S ISSUE!)
- MEM@HOU: 323 predictions moved
- POR@BOS: 325 predictions moved

---

### 2. Luka Doncic Data Issue (FIXED)
**Issue:** Luka had impossible predictions (0.38 points)

**Root Cause:** Missing `nba_api_id` in player record → stats lookup failed

**Fix Applied:**
- Updated `nba_api_id = '1629029'`
- Inserted season stats: 28.5 PTS/36, 8.8 REB/36, 8.7 AST/36, 3.5 3PM/36
- Deleted 11 bad predictions with near-zero values
- Regenerated predictions with realistic values (21.7/7.8/7.2)

**Current Status:** ✅ Fixed

---

### 3. FanDuel Odds Not Attached (ONGOING)
**Issue:** Predictions don't have `bookmaker_line` attached from FanDuel

**Current State:**
```python
# Most predictions have:
bookmaker_line = None
over_price = None
under_price = None
```

**Required:** Run odds sync to fetch FanDuel lines and attach to predictions

---

## Current Prediction Values

### Luka Doncic - Upcoming Games
| Game | Predicted PTS | Line | Recommendation |
|------|---------------|------|----------------|
| LAL @ CLE (Jan 28) | 20.0 | None | OVER |
| LAL @ CHI (Jan 27) | 21.7 | None | UNDER |

### Jalen Smith
| Game | Predicted PTS | Line | Recommendation |
|------|---------------|------|----------------|
| CHI games | ~10.5 | None | UNDER |

---

## Parlay Generation Status

**Last Run:** 2026-01-27
- Generated: 55 2-leg parlays, 6 3-leg parlays
- Status: ✅ Successfully sent to Telegram
- Issue: Ayo Dosunmu appearing (should be filtered out by whitelist)

**Top Parlays by EV:**
1. Ayo Dosunmu: Threes UNDER 1.5 + Points UNDER 12.5 (21.8% EV)

**Note:** Ayo Dosunmu is commented out in whitelist but still appearing in parlays - VPS code may be out of sync

---

## Database Stats

### Players
- Total active: 731
- Healthy (not injured): 645

### Games (Upcoming with odds)
- CLE @ CHA: 34 healthy players with odds
- IND @ BOS: 43 healthy players with odds
- BKN @ NYK: 33 healthy players with odds
- ATL @ MEM: 40 healthy players with odds
- DET @ NOP: 26 healthy players with odds
- OKC @ MIL: 24 healthy players with odds
- TOR @ SAC: 43 healthy players with odds
- CHI @ MIN: 55 healthy players with odds
- POR @ BOS: 58 healthy players with odds
- LAL @ CHI: 61 healthy players with odds
- MEM @ HOU: 58 healthy players with odds
- GSW @ MIN: 60 healthy players with odds

---

## Betting Results (User Feedback)

### Recent Bets Placed
1. ❌ **Jalen Smith UNDER 12.5** - He scored 13 (LOST by 1)
2. ❌ **Luka Doncic UNDER 33.5** - He scored 46 (LOST by 12.5)

**Learning:** Prediction system significantly under-estimated Luka's scoring

---

## Files Modified Recently

1. `app/core/fanduel_whitelist.py` - Ayo Dosunmu commented out
2. `app/services/core/parlay_service.py` - Deduplication logic added
3. `app/models/nba/models.py` - Luka nba_api_id updated
4. `seeds/defensive_rankings_2025-26.json` - Uploaded to VPS

---

## VPS Status

**API:** Running on port 8001
**Scheduler:** Status unknown
**Database:** PostgreSQL on port 5433

---

## Action Items

### High Priority
1. ✅ Fix duplicate game entries - COMPLETED
2. [ ] Sync FanDuel odds to attach betting lines
3. [ ] Verify Ayo Dosunmu is filtered from parlays
4. [ ] Deploy latest code to VPS (whitelist changes)
5. [ ] Fix GameMatcher to prevent future duplicates

### Medium Priority
1. [ ] Improve prediction accuracy (Luka under-prediction issue)
2. [ ] Add recent form/adjacency factors to model
3. [ ] Implement game result verification

### Low Priority
1. [ ] Update documentation
2. [ ] Add more defensive stats
3. [ ] Implement better error handling

---

## Environment Variables

**Required on VPS:**
- `THE_ODDS_API_KEY` - ✅ Configured
- `TELEGRAM_BOT_TOKEN` - ✅ Configured
- `DATABASE_URL` - ✅ Configured

---

## Contact Notes

- User placed bets based on system predictions
- Both bets lost (Luka 46 vs predicted ~22, Jalen 13 vs predicted ~10.5)
- User wants to understand why predictions were off
- FanDuel lines were accurate (33.5 for Luka, 12.5 for Jalen)

---

**Last Updated:** 2026-01-27 08:30 UTC
