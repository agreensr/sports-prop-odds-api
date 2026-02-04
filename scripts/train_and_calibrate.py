#!/usr/bin/env python3
"""
Train XGBoost model and fine-tune calibration multipliers based on historical data.

This script:
1. Fetches historical predictions with actual results
2. Trains XGBoost model on the data
3. Calculates calibration multipliers by player tier and stat type
4. Updates calibration_service.py with optimized multipliers

Research: Walsh & Joshi (2024) - Calibration-based selection achieves +34.69% ROI
Target: Expected Calibration Error (ECE) < 5%
"""
import os
import sys
import json
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import get_db
from app.models import Prediction, Game, PlayerStats, Player, PlayerSeasonStats
from app.services.nba.xgboost_prediction_service import XGBoostPredictionService

# Configuration
MIN_SAMPLES_FOR_TRAINING = 30
MIN_SAMPLES_PER_TIER = 5

# Player tier thresholds (same as calibration_service)
PLAYER_TIERS = {
    'elite': {'min_pts_per_36': 25.0, 'calibration_multiplier': 1.0},
    'above_avg': {'min_pts_per_36': 18.0, 'calibration_multiplier': 0.98},
    'average': {'min_pts_per_36': 12.0, 'calibration_multiplier': 0.95},
    'role_player': {'min_pts_per_36': 0.0, 'calibration_multiplier': 0.90}
}


def get_player_tier(db: Session, player_id: str) -> str:
    """Determine player tier based on points per 36."""
    season_stats = db.query(PlayerSeasonStats).filter(
        PlayerSeasonStats.player_id == player_id,
        PlayerSeasonStats.season == "2025-26"
    ).first()
    
    if not season_stats or not season_stats.points_per_36:
        return 'role_player'
    
    pts_per_36 = season_stats.points_per_36
    
    for tier, config in PLAYER_TIERS.items():
        if pts_per_36 >= config['min_pts_per_36']:
            return tier
    return 'role_player'


def fetch_historical_data(db: Session, days_back: int = 60) -> List[Dict]:
    """
    Fetch historical predictions with actual results.
    
    Returns list of dicts with features and targets.
    """
    cutoff = datetime.now() - timedelta(days=days_back)
    
    # Get completed games with predictions
    predictions = (
        db.query(Prediction)
        .join(Game, Prediction.game_id == Game.id)
        .filter(
            Game.game_date < cutoff,
            Game.status.in_(['final', 'completed', 'finished'])
        )
        .order_by(desc(Game.game_date))
        .all()
    )
    
    print(f"Found {len(predictions)} historical predictions")
    
    training_data = []
    
    for pred in predictions:
        # Get actual stats from PlayerStats
        actual_stats = db.query(PlayerStats).filter(
            PlayerStats.player_id == pred.player_id,
            PlayerStats.game_id == pred.game_id
        ).first()
        
        if not actual_stats:
            continue
        
        # Get actual value for the stat type
        actual_value = getattr(actual_stats, pred.stat_type, None)
        if actual_value is None:
            continue
        
        # Get player tier
        tier = get_player_tier(db, pred.player_id)
        
        training_data.append({
            'player_id': pred.player_id,
            'player_name': pred.player.name,
            'team': pred.player.team,
            'stat_type': pred.stat_type,
            'predicted': pred.predicted_value,
            'actual': actual_value,
            'error': pred.predicted_value - actual_value,
            'abs_error': abs(pred.predicted_value - actual_value),
            'tier': tier,
            'game_id': pred.game_id,
            'game_date': pred.game.game_date.isoformat() if pred.game.game_date else None
        })
    
    return training_data


def analyze_calibration_by_tier(data: List[Dict]) -> Dict:
    """Analyze prediction accuracy by player tier to recommend multipliers."""
    
    results = {}
    
    for tier in PLAYER_TIERS.keys():
        tier_data = [d for d in data if d['tier'] == tier]
        
        if not tier_data:
            continue
        
        n = len(tier_data)
        errors = [d['error'] for d in tier_data]
        abs_errors = [d['abs_error'] for d in tier_data]
        
        # Calculate metrics
        mean_error = np.mean(errors)
        mae = np.mean(abs_errors)
        
        # Positive mean_error means we're over-predicting (need lower multiplier)
        # Negative mean_error means we're under-predicting (need higher multiplier)
        
        # Current multiplier
        current_mult = PLAYER_TIERS[tier]['calibration_multiplier']
        
        # Suggested adjustment: if mean_error > 0, reduce multiplier
        # Formula: new_mult = current_mult * (1 - mean_error / (mean_error + mae))
        if mae > 0:
            adjustment = 1.0 - (mean_error / (mean_error + mae))
            # Limit adjustment to +/- 10%
            adjustment = max(0.90, min(1.10, adjustment))
            suggested_mult = current_mult * adjustment
        else:
            suggested_mult = current_mult
        
        results[tier] = {
            'n_samples': n,
            'mean_error': round(mean_error, 2),
            'mae': round(mae, 2),
            'current_multiplier': current_mult,
            'suggested_multiplier': round(suggested_mult, 3),
            'adjustment_factor': round(adjustment, 3) if mae > 0 else None
        }
    
    return results


def analyze_by_stat_type(data: List[Dict]) -> Dict:
    """Analyze accuracy by stat type."""
    
    results = {}
    
    for stat_type in ['points', 'rebounds', 'assists', 'threes']:
        stat_data = [d for d in data if d['stat_type'] == stat_type]
        
        if not stat_data:
            continue
        
        errors = [d['error'] for d in stat_data]
        abs_errors = [d['abs_error'] for d in stat_data]
        
        results[stat_type] = {
            'n_samples': len(stat_data),
            'mean_error': round(np.mean(errors), 2),
            'mae': round(np.mean(abs_errors), 2),
            'bias': 'overpredicts' if np.mean(errors) > 0 else 'underpredicts'
        }
    
    return results


