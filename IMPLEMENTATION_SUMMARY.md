# Prediction Accuracy Testing Framework - Implementation Summary

## Overview

A comprehensive testing framework has been created to measure and analyze prediction accuracy across multiple dimensions. The framework provides detailed insights into model performance, calibration, and areas for improvement.

## Files Created

### 1. Main Script
**File**: `/Users/seangreen/Documents/my-projects/sports-bet-ai-api/scripts/test_prediction_accuracy.py`
**Size**: 22KB
**Purpose**: Core accuracy testing engine

Features:
- Fetches resolved predictions from `prediction_tracking` table
- Calculates 8+ accuracy metrics
- Generates detailed reports by multiple dimensions
- Supports filtering (stat type, confidence, date range)
- Outputs human-readable or JSON format

### 2. Documentation
**File**: `/Users/seangreen/Documents/my-projects/sports-bet-ai-api/scripts/PREDICTION_ACCURACY_README.md`
**Size**: 11KB
**Purpose**: Comprehensive usage guide

Contents:
- Detailed explanation of all report sections
- Interpretation guidelines for each metric
- Troubleshooting common issues
- Best practices for accuracy tracking
- Integration examples with CI/CD
- Advanced analysis techniques

### 3. Quick Reference
**File**: `/Users/seangreen/Documents/my-projects/sports-bet-ai-api/scripts/ACCURACY_TEST_QUICKSTART.md`
**Size**: 2KB
**Purpose**: Fast lookup for common commands

Contents:
- Common command patterns
- Key metrics reference table
- Troubleshooting tips
- Quick workflow overview

### 4. Daily Automation
**File**: `/Users/seangreen/Documents/my-projects/sports-bet-ai-api/scripts/daily_accuracy_report.sh`
**Purpose**: Automated daily reporting

Features:
- Creates timestamped reports
- Exports JSON for historical tracking
- Health check with color-coded warnings
- Summary statistics display
- Error handling with exit codes

## Key Metrics Calculated

### Overall Performance
1. **Total Predictions**: Sample size
2. **Correct/Incorrect**: Win-loss record
3. **Accuracy Rate**: Percentage correct
4. **Mean Absolute Error (MAE)**: Average prediction error in points
5. **Mean Signed Error**: Prediction bias (over/underestimation)
6. **Average Confidence**: Model's average confidence level
7. **Average Edge**: Value over bookmaker lines
8. **Calibration Error**: How well confidence matches reality

### Dimensional Analysis
1. **Confidence Buckets**: Accuracy by confidence level (50-59%, 60-69%, 70-79%, 80-89%, 90-100%)
2. **Stat Types**: Breakdown by points, rebounds, assists, etc.
3. **Recommendation Types**: OVER vs UNDER performance
4. **Edge Magnitude**: Small, medium, large, huge edges
5. **Player Performance**: Best/worst performing players (min 5 predictions)
6. **Extreme Predictions**: Biggest overestimates and underestimates

## Usage Examples

### Basic Usage
```bash
# Generate full report
python3 scripts/test_prediction_accuracy.py

# Points predictions only
python3 scripts/test_prediction_accuracy.py --stat-type points

# High confidence only (80%+)
python3 scripts/test_prediction_accuracy.py --min-confidence 0.80

# Last 7 days
python3 scripts/test_prediction_accuracy.py --days-back 7
```

### Output Options
```bash
# Save to file
python3 scripts/test_prediction_accuracy.py --output report.txt

# Export JSON
python3 scripts/test_prediction_accuracy.py --json > report.json

# Combined
python3 scripts/test_prediction_accuracy.py --json --output report.json
```

### Daily Automation
```bash
# Run daily report
./scripts/daily_accuracy_report.sh
```

Output:
- `reports/accuracy_YYYYMMDD.txt` - Human-readable report
- `data/json/accuracy_YYYYMMDD.json` - Machine-readable data
- Console summary with health checks

## Report Interpretation

### Example Output Analysis

```
OVERALL PERFORMANCE
--------------------------------------------------------------------------------
Total Predictions:     500
Correct:               340 (68.0%)
Incorrect:             160 (32.0%)
Mean Absolute Error:   4.2 points
Mean Signed Error:     +0.3 points (bias)
Average Confidence:    76.5%
Average Edge:          +3.2%
Calibration Error:     8.5% (lower is better)
```

**Interpretation**:
- 68% accuracy is good (breakeven is ~52.4% at -110 odds)
- +0.3 bias = slight overestimation, well-calibrated
- +3.2% edge = model finding value vs bookmakers
- 8.5% calibration error = acceptable, room for improvement
- 76.5% avg confidence vs 68% actual = slight overconfidence

**Action Items**:
1. Monitor calibration error, recalibrate if > 10%
2. Investigate why OVER/UNDER rates differ (if applicable)
3. Review worst-performing stat types
4. Check edge calculation for correlation with accuracy

## Health Checks

The daily automation script includes automatic health checks:

- **Calibration Error > 15%**: Model needs recalibration (RED warning)
- **Calibration Error > 10%**: Monitor closely (YELLOW warning)
- **Calibration Error < 10%**: Acceptable (GREEN)
- **Sample size < 10**: Results may not be representative (YELLOW warning)

