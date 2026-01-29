# Model Architecture Decision: Single Table vs Separate Tables

## The Short Answer

**Keep separate tables per sport.** Your product is sport-specific (users ask for NBA predictions or NFL predictions, not "give me predictions across all sports"). You don't need cross-sport operations in your core product flows.

## Current State (Hybrid Approach)

Your codebase uses a **hybrid approach**:

| Entity | NBA | NFL | MLB | NHL |
|--------|-----|-----|-----|-----|
| Players | `players` (unified) | `nfl_players` | `mlb_players` | `nhl_players` |
| Games | `games` (unified) | `nfl_games` | `mlb_games` | `nhl_games` |
| Predictions | `predictions` (unified) | `nfl_predictions` | `mlb_predictions` | `nhl_predictions` |

**Why this happened:** NBA was the first sport (your "primary" product), and newer sports were added with separate tables to avoid disrupting the working NBA system.

---

## Option 1: Single Table (Fully Unified)

### Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                      players                                 │
├─────────────────────────────────────────────────────────────┤
│ id (PK) │ sport_id │ name  │ team │ position │ nba_api_id │ ...
├─────────────────────────────────────────────────────────────┤
│   1     │   nba    │ LeBron│ LAL  │    SF    │   2544    │
│   2     │   nba    │ Steph │ GSW  │    PG    │   201939  │
│   3     │   nfl    │ Mahomes│ KC  │    QB    │   NULL    │
│   4     │   nfl    │ Allen │ BUF  │    QB    │   NULL    │
└─────────────────────────────────────────────────────────────┘
```

### Benefits

| Benefit | Explanation | Impact on Your Codebase |
|---------|-------------|-------------------------|
| **Shared Code** | One service class can handle all sports | `BasePredictionService` works as-is |
| **Consistent Schema** | Same column names everywhere | Frontend code is simpler |
| **Adding New Sports** | Just add rows, not new tables | Adding MLS/soccer is trivial |
| **Referential Integrity** | Foreign keys work naturally | No complex join conditions |
| **Simpler Migrations** | One set of tables to evolve | Less migration overhead |

### Constraints

| Constraint | Mitigation |
|-----------|------------|
| Sparse columns (NFL has `passing_yards`, NBA has `threes`) | Use JSONB column for sport-specific stats |
| Larger table size (~50K rows vs ~10K per sport) | Index on `sport_id` makes queries fast |
| Sport-specific validation logic | Use SQLAlchemy `@validates` with conditional logic |
| Migration complexity (need to merge existing tables) | One-time migration script required |

### Example Query (Single Sport - Your Typical Use Case)
```sql
-- Still simple and readable
SELECT p.name, pr.stat_type, pr.predicted_value
FROM predictions pr
JOIN players p ON pr.player_id = p.id
WHERE pr.sport_id = 'nba'
  AND pr.confidence > 0.70
