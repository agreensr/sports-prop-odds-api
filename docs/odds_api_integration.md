# Real-Time Odds API Integration

## Overview

The Enhanced Prediction Service now integrates with The Odds API to fetch live bookmaker lines for NBA player props. This integration provides accurate, up-to-date betting lines for generating predictions.

## Architecture

### Components

1. **OddsApiService** (`app/services/core/odds_api_service.py`)
   - Handles all HTTP requests to The Odds API
   - Implements caching to prevent rate limit issues
   - Tracks API quota usage
   - Circuit breaker for error resilience

2. **GameOddsMapper** (`app/services/nba/game_odds_mapper.py`)
   - Maps internal Game IDs to Odds API event IDs
   - Uses tiered lookup strategy:
     1. Cached `odds_api_event_id` on Game model (fastest)
     2. game_mappings table (from sync jobs)
     3. Live Odds API query (fallback)

3. **PlayerPropsParser** (`app/services/nba/player_props_parser.py`)
   - Parses Odds API response data
   - Extracts lines for specific players and stat types
   - Supports multiple bookmakers with priority ordering
   - Handles player name normalization

4. **EnhancedPredictionService** (`app/services/nba/enhanced_prediction_service.py`)
   - Orchestrates the odds fetching pipeline
   - Implements intelligent caching to prevent redundant API calls
   - Populates `odds_fetched_at` and `odds_last_updated` timestamps
   - Falls back to estimated lines when API fails

## Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│ 1. User Request: Generate Predictions                                │
│    generate_prop_predictions(game_id, stat_types, bookmaker)         │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 2. Get Active Players                                               │
│    - Query players for both teams                                   │
│    - Filter by minutes, games played, injury status                 │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 3. For Each Player + Stat Type:                                     │
│                                                                     │
│    a. Calculate Base Projection                                     │
│       - EWMA-weighted recent form                                   │
│       - Contextual adjustments (rest, pace, opponent)               │
│                                                                     │
│    b. Get Bookmaker Line                                            │
│       - Try to fetch real odds from Odds API                        │
│       - Fall back to estimation if unavailable                      │
│                                                                     │
│    c. Calculate Edge & Recommendation                               │
│       - edge = projection - line                                    │
│       - Determine OVER/UNDER/PASS based on edge                     │
│                                                                     │
│    d. Calculate Confidence                                          │
│       - Based on edge magnitude, sample size, volatility            │
└────────────────────────┬────────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│ 4. Return Prediction List                                           │
└─────────────────────────────────────────────────────────────────────┘
```

## Odds Fetching Flow

```
_get_bookmaker_line(player, game, stat_type, bookmaker)
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│ Is Odds API Service Available?                              │
└────────┬──────────────────────────────────────┬─────────────┘
         │ YES                                  │ NO
         ▼                                      ▼
┌─────────────────────────┐         ┌──────────────────────┐
│ Fetch Real Odds         │         │ Estimate from Stats  │
│                         │         │                      │
│ 1. Map Game → Event ID  │         │ - Use season stats   │
│ 2. Check Cache          │         │ - Apply 95% factor   │
│ 3. Fetch Player Props   │         │ - Round to 0.5       │
│ 4. Parse Line Data      │         │                      │
│ 5. Return with          │         │ Return:              │
│    bookmaker name       │         │ line_source =        │
│    fetched_at           │         │   "estimated"        │
│    odds_fetched_at      │         │                      │
│    odds_last_updated    │         │                      │
└─────────────────────────┘         └──────────────────────┘
```

## Caching Strategy

### Two-Level Caching

1. **OddsApiService-Level Cache**
   - Key: `(endpoint, params)`
   - TTL: 5 minutes for player props
   - Prevents redundant API calls across different services

2. **PredictionService-Level Cache**
   - Key: `(game_id, stat_type)`
   - TTL: 5 minutes (configurable)
   - Prevents redundant calls when generating predictions for multiple players

### Cache Flow Example

```python
# First call for Game X, points
player_a_points = _get_bookmaker_line(player_a, game_x, "points", "draftkings")
# → API call made, response cached

