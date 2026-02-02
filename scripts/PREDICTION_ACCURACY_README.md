# Prediction Accuracy Testing Framework

Comprehensive testing framework for measuring prediction accuracy across multiple dimensions.

## Overview

The `test_prediction_accuracy.py` script analyzes resolved predictions from the `prediction_tracking` table and generates detailed accuracy reports. It helps identify model strengths, weaknesses, and calibration issues.

## Prerequisites

- Database with resolved predictions (run `update_prediction_tracking.py` first)
- Python 3.8+
- Database credentials configured in `.env`

## Quick Start

### Basic Usage

```bash
# Generate full accuracy report
python scripts/test_prediction_accuracy.py

# View help
python scripts/test_prediction_accuracy.py --help
```

### Common Filters

```bash
# Filter by stat type
python scripts/test_prediction_accuracy.py --stat-type points

# Only high-confidence predictions (80%+)
python scripts/test_prediction_accuracy.py --min-confidence 0.80

# Last 30 days only
python scripts/test_prediction_accuracy.py --days-back 30

# Combine filters
python scripts/test_prediction_accuracy.py --stat-type points --min-confidence 0.70 --days-back 7
```

### Output Options

```bash
# Save report to file
python scripts/test_prediction_accuracy.py --output accuracy_report.txt

# Export as JSON for further analysis
python scripts/test_prediction_accuracy.py --json > accuracy_data.json

# Save JSON to file
python scripts/test_prediction_accuracy.py --json --output accuracy_report.json
```

## Report Sections

### 1. Overall Performance

Key metrics for total prediction set:
- **Total Predictions**: Sample size
- **Correct/Incorrect**: Win-loss record
- **Accuracy Rate**: Percentage of correct predictions
- **Mean Absolute Error (MAE)**: Average deviation from actual (points)
- **Mean Signed Error**: Prediction bias (positive = overestimates, negative = underestimates)
- **Average Confidence**: Model's average confidence level
- **Average Edge**: Average value edge over bookmaker line
- **Calibration Error**: How well confidence matches actual accuracy (lower is better)

### 2. Accuracy by Confidence Bucket

Groups predictions by confidence level:
- 50%-59%: Low confidence
- 60%-69%: Medium-low confidence
- 70%-79%: Medium-high confidence
- 80%-89%: High confidence
- 90%-100%: Very high confidence

**Interpretation**: Higher confidence buckets should have higher accuracy rates. If 80%-89% bucket only hits 60%, model is overconfident (calibration issue).

### 3. Accuracy by Stat Type

Breakdown by prediction category:
- points, rebounds, assists, threes, etc.

**Interpretation**: Identify which stat types the model predicts best/worst.

### 4. Accuracy by Recommendation Type

OVER vs UNDER performance:
- OVER: Predicted value > bookmaker line
- UNDER: Predicted value < bookmaker line

**Interpretation**: If OVER hits 75% but UNDER hits 55%, model has bias toward OVER recommendations.

### 5. Accuracy by Edge Magnitude

Groups predictions by edge size (value):
- Small (0-2%): Minimal value
- Medium (2-5%): Moderate value
- Large (5-10%): High value
- Huge (10%+): Very high value

**Interpretation**: Larger edges should theoretically correlate with higher accuracy. If not, edge calculation may be flawed.

### 6. Top Performing Players

Best accuracy rates (minimum 5 predictions).

**Interpretation**: Identifies players model understands well. Consider why these players are easier to predict.

### 7. Lowest Performing Players

Worst accuracy rates (minimum 5 predictions).

**Interpretation**: Identifies players model struggles with. May indicate:
- Inconsistent playing time
- Role changes
- Injury-prone
- Model lacks key features for these players

### 8. Largest Overestimates/Underestimates

Specific predictions with biggest errors.

**Interpretation**:
- **Overestimates**: Model predicted high, player performed low (injury? bench? matchup?)
- **Underestimates**: Model predicted low, player exploded (breakout game? garbage time?)

## Using the Reports

### Daily Workflow

```bash
# 1. Update predictions with actual results (run first)
python scripts/update_prediction_tracking.py

# 2. Generate accuracy report
python scripts/test_prediction_accuracy.py --output "reports/accuracy_$(date +%Y%m%d).txt"

# 3. Export JSON for historical tracking
python scripts/test_prediction_accuracy.py --json --output "data/accuracy_$(date +%Y%m%d).json"
```

### Analyzing Model Performance

1. **Check Calibration Error**
   - Should be < 10%
   - High values indicate confidence doesn't match reality

2. **Review Confidence Buckets**
   - 90%+ predictions should hit 90%+
   - 70-79% should hit ~75%
   - If not, recalibrate confidence scoring

3. **Identify Stat Type Issues**
   - If points: 70%, rebounds: 55%, assists: 60%
   - Investigate why rebounds model underperforms
   - May need different features or weights

4. **Check Mean Signed Error**
   - Positive (+2.5): Model consistently overestimates
   - Negative (-1.2): Model consistently underestimates
   - Near zero (±0.5): Well-calibrated

