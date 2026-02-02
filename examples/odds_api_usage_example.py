#!/usr/bin/env python3
"""
Example: Using the Enhanced Prediction Service with Real-Time Odds API

This example demonstrates how to:
1. Initialize the service with Odds API
2. Generate predictions with live bookmaker lines
3. Handle fallback when API is unavailable
4. Monitor API quota usage

Author: Enhanced Prediction Service v2.0
Date: 2025-01-30
"""
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.models import Game
from app.services.nba.enhanced_prediction_service import EnhancedPredictionService
from app.services.core.odds_api_service import OddsApiService


def example_with_real_odds():
    """Example: Generate predictions using real-time Odds API."""
    print("=" * 80)
    print("Example 1: Predictions with Real-Time Odds API")
    print("=" * 80)
    print()

    # Setup database
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Check for API key
        if not settings.odds_api_key:
            print("❌ ODDS_API_KEY not found in environment")
            print("   Skipping real odds example")
            return

        # Initialize Odds API service
        odds_service = OddsApiService(api_key=settings.odds_api_key)
        print("✅ Odds API service initialized")
        print()

        # Get today's game
        from datetime import date, timedelta

        game = db.query(Game).filter(
            Game.game_date >= date.today(),
            Game.game_date <= date.today() + timedelta(days=1),
            Game.sport_id == "nba"
        ).first()

        if not game:
            print("❌ No games found for today")
            return

        print(f"Game: {game.away_team} @ {game.home_team}")
        print(f"Date: {game.game_date}")
        print()

        # Initialize prediction service WITH Odds API
        prediction_service = EnhancedPredictionService(
            db=db,
            odds_api_service=odds_service  # This enables real odds fetching
        )

        # Generate predictions
        predictions = prediction_service.generate_prop_predictions(
            game_id=game.id,
            stat_types=["points", "rebounds", "assists", "threes"],
            bookmaker="draftkings"
        )

        print(f"Generated {len(predictions)} predictions")
        print()

        # Display sample predictions
        print("Sample Predictions (Top 5 by Edge):")
        print("-" * 80)

        # Sort by edge (absolute value)
        sorted_predictions = sorted(
            predictions,
            key=lambda p: abs(p['edge']),
            reverse=True
        )[:5]

        for i, pred in enumerate(sorted_predictions, 1):
            print(f"\n{i}. {pred['player']} ({pred['team']}) - {pred['stat_type'].upper()}")
            print(f"   Projected: {pred['projected']} vs Line: {pred['line']} ({pred['bookmaker']})")
            print(f"   Edge: {pred['edge']:+.1f}")
            print(f"   Recommendation: {pred['recommendation']}")
            print(f"   Confidence: {pred['confidence']:.0%}")
            print(f"   Source: {pred['line_source']}")

            if pred.get('odds_fetched_at'):
                print(f"   Odds Fetched: {pred['odds_fetched_at']}")

        print("\n" + "-" * 80)

        # Check API quota
        quota = odds_service.get_quota_status()
        print("\nAPI Quota Status:")
        print(f"  Requests Remaining: {quota['requests_remaining']}")
        print(f"  Requests Used: {quota['requests_used']}")
        print(f"  Quota Used: {quota['quota_percentage']:.1f}%")

        # Cleanup
        import asyncio
        asyncio.run(odds_service.close())

    finally:
        db.close()


def example_with_estimation():
    """Example: Generate predictions using estimated lines (no API)."""
    print("\n")
    print("=" * 80)
    print("Example 2: Predictions with Estimated Lines (No API)")
    print("=" * 80)
    print()

    # Setup database
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Get today's game
        from datetime import date, timedelta

        game = db.query(Game).filter(
            Game.game_date >= date.today(),
            Game.game_date <= date.today() + timedelta(days=1),
            Game.sport_id == "nba"
        ).first()

        if not game:
            print("❌ No games found for today")
            return

        print(f"Game: {game.away_team} @ {game.home_team}")
        print(f"Date: {game.game_date}")
        print()

        # Initialize prediction service WITHOUT Odds API
        prediction_service = EnhancedPredictionService(
            db=db,
            odds_api_service=None  # No API - will use estimation
        )

        print("✅ Prediction service initialized (estimation mode)")
        print()

        # Generate predictions
        predictions = prediction_service.generate_prop_predictions(
            game_id=game.id,
            stat_types=["points", "rebounds"],
            bookmaker="draftkings"
        )

        print(f"Generated {len(predictions)} predictions")
        print()

        # Display sample predictions
        print("Sample Predictions (Top 3 by Edge):")
        print("-" * 80)

        sorted_predictions = sorted(
            predictions,
            key=lambda p: abs(p['edge']),
            reverse=True
        )[:3]

        for i, pred in enumerate(sorted_predictions, 1):
            print(f"\n{i}. {pred['player']} ({pred['team']}) - {pred['stat_type'].upper()}")
            print(f"   Projected: {pred['projected']} vs Line: {pred['line']}")
            print(f"   Edge: {pred['edge']:+.1f}")
            print(f"   Recommendation: {pred['recommendation']}")
            print(f"   Confidence: {pred['confidence']:.0%}")
            print(f"   Source: {pred['line_source']} (estimated from season stats)")

    finally:
        db.close()