ORDER BY pr.confidence DESC
LIMIT 10;
```

---

## Option 2: Separate Tables (Per Sport)

### Architecture
```
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│   nba_players    │  │   nfl_players    │  │   mlb_players    │
├──────────────────┤  ├──────────────────┤  ├──────────────────┤
│ id (PK)          │  │ id (PK)          │  │ id (PK)          │
│ name             │  │ name             │  │ name             │
│ team             │  │ team             │  │ team             │
│ position         │  │ position         │  │ position         │
│ threes_made      │  │ passing_yards    │  │ home_runs        │
│ ...              │  │ ...              │  │ ...              │
└──────────────────┘  └──────────────────┘  └──────────────────┘
```

### Benefits

| Benefit | Explanation | Impact on Your Codebase |
|---------|-------------|-------------------------|
| **Sport-Specific Columns** | No NULL columns for irrelevant stats | `nfl_players.passing_yards` is clean |
| **Independent Validation** | Each sport has its own model rules | NFL QB logic doesn't leak to NBA |
| **Isolated Failures** | Issue with NFL doesn't affect NBA | Safer production deployments |
| **Per-Sport Indexing** | Optimized indexes per sport | NBA indexes on `threes`, NFL on `passing_yards` |
| **Zero Migration** | No data movement required | Current code keeps working |
| **Easier to Delete** | Drop sport = drop tables | Removing MLS is `DROP TABLE mlb_*` |

### Constraints

| Constraint | Mitigation |
|-----------|------------|
| Duplicated code (4x Player models) | Use mixins or composition |
| Adding new sport = create new tables | Code generation / scaffolding |
| Harder to share services | Each sport needs its own service class |

### Example Query (Your Typical Use Case)
```sql
-- Simple and straightforward
SELECT p.name, pr.stat_type, pr.predicted_value
FROM nba_predictions pr
JOIN nba_players p ON pr.player_id = p.id
WHERE pr.confidence > 0.70
ORDER BY pr.confidence DESC
LIMIT 10;
```

---

## Recommendation for Your Codebase

### Stick with **Separate Tables** (Current Approach) - Here's Why:

1. **NBA is your cash cow** - It's the primary product with the most users. Don't risk breaking it.

2. **Sports have fundamentally different stats:**
   - NBA: points, rebounds, assists, threes, minutes
   - NFL: passing_yards, rushing_yards, receptions, interceptions
   - MLB: home_runs, rbis, batting_average, era
   - NHL: goals, assists, plus_minus, saves

   These don't normalize well into a single schema without heavy use of JSONB or sparse columns.

3. **You already have `BasePredictionService`** - This abstracts the common logic while allowing each sport to have its own models. This is the right pattern for multi-sport with divergent schemas.

4. **Zero migration risk** - Merging tables requires:
   - Hours of downtime
   - Complex data migration scripts
   - Testing every edge case
   - Rollback plan if something breaks

5. **Per-sport isolation is valuable:**
   - If NFL has a data quality issue, it doesn't affect NBA
   - You can tune indexes per sport
   - Different retention policies per sport

---

## If You Want to Improve the Current Architecture

Instead of merging tables, consider these improvements:

### 1. Create a Shared Interface/Protocol
```python
# app/models/shared.py
from abc import ABC, abstractmethod

class PlayerModel(ABC):
    """Interface that all sport-specific Player models must implement."""

    @abstractmethod
    def get_sport_id(self) -> str:
        """Return the sport identifier."""
        pass

    @abstractmethod
    def get_display_name(self) -> str:
        """Return player's display name."""
        pass

    @abstractmethod
    def get_team(self) -> str:
        """Return player's team abbreviation."""
        pass
```

### 2. Use Code Generation for New Sports
Since each sport follows the same pattern, create a script to scaffold new sports:

```bash
# Add a new sport in minutes
python scripts/add_sport.py --sport=mlb --name="MLB" --stats="home_runs,rbis,batting_average"
```

This generates:
- `app/models/mlb/models.py`
- `app/services/mlb/prediction_service.py`
- `app/api/routes/mlb/predictions.py`

### 3. Use JSONB for Sport-Specific Stats (Hybrid Approach)
Keep the main tables separate, but use JSONB for stats that vary wildly:

```python
# Instead of separate stat columns
class PlayerStats(Base):
    __tablename__ = "player_stats"

    id = Column(String(36), primary_key=True)
    player_id = Column(String(36), ForeignKey("players.id"))
    sport_id = Column(String(3), nullable=False)

    # Common stats
    games_played = Column(Integer)

    # Sport-specific stats (flexible!)
    stats_json = Column(JSONB, nullable=False)
    # Example NBA: {"points": 25.4, "threes": 3.2, "assists": 8.1}
    # Example NFL: {"passing_yards": 284, "touchdowns": 2, "interceptions": 0}
```

---

## Decision Matrix

| Criteria | Single Table | Separate Tables | Winner |
|----------|-------------|-----------------|--------|
| Code reusability | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | Separate |
| Schema clarity | ⭐⭐ | ⭐⭐⭐⭐⭐ | Separate |
| Migration risk | ⭐ | ⭐⭐⭐⭐⭐ | Separate |
| Adding new sports | ⭐⭐⭐⭐⭐ | ⭐⭐ | Single |
| Per-sport optimization | ⭐⭐ | ⭐⭐⭐⭐⭐ | Separate |
| Fault isolation | ⭐⭐ | ⭐⭐⭐⭐⭐ | Separate |
| Query performance (single sport) | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | Separate |

---

## Final Verdict

**Keep Separate Tables** for the core entities (Players, Games, Season Stats).

**Why this is right for your product:**
1. **Your queries are sport-specific** - Users ask for NBA predictions or NFL predictions, not cross-sport
2. **Stats don't overlap** - Passing yards vs three-pointers vs home runs are fundamentally different
3. **You already have `BasePredictionService`** - Code reuse is handled at the service layer, not schema layer
4. **Zero migration risk** - No need to move data around
5. **Fault isolation** - Issues with NFL don't affect your cash cow (NBA)