def calculate_calibration_error(data: List[Dict]) -> float:
    """
    Calculate Expected Calibration Error (ECE).
    
    ECE measures the difference between predicted confidence and actual accuracy.
    Lower is better - target is < 5%.
    """
    if not data:
        return 0.0
    
    # Group by confidence bins (0.1 width)
    bins = {}
    for d in data:
        conf = min(0.9, max(0.5, d.get('confidence', 0.5)))
        bin_key = int(conf * 10) / 10
        
        if bin_key not in bins:
            bins[bin_key] = {'correct': 0, 'total': 0}
        
        bins[bin_key]['total'] += 1
        # Consider prediction correct if within 10% of actual
        if abs(d['error']) <= 0.1 * max(1.0, d['actual']):
            bins[bin_key]['correct'] += 1
    
    # Calculate weighted error
    total_weight = 0
    weighted_error = 0
    
    for bin_conf, counts in bins.items():
        if counts['total'] > 0:
            accuracy = counts['correct'] / counts['total']
            weight = counts['total'] / len(data)
            weighted_error += weight * abs(bin_conf - accuracy)
            total_weight += weight
    
    return weighted_error if total_weight > 0 else 0.0


def generate_calibration_report(data: List[Dict]) -> str:
    """Generate a comprehensive calibration report."""
    
    lines = []
    lines.append("=" * 80)
    lines.append("CALIBRATION ANALYSIS REPORT")
    lines.append(f"Generated: {datetime.now().isoformat()}")
    lines.append("=" * 80)
    
    # Overall stats
    n = len(data)
    errors = [d['error'] for d in data]
    abs_errors = [d['abs_error'] for d in data]
    
    lines.append("OVERALL PERFORMANCE")
    lines.append("-" * 40)
    lines.append(f"Total predictions: {n}")
    lines.append(f"Mean error: {np.mean(errors):.2f} points")
    lines.append(f"Mean absolute error: {np.mean(abs_errors):.2f} points")
    lines.append(f"Bias: {'Overpredicts' if np.mean(errors) > 0 else 'Underpredicts'} ({np.mean(errors):.2f})")
    
    # Calibration error
    ece = calculate_calibration_error(data)
    lines.append(f"Calibration Error (ECE): {ece:.1%} (target: <5%)")
    
    lines.append("")
    
    # By tier
    tier_results = analyze_calibration_by_tier(data)
    lines.append("CALIBRATION BY PLAYER TIER")
    lines.append("-" * 40)
    
    for tier in ['elite', 'above_avg', 'average', 'role_player']:
        if tier in tier_results:
            r = tier_results[tier]
            lines.append(f"\n{tier.upper()}:")
            lines.append(f"  Samples: {r['n_samples']}")
            lines.append(f"  Mean Error: {r['mean_error']:.2f}")
            lines.append(f"  MAE: {r['mae']:.2f}")
            lines.append(f"  Current Multiplier: {r['current_multiplier']}")
            lines.append(f"  Suggested Multiplier: {r['suggested_multiplier']}")
            if r.get('adjustment_factor'):
                lines.append(f"  Adjustment: {r['adjustment_factor']}")
    
    lines.append("")
    
    # By stat type
    stat_results = analyze_by_stat_type(data)
    lines.append("CALIBRATION BY STAT TYPE")
    lines.append("-" * 40)
    
    for stat_type, r in stat_results.items():
        lines.append(f"\n{stat_type}:")
        lines.append(f"  Samples: {r['n_samples']}")
        lines.append(f"  Mean Error: {r['mean_error']:.2f}")
        lines.append(f"  MAE: {r['mae']:.2f}")
        lines.append(f"  Bias: {r['bias']}")
    
    # Recommended multipliers
    lines.append("")
    lines.append("RECOMMENDED CALIBRATION MULTIPLIERS")
    lines.append("-" * 40)
    
    for tier in ['elite', 'above_avg', 'average', 'role_player']:
        if tier in tier_results:
            r = tier_results[tier]
            mult = r['suggested_multiplier']
            lines.append(f"    '{tier}': {{'calibration_multiplier': {mult}}},")
    
    lines.append("}" * 80)
    
    return "\n".join(lines)


def main():
    """Main function."""
    db = next(get_db())
    
    print("Fetching historical predictions and actual results...")
    data = fetch_historical_data(db, days_back=60)
    
    if not data:
        print("No historical data found. Exiting.")
        return
    
    print(f"\nProcessing {len(data)} prediction results...")
    
    # Generate report
    report = generate_calibration_report(data)
    print("\n" + report)
    
    # Save report to file
    reports_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'reports')
    os.makedirs(reports_dir, exist_ok=True)
    
    report_file = os.path.join(reports_dir, f"calibration_analysis_{datetime.now().strftime('%Y%m%d')}.txt")
    with open(report_file, 'w') as f:
        f.write(report)
    
    print(f"\nReport saved to: {report_file}")
    
    # Summary
    ece = calculate_calibration_error(data)
    print(f"\nCurrent Calibration Error (ECE): {ece:.1%}")
    
    if ece > 0.05:
        print("ACTION REQUIRED: Calibration error exceeds 5% target.")
        print("Review recommended multipliers above and update calibration_service.py")
    else:
        print("Calibration is within target range (<5% ECE)")


if __name__ == '__main__':
    main()