5. **Evaluate Edge Performance**
   - If huge edges (10%+) don't outperform small edges
   - Edge calculation may be flawed
   - Or model already accounts for edge in confidence

### Tracking Progress Over Time

```bash
# Weekly accuracy comparison
for day in {0..6}; do
    date=$(date -d "$day days ago" +%Y%m%d)
    echo "=== $date ==="
    python scripts/test_prediction_accuracy.py --days-back 1 --min-confidence 0.70
done
```

## Advanced Analysis

### Export to CSV for Further Analysis

```python
import json
import pandas as pd

# Load JSON report
with open('accuracy_report.json') as f:
    data = json.load(f)

# Convert to DataFrames
overall_df = pd.DataFrame([data['overall']])
stat_type_df = pd.DataFrame.from_dict(data['stat_type_metrics'], orient='index')
confidence_df = pd.DataFrame.from_dict(data['confidence_buckets'], orient='index')

# Export to CSV
overall_df.to_csv('overall_metrics.csv', index=False)
stat_type_df.to_csv('stat_type_accuracy.csv')
confidence_df.to_csv('confidence_calibration.csv')
```

### Compare Model Versions

```bash
# Filter by date range for each model version
python scripts/test_prediction_accuracy.py --days-back 30 --output model_v1.txt

# Then after model update
python scripts/test_prediction_accuracy.py --days-back 30 --output model_v2.txt

# Compare results
diff model_v1.txt model_v2.txt
```

## Integration with CI/CD

Add to automated testing pipeline:

```yaml
# .github/workflows/accuracy_test.yml
name: Prediction Accuracy Test

on:
  schedule:
    - cron: '0 6 * * *'  # Daily at 6 AM
  workflow_dispatch:

jobs:
  accuracy_test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
      - name: Update prediction tracking
        run: |
          python scripts/update_prediction_tracking.py
      - name: Run accuracy test
        run: |
          python scripts/test_prediction_accuracy.py --json --output accuracy_report.json
      - name: Upload results
        uses: actions/upload-artifact@v2
        with:
          name: accuracy-report
          path: accuracy_report.json
```

## Troubleshooting

### "No predictions found matching criteria"

**Cause**: No resolved predictions in database.

**Solution**:
1. Run `update_prediction_tracking.py` first to fetch actual results
2. Verify games have completed and boxscores are available
3. Check `prediction_tracking` table has `actual_resolved_at` values

### Low accuracy in high confidence buckets

**Cause**: Model overconfidence, miscalibrated confidence scores.

**Solutions**:
1. Review confidence calculation in prediction service
2. Apply Platt scaling or isotonic regression for calibration
3. Reduce confidence scores by 5-10% across the board
4. Add more features to improve confidence discrimination

### High Mean Absolute Error (> 10)

**Cause**: Predictions far from actual values.

**Solutions**:
1. Check if model is using outdated player stats
2. Verify feature engineering (recent form, matchups, etc.)
3. Consider ensemble models for better predictions
4. Review data quality for training set

### Negative Average Edge

**Cause**: Bookmaker lines consistently higher than predictions.

**Solutions**:
1. Verify data quality (are predictions stored correctly?)
2. Check if bookmaker line data is stale
3. May indicate model is conservative (underestimates)
4. Consider if this creates value (contrarian approach)

## Best Practices

1. **Run Daily**: Accuracy metrics should be tracked daily for early problem detection
2. **Save Reports**: Archive reports for historical comparison
3. **Investigate Outliers**: Look at extreme predictions manually
4. **Calibrate Regularly**: If calibration error > 10%, recalibrate confidence
5. **Segment Analysis**: Don't just look at overall accuracy - drill down by stat, player, confidence
6. **Set Benchmarks**: Establish minimum accuracy targets (e.g., 65% overall, 75% for 80%+ confidence)
7. **A/B Test**: Try model changes and compare accuracy before/after

## Example Report Interpretation

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

**Analysis**:
- 68% accuracy is reasonable (breakeven is ~52.4% at -110 odds)
- +0.3 bias = slight overestimation, but well-calibrated
- +3.2% edge = model finding value vs bookmakers
- 8.5% calibration error = acceptable, could be better
- 76.5% avg confidence vs 68% actual = slight overconfidence

**Action Items**:
1. Reduce all confidence scores by 5% to improve calibration
2. Investigate why OVER vs UNDER rates differ (if they do)
3. Check if edge calculation correlates with actual win rate
4. Review stat types with lowest accuracy

## Related Scripts

- `update_prediction_tracking.py`: Fetch actual results and populate `actual_value`
- `generate_predictions.py`: Create predictions for upcoming games
- `analyze_model_performance.py`: (custom) Deep dive into specific issues

## Support

For questions or issues:
1. Check database has recent predictions: `SELECT COUNT(*) FROM prediction_tracking WHERE actual_resolved_at IS NOT NULL`
2. Verify data freshness: `SELECT MAX(actual_resolved_at) FROM prediction_tracking`
3. Review logs for errors during prediction tracking updates
4. Check if NBA API is returning boxscore data correctly

## Version History

- v1.0 (2026-01-30): Initial release with comprehensive accuracy metrics
