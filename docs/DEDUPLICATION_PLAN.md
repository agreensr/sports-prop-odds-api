# Game Deduplication Plan

## Summary
Successfully removed **93 duplicate game entries** from the database. Created deduplication script to prevent future issues.

## What Was Fixed

### Critical Duplicates (with predictions)
| Matchup | Date | Predictions Moved | Action |
|---------|------|-------------------|--------|
| CHI@MIN | 2026-01-22 | 168 | Kept NBA API, deleted TheOddsAPI |
| GSW@MIN | 2026-01-27 | 152+164 | Kept NBA API, deleted TheOddsAPI |
| **LAL@CHI** | **2026-01-27** | **159+160** | **Kept NBA API, deleted TheOddsAPI** |
| MEM@HOU | 2026-01-27 | 148+175 | Kept NBA API, deleted TheOddsAPI |
| POR@BOS | 2026-01-27 | 152+173 | Kept NBA API, deleted TheOddsAPI |

### Non-Critical Duplicates (no predictions)
- 88 additional duplicates removed
- No data loss

## Root Cause

**Two data sources creating separate games for the same matchup:**

1. **NBA API** - Creates games with external_id like `0022500661`
2. **TheOddsAPI** - Creates games with external_id like `401705153` or hash strings

The GameMatcher service was supposed to prevent this, but the deduplication wasn't working properly.

## Prevention Plan

### 1. Fix GameMatcher (HIGH PRIORITY)

**File:** `app/services/sync/matchers/game_matcher.py`

**Changes needed:**
```python
def find_or_create_game(self, nba_game_id: str, odds_event_id: str) -> Game:
    """
    Find existing game or create new one.

    Priority:
    1. Check if NBA game already exists
    2. If yes, link odds_event_id to it (update game_mapping)
    3. If no, create new game with both IDs
    """
    # Check if NBA game exists
    existing = self.db.query(Game).filter(
        Game.external_id == nba_game_id
    ).first()

    if existing:
        # Link odds_event to existing game
        self._link_odds_to_game(existing, odds_event_id)
        return existing
    else:
        # Create new game
        return self._create_game(nba_game_id, odds_event_id)
```

### 2. Add Unique Constraint (MEDIUM PRIORITY)

**File:** `migrations/016_add_game_uniqueness_constraint.sql`

```sql
-- Add unique constraint on away_team + home_team + game_date
-- This prevents duplicates at database level

ALTER TABLE games DROP CONSTRAINT IF EXISTS games_unique_matchup;
ALTER TABLE games ADD CONSTRAINT games_unique_matchup
UNIQUE (away_team, home_team, DATE(game_date));

-- Handle existing violations before adding constraint
-- (This should be done after cleanup)
```

### 3. Improve Sync Orchestrator (MEDIUM PRIORITY)

**File:** `app/services/sync/orchestrator.py`

**Changes:**
- Check for existing games before creating new ones
- Use game_mapping table to link sources
- Log when games are skipped due to duplicates

### 4. Scheduled Deduplication (LOW PRIORITY)

**Add to scheduler:**
```python
# Run daily deduplication check
scheduler.add_job(
    deduplicate_games,
    'cron',
    hour=3,  # 3 AM daily
    id='deduplication_check'
)
```

### 5. Monitoring (LOW PRIORITY)

**Add alerting:**
- Log when duplicate games are created
- Send notification if duplicate count > 0
- Track duplicate creation rate

## Tools Created

### 1. Deduplication Script
**Location:** `scripts/deduplicate_games.py`

**Usage:**
```bash
# Preview changes
python scripts/deduplicate_games.py --dry-run

# Apply changes
python scripts/deduplicate_games.py --execute

# Show statistics
python scripts/deduplicate_games.py --stats
```

**Strategy:**
- Keep NBA API games (official source)
- Move predictions from duplicates
- Delete TheOddsAPI duplicates

### 2. Status Endpoint
**Location:** Can add to `/api/sync/status`

**Response:**
```json
{
  "duplicate_games": 0,
  "last_deduplication": "2026-01-27T14:30:00Z",
  "status": "healthy"
}
```

## Verification

### Before Deduplication
- Total games: 2161
- Duplicate matchups: 93
- Critical duplicates: 5 (with predictions)

### After Deduplication
- Total games: 2068
- Duplicate matchups: 0
- Predictions preserved: All moved to correct games

## Next Steps

1. ✅ **Complete**: Run deduplication script
2. 🔄 **In Progress**: Fix GameMatcher to prevent new duplicates
3. 📋 **Todo**: Add database constraint
4. 📋 **Todo**: Add scheduled deduplication check
5. 📋 **Todo**: Set up monitoring/alerting

## Files Modified

- `scripts/deduplicate_games.py` - Created
- `APP_STATUS.md` - Updated

## Contact

For questions or issues, refer to:
- APP_STATUS.md for current system status
- game_matcher.py for matching logic
- sync orchestrator for sync process

---

**Last Updated:** 2026-01-27
**Status:** Active prevention plan