## Integration with Existing Workflow

### Prerequisites
Before running accuracy tests:
1. Generate predictions using existing prediction service
2. Run `update_prediction_tracking.py` to fetch actual results from NBA API
3. Ensure predictions have `actual_resolved_at` populated

### Typical Workflow
```bash
# 1. Generate predictions (existing workflow)
python scripts/generate_predictions.py

# 2. After games complete, update with actual results
python scripts/update_prediction_tracking.py

# 3. Test accuracy
python scripts/test_prediction_accuracy.py --output reports/latest.txt
```

### Automation (Recommended)
```bash
# Add to crontab for daily execution
0 6 * * * /path/to/sports-bet-ai-api/scripts/daily_accuracy_report.sh >> /var/log/accuracy.log 2>&1
```

## Data Source

The script reads from the `prediction_tracking` table:

```sql
SELECT * FROM prediction_tracking
WHERE actual_resolved_at IS NOT NULL
  AND actual_value IS NOT NULL
  AND is_correct IS NOT NULL;
```

Key columns used:
- `predicted_value`: Model's prediction
- `actual_value`: Actual game result
- `is_correct`: Was the recommendation (OVER/UNDER) correct?
- `difference`: predicted_value - actual_value
- `confidence`: Model's confidence score (0-1)
- `edge`: Value over bookmaker line
- `stat_type`: points, rebounds, assists, etc.

## Technical Implementation

### Architecture
- **Language**: Python 3.8+
- **Database**: PostgreSQL via SQLAlchemy
- **Output**: Text or JSON format
- **Dependencies**: sqlalchemy, statistics, collections

### Key Classes
- `AccuracyAnalyzer`: Main analysis engine
  - `fetch_predictions()`: Query database with filters
  - `calculate_overall_metrics()`: Summary statistics
  - `get_confidence_buckets()`: Group by confidence
  - `get_stat_type_metrics()`: Breakdown by stat type
  - `get_edge_buckets()`: Group by edge magnitude
  - `get_best_performers()` / `get_worst_performers()`: Player rankings
  - `get_extreme_predictions()`: Outlier analysis
  - `generate_report()`: Formatted output

### Error Handling
- Validates input parameters (confidence range, etc.)
- Handles empty result sets gracefully
- Provides helpful error messages
- Exit codes for automation (0 = success, 1 = failure)

## Benefits

1. **Model Monitoring**: Track accuracy trends over time
2. **Calibration Detection**: Identify overconfidence issues
3. **Weakness Identification**: Find underperforming stat types/players
4. **Value Assessment**: Verify edge calculations correlate with accuracy
5. **Bias Detection**: Catch systematic over/underestimation
6. **Historical Tracking**: JSON export for trend analysis
7. **Automated Alerting**: Health checks warn of issues

## Next Steps

1. **Run Initial Baseline**: Establish current accuracy metrics
2. **Set Targets**: Define acceptable thresholds (e.g., 65% accuracy, <10% calibration error)
3. **Schedule Regular Reports**: Daily automated checks
4. **Track Trends**: Monitor accuracy changes over time
5. **Investigate Issues**: Deep dive into identified weaknesses
6. **Iterate**: Use insights to improve model features/calibration

## Sample Output

```
================================================================================
PREDICTION ACCURACY REPORT
================================================================================

OVERALL PERFORMANCE
--------------------------------------------------------------------------------
Total Predictions:     14
Correct:               9 (64.3%)
Incorrect:             5 (35.7%)
Mean Absolute Error:   5.55 points
Mean Signed Error:     +0.59 points (bias)
Average Confidence:    79.0%
Average Edge:          -57.86%
Calibration Error:     25.5% (lower is better)

ACCURACY BY CONFIDENCE BUCKET
--------------------------------------------------------------------------------
70%-79%: 4/4 (100.0%)

ACCURACY BY STAT TYPE
--------------------------------------------------------------------------------
points             9/  14 ( 64.3%)  MAE: 5.55

ACCURACY BY RECOMMENDATION TYPE
--------------------------------------------------------------------------------
OVER      5/   7 ( 71.4%)  MAE: 5.54
UNDER     4/   7 ( 57.1%)  MAE: 5.56

ACCURACY BY EDGE MAGNITUDE
--------------------------------------------------------------------------------
small (0-2%)            4/   7 ( 57.1%)
huge (10%+)             5/   7 ( 71.4%)

LARGEST OVERESTIMATES (predicted - actual)
--------------------------------------------------------------------------------
Tyrese Maxey              points  : Pred 26.8 vs Actual 40.0 (Diff: +13.2)
Kyshawn George            points  : Pred 13.8 vs Actual 23.0 (Diff: +9.2)
Bobby Portis              points  : Pred 12.5 vs Actual 19.0 (Diff: +6.5)
...

================================================================================
END OF REPORT
================================================================================
```

## Support

For detailed information:
- Full documentation: `scripts/PREDICTION_ACCURACY_README.md`
- Quick reference: `scripts/ACCURACY_TEST_QUICKSTART.md`
- Help: `python3 scripts/test_prediction_accuracy.py --help`

## Version

v1.0 - Initial release (2026-01-30)