# Second call for same game, same stat
player_b_points = _get_bookmaker_line(player_b, game_x, "points", "draftkings")
# → Uses cached response (no API call)

# Different stat type
player_a_rebounds = _get_bookmaker_line(player_a, game_x, "rebounds", "draftkings")
# → New API call (different cache key)

# After 5 minutes
player_c_points = _get_bookmaker_line(player_c, game_x, "points", "draftkings")
# → Cache expired, fresh API call made
```

## Database Fields

### Game Model
- `odds_api_event_id`: Cached Odds API event ID (populated by sync or lookup)

### Prediction Model
- `odds_fetched_at`: Timestamp when odds were first fetched from API
- `odds_last_updated`: Timestamp when odds were last refreshed

### Usage Example

```python
from app.services.nba.enhanced_prediction_service import EnhancedPredictionService
from app.services.core.odds_api_service import OddsApiService
from app.core.config import settings

# Initialize services
odds_service = OddsApiService(api_key=settings.odds_api_key)
prediction_service = EnhancedPredictionService(
    db=db_session,
    odds_api_service=odds_service  # Pass to enable real odds
)

# Generate predictions
predictions = prediction_service.generate_prop_predictions(
    game_id="abc-123",
    stat_types=["points", "rebounds", "assists", "threes"],
    bookmaker="draftkings"
)

# Each prediction includes:
for pred in predictions:
    print(f"Player: {pred['player']}")
    print(f"Stat: {pred['stat_type']}")
    print(f"Line: {pred['line']}")
    print(f"Line Source: {pred['line_source']}")  # "draftkings" or "estimated"
    print(f"Odds Fetched: {pred.get('odds_fetched_at')}")
    print(f"Odds Updated: {pred.get('odds_last_updated')}")
```

## Error Handling

### Fallback Behavior

The service gracefully handles failures:

1. **Odds API Unavailable**
   - Falls back to season stats estimation
   - Sets `line_source = "estimated"`
   - Prediction generation continues

2. **No Lines for Player**
   - Player excluded from predictions
   - Only players with real or estimated lines are included

3. **Circuit Breaker Open**
   - After multiple failures, circuit opens
   - All requests use estimation for cooldown period
   - Prevents cascading failures

### Example Error Log

```
INFO: No odds_event_id found for game abc-123, falling back to estimation
DEBUG: No line found for John Doe points in event xyz-789
INFO: Using estimated line for John Doe points: 15.5
```

## Configuration

### Environment Variables

```bash
# .env file
ODDS_API_KEY=your_api_key_here
DATABASE_URL=postgresql://user:pass@localhost/dbname
```

### Settings

```python
# In EnhancedPredictionService.__init__
self._cache_ttl_seconds = 300  # 5 minutes
self.min_edge_for_bet = 2.0    # Minimum edge to recommend bet
```

## Testing

### Run Integration Test

```bash
# Test full Odds API integration
python scripts/test_odds_api_integration.py

# Test fallback behavior (no API key needed)
python scripts/test_odds_api_integration.py --test-fallback
```

### Test Coverage

The integration test verifies:
1. ✅ Real-time odds fetching from Odds API
2. ✅ Proper caching of odds data
3. ✅ Fallback to estimation when API fails
4. ✅ Timestamp population (odds_fetched_at, odds_last_updated)
5. ✅ Line source tracking
6. ✅ Bookmaker priority handling

## Performance Considerations

### API Rate Limits

- **Free Plan**: 500 requests/month
- **Paid Plan**: 20,000 requests/month (~666/day)
- **Current Usage**: With caching, ~10-20 requests per game
- **Recommended**: Use paid plan for production

### Optimization Tips

1. **Batch Predictions**: Generate all predictions for a game at once
2. **Cache Warming**: Pre-fetch odds before generating predictions
3. **Async Processing**: Use background tasks for prediction generation
4. **Selective Bookmakers**: Only fetch from primary bookmaker

### Example: Efficient Batch Processing

```python
# Good: Generate all predictions at once
predictions = service.generate_prop_predictions(
    game_id="abc-123",
    stat_types=["points", "rebounds", "assists", "threes"],
    bookmaker="draftkings"
)
# → 4 API calls maximum (one per stat type)

