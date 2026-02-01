# Accuracy Testing Quick Reference

## Common Commands

```bash
# Full report
python scripts/test_prediction_accuracy.py

# Points only
python scripts/test_prediction_accuracy.py --stat-type points

# High confidence only (80%+)
python scripts/test_prediction_accuracy.py --min-confidence 0.80

# Last 7 days
python scripts/test_prediction_accuracy.py --days-back 7

# Save to file
python scripts/test_prediction_accuracy.py --output reports/accuracy.txt

# Export JSON
python scripts/test_prediction_accuracy.py --json > reports/accuracy.json
```

## Key Metrics

| Metric | Good | Concern | Action |
|--------|------|---------|--------|
| Accuracy Rate | > 65% | < 55% | Model retraining needed |
| MAE | < 5 | > 10 | Feature engineering |
| Mean Signed Error | ±0.5 | > ±2 | Bias correction |
| Calibration Error | < 10% | > 15% | Recalibrate confidence |
| 90%+ Bucket | > 85% | < 80% | Reduce confidence scores |

## Workflow

```bash
# 1. Update with actual results (MUST RUN FIRST)
python scripts/update_prediction_tracking.py

# 2. Test accuracy
python scripts/test_prediction_accuracy.py

# 3. Review report
cat accuracy_report.txt
```

## Report Sections

1. **Overall** - Big picture performance
2. **Confidence Buckets** - Calibration check
3. **Stat Types** - Which stats work best
4. **OVER/UNDER** - Recommendation bias
5. **Edge Magnitude** - Value detection
6. **Best Players** - Model strengths
7. **Worst Players** - Model weaknesses
8. **Extremes** - Outlier investigation

## Troubleshooting

**No predictions found?**
→ Run `update_prediction_tracking.py` first

**Low accuracy in high confidence?**
→ Model is overconfident, reduce scores by 5-10%

**High MAE (> 10)?**
→ Check feature quality and data freshness

**Negative edge?**
→ Bookmaker lines higher than predictions (conservative model)

## Quick Tips

- Run daily to catch issues early
- Save reports for historical tracking
- Focus on calibration error (< 10% target)
- Investigate worst-performing players manually
- Compare stat types to find model blind spots