def example_selective_bookmaker():
    """Example: Generate predictions for specific bookmaker."""
    print("\n")
    print("=" * 80)
    print("Example 3: Selecting Specific Bookmaker")
    print("=" * 80)
    print()

    print("Available bookmakers:")
    print("  - draftkings (primary)")
    print("  - fanduel")
    print("  - betmgm")
    print("  - caesars")
    print("  - pointsbetus")
    print()

    # Show how to specify bookmaker
    print("Code Example:")
    print("-" * 80)
    print("""
# Initialize with Odds API
odds_service = OddsApiService(api_key=settings.odds_api_key)
prediction_service = EnhancedPredictionService(
    db=db,
    odds_api_service=odds_service
)

# Generate predictions for specific bookmaker
predictions = prediction_service.generate_prop_predictions(
    game_id=game_id,
    stat_types=["points", "rebounds", "assists", "threes"],
    bookmaker="fanduel"  # Specify your preferred bookmaker
)

# Each prediction will use lines from that bookmaker
for pred in predictions:
    print(f"{pred['player']}: {pred['line']} ({pred['bookmaker']})")
    """)
    print("-" * 80)


def example_monitoring():
    """Example: Monitor prediction quality and API usage."""
    print("\n")
    print("=" * 80)
    print("Example 4: Monitoring & Quality Control")
    print("=" * 80)
    print()

    print("Key Metrics to Track:")
    print()
    print("1. API Quota Usage:")
    print("   - Check quota_status['requests_remaining']")
    print("   - Alert when < 20% remaining")
    print()
    print("2. Real vs Estimated Lines:")
    print("   - Count predictions with line_source != 'estimated'")
    print("   - Target: >80% real lines")
    print()
    print("3. Odds Freshness:")
    print("   - Check odds_fetched_at timestamp")
    print("   - Alert if >10 minutes old")
    print()
    print("4. Cache Efficiency:")
    print("   - Check cache size: len(prediction_service._odds_cache)")
    print("   - Target: >90% cache hit rate")
    print()
    print("5. Prediction Distribution:")
    print("   - OVER/UNDER/PASS ratio")
    print("   - Confidence distribution")
    print()
    print("Code Example:")
    print("-" * 80)
    print("""
# After generating predictions
predictions = service.generate_prop_predictions(...)

# Analyze results
from collections import Counter

recommendations = Counter(p['recommendation'] for p in predictions)
sources = Counter(p['line_source'] for p in predictions)

print("Recommendations:", dict(recommendations))
# Output: {'OVER': 15, 'UNDER': 8, 'PASS': 22}

print("Line Sources:", dict(sources))
# Output: {'draftkings': 40, 'estimated': 5}

# Check confidence
avg_confidence = sum(p['confidence'] for p in predictions) / len(predictions)
print(f"Average Confidence: {avg_confidence:.0%}")
    """)
    print("-" * 80)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Enhanced Prediction Service Usage Examples"
    )
    parser.add_argument(
        '--example',
        type=int,
        choices=[1, 2, 3, 4],
        help='Which example to run (1-4)'
    )

    args = parser.parse_args()

    if args.example == 1:
        example_with_real_odds()
    elif args.example == 2:
        example_with_estimation()
    elif args.example == 3:
        example_selective_bookmaker()
    elif args.example == 4:
        example_monitoring()
    else:
        # Run all examples
        print("\n" + "=" * 80)
        print("Enhanced Prediction Service - Usage Examples")
        print("=" * 80)

        # Check if API key is available
        if settings.odds_api_key:
            example_with_real_odds()
        else:
            print("⚠️  Skipping Example 1 (ODDS_API_KEY not set)")
            print("   Set ODDS_API_KEY in .env to run real odds example\n")

        example_with_estimation()
        example_selective_bookmaker()
        example_monitoring()

        print("\n" + "=" * 80)
        print("Examples Complete")
        print("=" * 80)
        print("\nTo run individual examples:")
        print("  python examples/odds_api_usage_example.py --example 1")
        print("  python examples/odds_api_usage_example.py --example 2")
        print("  etc.")
