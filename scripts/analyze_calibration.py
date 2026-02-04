#!/usr/bin/env python3
"""
Analyze prediction accuracy and recommend calibration multiplier adjustments.
"""
import os
import sys
import numpy as np
from datetime import datetime, timedelta
from sqlalchemy import desc

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import get_db
from app.models import Prediction, Game, PlayerStats, PlayerSeasonStats

PLAYER_TIERS = {
    'elite': {'min_pts_per_36': 25.0, 'calibration_multiplier': 1.0},
    'above_avg': {'min_pts_per_36': 18.0, 'calibration_multiplier': 0.98},
    'average': {'min_pts_per_36': 12.0, 'calibration_multiplier': 0.95},
    'role_player': {'min_pts_per_36': 0.0, 'calibration_multiplier': 0.90}
}


def get_player_tier(db, player_id):
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


def analyze_calibration(db):
    cutoff = datetime.now() - timedelta(days=60)
    
    predictions = (
        db.query(Prediction)
        .join(Game, Prediction.game_id == Game.id)
        .filter(
            Game.game_date < cutoff,
            Game.status.in_(['final', 'completed', 'finished'])
        )
        .order_by(desc(Game.game_date))
        .limit(100)
        .all()
    )
    
    print(f"Found {len(predictions)} historical predictions")
    
    data_by_tier = {tier: [] for tier in PLAYER_TIERS}
    
    for pred in predictions:
        actual_stats = db.query(PlayerStats).filter(
            PlayerStats.player_id == pred.player_id,
            PlayerStats.game_id == pred.game_id
        ).first()
        
        if not actual_stats:
            continue
        
        actual_value = getattr(actual_stats, pred.stat_type, None)
        if actual_value is None:
            continue
        
        tier = get_player_tier(db, pred.player_id)
        error = pred.predicted_value - actual_value
        
        data_by_tier[tier].append({
            'error': error,
            'abs_error': abs(error)
        })
    
    print("\n" + "="*60)
    print("CALIBRATION ANALYSIS BY TIER")
    print("="*60)
    
    recommended = {}
    
    for tier, data in data_by_tier.items():
        if not data:
            continue
        
        errors = [d['error'] for d in data]
        abs_errors = [d['abs_error'] for d in data]
        
        mean_error = np.mean(errors)
        mae = np.mean(abs_errors)
        
        current_mult = PLAYER_TIERS[tier]['calibration_multiplier']
        
        # Calculate adjustment
        if mae > 0:
            adjustment = 1.0 - (mean_error / (mean_error + mae))
            adjustment = max(0.90, min(1.10, adjustment))
            suggested_mult = round(current_mult * adjustment, 3)
        else:
            suggested_mult = current_mult
        
        recommended[tier] = suggested_mult
        
        print(f"\n{tier.upper()}:")
        print(f"  Samples: {len(data)}")
        print(f"  Mean Error: {mean_error:.2f} ({'over' if mean_error > 0 else 'under'}predicting)")
        print(f"  MAE: {mae:.2f}")
        print(f"  Current Multiplier: {current_mult}")
        print(f"  Suggested Multiplier: {suggested_mult} ({'adjust' if suggested_mult != current_mult else 'no change'})")
    
    print("\n" + "="*60)
    print("RECOMMENDED MULTIPLIERS:")
    print("="*60)
    
    for tier, mult in recommended.items():
        print(f"    '{tier}': {{'calibration_multiplier': {mult}}},")

if __name__ == '__main__':
    db = next(get_db())
    analyze_calibration(db)
