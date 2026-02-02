#!/usr/bin/env python3
"""
Show sample predictions demonstrating all tier improvements.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import get_db
from app.services.nba.enhanced_prediction_service import EnhancedPredictionService
from app.models import Game, PlayerSeasonStats
from sqlalchemy import desc

db = next(get_db())

# Get most recent game
game = db.query(Game).filter(
    Game.sport_id == 'nba'
).order_by(desc(Game.game_date)).first()

print('=' * 80)
print('SAMPLE PREDICTIONS - DEMONSTRATING TIER IMPROVEMENTS')
print('=' * 80)
print(f'Game: {game.away_team} @ {game.home_team}')
print(f'Date: {game.game_date}')
print('=' * 80)
print()

service = EnhancedPredictionService(db)
players = service._get_active_players(game)

print(f'Generating predictions for {len(players)} active players...')
print()

# Generate predictions for first 5 players
for i, player in enumerate(players[:5], 1):
    pred = service._generate_single_prediction(player, game, 'points', 'draftkings')

    if pred:
        factors = pred.get('factors', {})

        print(f'{i}. {pred["player"]} ({player.team})')
        print(f'   Position: {player.position}')
        print(f'   Prediction: {pred["projected"]:.1f} pts')
        print(f'   Bookmaker Line: {pred["line"]:.1f}')
        print(f'   Edge: {pred["edge"]:+.1f}')
        print(f'   Recommendation: {pred["recommendation"]}')
        print(f'   Confidence: {pred["confidence"]:.2%}')
        print()
        print('   FACTORS:')

        # Base projection
        print(f'   • Base per-36: {factors.get("base_per_36", 0):.1f}')
        print(f'   • Projected minutes: {factors.get("projected_minutes", 0):.1f}')

        # Tier 2: Fatigue factor
        fatigue = factors.get('fatigue_factor', 1.0)
        if fatigue != 1.0:
            print(f'   • Fatigue factor (T2): {fatigue:.3f} ({(fatigue-1)*100:+.1f}%)')
        else:
            print(f'   • Fatigue factor (T2): {fatigue:.3f} (no penalty)')

        # Tier 3: Usage boost
        usage = factors.get('teammate_injuries', 0)
        if usage != 0:
            print(f'   • Usage boost (T3): {usage:.3f} ({usage*100:+.1f}%)')
        else:
            print(f'   • Usage boost (T3): {usage:.3f} (no injured teammates)')

        # Tier 3: Opponent defense
        opp = factors.get('opponent_defense', 0)
        print(f'   • Opponent defense (T3): {opp:+.3f} ({opp*100:+.1f}%)')

        # Tier 4: Travel fatigue
        travel = factors.get('travel_fatigue', 0)
        if travel != 0:
            print(f'   • Travel fatigue (T4): {travel:+.3f} ({travel*100:+.1f}%)')
        else:
            print(f'   • Travel fatigue (T4): {travel:.3f} (no penalty)')

        # Tier 4: Matchup score
        matchup = factors.get('matchup_score', 1.0)
        print(f'   • Matchup score (T4): {matchup:.3f} ({(matchup-1)*100:+.1f}%)')

        # Sample size
        sample = factors.get('sample_size', 0)
        std_dev = factors.get('std_dev')
        if std_dev:
            print(f'   • Sample size: {sample} games (std dev: {std_dev:.2f})')
        else:
            print(f'   • Sample size: {sample} games')

        print()
        print('-' * 80)
        print()

print('=' * 80)
print('TIER IMPROVEMENTS LEGEND')
print('=' * 80)
print('T1 (Tier 1): Rest days from actual data, recent activity filtering')
print('T2 (Tier 2): Age-adjusted fatigue, non-linear minutes scaling')
print('T3 (Tier 3): Usage boost from injuries, dynamic opponent adjustments')
print('T4 (Tier 4): Travel fatigue, matchup scoring')
print('=' * 80)

db.close()
