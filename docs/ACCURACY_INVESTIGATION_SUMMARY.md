# NBA Prediction Accuracy Investigation - Session Summary

**Date:** January 31, 2026

## Overview

This session investigated why OVER predictions were failing while UNDER predictions were winning, leading to several critical bug fixes and improvements to the prediction system.

## Key Findings

### 1. Timezone Bug Fixed ⚠️

**Problem:** Game times displayed 6 hours off
- ESPN API returns UTC times correctly
- But database was storing Central Time as UTC
- When converted to EST for display, times were wrong

**Example:**
- NOP @ PHI: showing 1:30 PM EST → fixed to 7:30 PM EST ✓
- ATL @ IND: showing 1:00 PM EST → fixed to 7:00 PM EST ✓

**Root Cause:**
- `ESPNApiService._parse_espn_date()` was converting UTC to Central Time
- Then storing Central Time in UTC column (double conversion bug)

**Fix:**
- Modified ESPN service to return raw UTC (no timezone conversion)
- Store UTC in database
- Convert to EST only for display

### 2. was_correct Calculation Bug Fixed 🐛

**Problem:** `was_correct` was comparing `actual vs predicted_value` instead of `actual vs bookmaker_line`

**Old Logic (Wrong):**
```python
if recommendation == "OVER":
    was_correct = actual_value > predicted_value  # ❌ Wrong!
```

**New Logic (Correct):**
```python
line = bookmaker_line or predicted_value  # Use bookmaker line when available
if recommendation == "OVER":
    was_correct = actual_value > line  # ✓ Correct!
```

**Impact:** Historical accuracy stats (35.8% OVER, 73.5% UNDER) were **meaningless** because they compared against our projection, not the bookmaker line.

### 3. OVER vs UNDER Investigation

**Discovery:** Old predictions (828) had NO `bookmaker_line` - they were generated before Odds API integration

| Stat | OVER Win Rate | UNDER Win Rate | Issue |
|------|--------------|----------------|-------|
| Points | 35.8% | 73.5% | No lines - comparing to own projection |
| Rebounds | 19.2% | 67.6% | No lines |
| Assists | 36.2% | 62.6% | No lines |
| Threes | 25.0% | 53.6% | No lines |

**New predictions (1,359)** now have bookmaker lines from Odds API ✓

## First Real Accuracy Data

### SAS @ CHA (Jan 31, 2026) - First Game with Bookmaker Lines

| Recommendation | Wins | Total | Win Rate |
|--------------|------|-------|----------|
| OVER | 0 | 1 | 0.0% |
| UNDER | 20 | 23 | **87.0%** |

**Notable Predictions:**
- Wembanyama points: pred=28.6, line=24.0, actual=16.0 (OVER lost - over-predicted)
- Miles Bridges: pred=31.0, line=28.5, actual=16.0 (UNDER won)
- Brandon Miller: pred=14.8, line=19.0, actual=6.0 (UNDER won)

## Changes Made

### 1. ESPN Service (`app/services/core/espn_service.py`)
- `_parse_espn_date()` now returns raw UTC instead of Central Time
- Added comment explaining UTC storage for database

### 2. Timezone Utils (`app/utils/timezone.py`)
- Added `utc_to_eastern()` function
- Added `format_game_time_eastern()` function
- Updated documentation to reflect EST display instead of CST

### 3. Predictions API (`app/api/routes/nba/predictions.py`)
- Updated to use `utc_to_eastern()` for display
- Changed from `date_central` to `date_est` in response

### 4. Boxscore Import (`app/services/nba/boxscore_import_service.py`)
- Fixed `was_correct` calculation to use `bookmaker_line`
- Falls back to `predicted_value` for legacy data without lines

### 5. Database Changes
- Resynced 51 games with correct UTC times
- Regenerated 986 predictions with proper time data

## Current State

| Metric | Value |
|--------|-------|
| Predictions with bookmaker lines | 1,359 (pending) |
| Predictions with lines resolved | 24 (SAS @ CHA) |
| OVER accuracy (first real data) | 0.0% (0/1) |
| UNDER accuracy (first real data) | 87.0% (20/23) |

## Pending

- Monitoring script running on server (PID 1867627)
- Checking for completed games every 3 minutes
- Will automatically resolve predictions as games finish
- Upcoming games tonight: ATL @ IND (7pm), NOP @ PHI (7:30pm), CHI @ MIA (8pm), MIN @ MEM (8pm), DAL @ HOU (8:30pm)

## Key Insights

1. **Historical accuracy stats were misleading** - they compared actual vs our projection, not actual vs bookmaker line
2. **UNDER bias persists even with correct logic** - 87% UNDER win rate in first real data
3. **Model calibration may still be too aggressive** - STAT_CALIBRATION factors of 0.70-0.90 might be over-correcting
4. **Time zone handling is critical** - small bugs in timezone conversion cause 6-hour errors

## Next Steps

1. **Wait for more games to complete** - need larger sample size for meaningful stats
2. **Analyze calibration factors** - if UNDER wins at 87%, model is too conservative
3. **Consider UNDER-only strategy** - if bias persists, optimize for what works
4. **Monitor prediction quality** - track edge (predicted - line) vs actual outcome

## Files Modified

- `app/services/core/espn_service.py` - UTC timezone fix
- `app/utils/timezone.py` - Added EST functions
- `app/api/routes/nba/predictions.py` - EST display
- `app/services/nba/boxscore_import_service.py` - was_correct fix
- `scripts/resync_espn_schedule.py` - Game resync with correct times
- `scripts/recalculate_accuracy.py` - Historical recalculation script
- `scripts/monitor_and_resolve.py` - Background monitor for game completion
- `scripts/resolve_simple.py` - Manual game resolution script
- `scripts/check_progress.py` - Progress check script

## Technical Notes

- All times now stored in UTC
- Display times in Eastern Time (EST)
- Bookmaker lines from Odds API v4
- ESPN API used for game status and boxscores
- PostgreSQL database on remote server (seanbot.fun)
