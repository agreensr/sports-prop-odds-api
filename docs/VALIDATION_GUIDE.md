# Model Validation Guide

## Quick Reference

### Run Full Validation
```bash
cd /Users/seangreen/Documents/my-projects/sports-bet-ai-api
python3 scripts/validate_model_improvements.py
```

### Run with Real Odds Only (No Estimated Lines)
```bash
python3 scripts/validate_model_improvements.py --no-estimated
```

### Test Specific Game
```bash
python3 scripts/validate_model_improvements.py --game-id GAME_UUID
```

## What Gets Validated

### Tier 1: Rest Days & Injury Filtering
- ✅ Rest days are deterministic (not random)
- ✅ Players filtered by last_game_date
- ✅ Injury filter excludes OUT/DOUBTFUL/QUESTIONABLE
- ✅ Specific players filtered correctly (Jalen Williams)

### Tier 2: Fatigue Scaling
- ✅ Age-adjusted B2B penalties (young < prime < veteran)
- ✅ Non-linear fatigue scaling by minutes
- ✅ Rest days bonus for adequate recovery

### Tier 3: Usage Boost
- ✅ Usage boost in valid range (0-20%)
- ✅ Dynamic opponent adjustment
- ✅ Position-specific usage (bigs vs guards)

### Tier 4: Travel Fatigue
- ✅ Away team travel fatigue calculation
- ✅ Home team has no travel penalty
- ✅ Matchup score in valid range

### Sanity Checks
- ✅ No negative predictions
- ✅ Confidence in valid range [0.40, 0.80]
- ✅ Edge matches recommendation
- ✅ Line source validation

### Test Cases
- ✅ Jaylin Williams appears (healthy)
- ✅ Jalen Williams filtered (not played recently)
- ✅ Young players have lower B2B penalty

## Expected Results

### Successful Run
```
✅ OVERALL: PASS (19/19 tests passed)
```

### Typical Output Time
- 30-60 seconds
- Depends on database size and network

### Files Generated
1. `validation_report.txt` - Plain text summary
2. `docs/model_validation_report.md` - Detailed markdown report

## Troubleshooting

### No Predictions Generated
**Issue:** "No predictions generated"
**Solution:** Run with `--no-estimated` flag disabled (default is enabled)

### Database Connection Error
**Issue:** "could not connect to server"
**Solution:** Ensure PostgreSQL is running on port 5433

### Module Not Found
**Issue:** "ModuleNotFoundError: No module named 'app'"
**Solution:** Run from project root directory

## Maintenance

### Weekly Validation
Run full validation weekly to ensure model stability:
```bash
python3 scripts/validate_model_improvements.py > weekly_validation_$(date +%Y%m%d).txt
```

### After Code Changes
Run validation after any changes to:
- `enhanced_prediction_service.py`
- Player filtering logic
- Fatigue calculations
- Usage boost algorithms

### Monitoring Metrics
Track these metrics over time:
- Prediction accuracy by tier
- Age group performance
- Travel fatigue impact
- Usage boost effectiveness

## Understanding Results

### Age-Adjusted B2B Penalties
```
21yo: -0.070 (7% penalty, recovers fast)
30yo: -0.150 (15% penalty, prime years)
38yo: -0.200 (20% penalty, needs more recovery)
```

### Fatigue Scaling
```
32 min: 100% efficiency (baseline)
36 min:  95% efficiency (-5%)
40 min:  87% efficiency (-13%)
42 min:  75% efficiency (-25% floor)
```

### Travel Fatigue Bands
```
< 500 miles:     0% penalty
500-1000 miles: -1% penalty
1000-1500 miles: -2% penalty
1500-2000 miles: -3% penalty
2000+ miles:     -5% penalty
Altitude (DEN/UTA): Additional -2%
```

## Support

For issues or questions:
1. Check logs in `validation_report.txt`
2. Review detailed report in `docs/model_validation_report.md`
3. Verify database connection: `psql -h localhost -p 5433 -U postgres -d sports_bet_ai`

## Version History

- **v1.0** (2026-01-30): Initial validation with all 4 tiers
- **v1.1** (2026-01-30): Fixed mock player age calculation
- **v1.2** (2026-01-30): Added estimated lines support for testing