# Avoid: Individual player predictions
for player in players:
    pred = service.generate_prediction(player, "points")  # Inefficient
# → N API calls where N = number of players
```

## Monitoring

### Key Metrics

1. **API Quota Usage**
   ```python
   quota_status = odds_service.get_quota_status()
   print(f"Remaining: {quota_status['requests_remaining']}")
   print(f"Used: {quota_status['requests_used']}")
   print(f"Percentage: {quota_status['quota_percentage']}%")
   ```

2. **Cache Hit Rate**
   ```python
   cache_size = len(prediction_service._odds_cache)
   print(f"Cached odds entries: {cache_size}")
   ```

3. **Prediction Sources**
   ```python
   # Track real vs estimated lines
   real_lines = sum(1 for p in predictions if p['line_source'] != 'estimated')
   estimated_lines = len(predictions) - real_lines
   print(f"Real lines: {real_lines}")
   print(f"Estimated lines: {estimated_lines}")
   ```

### Logging

The service logs key events:

```
INFO: Fetching player props for event xyz-789
INFO: Found line for LeBron James points: 25.5 (draftkings)
DEBUG: Using cached odds for game abc-123, stat_type=points
WARNING: No player props data for event xyz-789, falling back to estimation
ERROR: Error fetching real odds for Player Name points: Connection timeout
```

## Troubleshooting

### Issue: No Predictions Generated

**Symptom**: `generate_prop_predictions()` returns empty list

**Possible Causes**:
1. No active players for game (check injury status)
2. No odds data available and estimation disabled
3. API quota exceeded

**Solutions**:
```bash
# Check active players
python -c "from app.services.nba.enhanced_prediction_service import EnhancedPredictionService; \
service = EnhancedPredictionService(db); \
players = service._get_active_players(game); \
print(f'Active players: {len(players)}')"

# Check API quota
python scripts/test_odds_api_integration.py
```

### Issue: All Lines Show "Estimated"

**Symptom**: All predictions have `line_source = "estimated"`

**Possible Causes**:
1. Odds API key not set
2. No odds_event_id for game
3. Player props not available for this game

**Solutions**:
```bash
# Verify API key
echo $ODDS_API_KEY

# Check game mapping
python -c "from app.models import Game; from app.db import get_db; \
game = get_db().query(Game).first(); \
print(f'odds_api_event_id: {game.odds_api_event_id}')"

# Run sync job to populate mappings
python scripts/sync_nba_games.py
```

### Issue: High API Usage

**Symptom**: Quota depleting too quickly

**Possible Causes**:
1. Cache not working
2. Redundant API calls
3. Generating predictions too frequently

**Solutions**:
- Increase cache TTL
- Batch predictions
- Use background jobs with intervals

## Future Enhancements

1. **Opening Odds**
   - Currently using current line for both `line` and `line_open`
   - TODO: Fetch historical opening odds

2. **Line Movement Tracking**
   - Store historical line changes
   - Adjust confidence based on sharp vs public money

3. **Multi-Bookmaker Aggregation**
   - Fetch from multiple bookmakers
   - Use consensus lines for predictions

4. **WebSocket Updates**
   - Real-time odds updates
   - Push notifications for line changes

## Related Files

- `/app/services/core/odds_api_service.py` - Odds API client
- `/app/services/nba/game_odds_mapper.py` - Game to event mapping
- `/app/services/nba/player_props_parser.py` - Response parsing
- `/app/services/nba/enhanced_prediction_service.py` - Main prediction logic
- `/scripts/test_odds_api_integration.py` - Integration tests
- `/app/models/nba/models.py` - Database models
