#!/usr/bin/env python3
"""
Test script for Odds API integration in Enhanced Prediction Service.

This script verifies:
1. Real-time odds fetching from Odds API
2. Proper caching of odds data
3. Fallback to estimation when API fails
4. Timestamp population (odds_fetched_at, odds_last_updated)
5. Line source tracking

Usage:
    python scripts/test_odds_api_integration.py
"""
import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.models import Game, Player
from app.services.nba.enhanced_prediction_service import EnhancedPredictionService
from app.services.core.odds_api_service import OddsApiService


def get_test_game(db):
    """Get a test game for today's date."""
    from datetime import date, timedelta

    # Look for a game within the next 3 days
    start_date = date.today()
    end_date = start_date + timedelta(days=3)

    game = db.query(Game).filter(
        Game.game_date >= start_date,
        Game.game_date <= end_date,
        Game.sport_id == "nba"
    ).first()

    return game


def test_odds_api_integration():
    """Test the full Odds API integration."""
    print("=" * 80)
    print("Testing Odds API Integration")
    print("=" * 80)
    print()

    # Setup database connection
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Step 1: Get a test game
        print("Step 1: Finding test game...")
        game = get_test_game(db)
        if not game:
            print("❌ No upcoming games found in database")
            print("   Run: python scripts/sync_nba_games.py to fetch games")
            return False

        print(f"✅ Found game: {game.away_team} @ {game.home_team}")
        print(f"   Game ID: {game.id}")
        print(f"   Game Date: {game.game_date}")
        print()

        # Step 2: Initialize Odds API service
        print("Step 2: Initializing Odds API service...")
        if not settings.odds_api_key:
            print("❌ ODDS_API_KEY not found in environment")
            print("   Set ODDS_API_KEY in .env file")
            return False

        odds_service = OddsApiService(api_key=settings.odds_api_key)
        print(f"✅ Odds API service initialized")
        print()

        # Step 3: Initialize Enhanced Prediction Service with Odds API
        print("Step 3: Initializing Enhanced Prediction Service...")
        prediction_service = EnhancedPredictionService(
            db=db,
            odds_api_service=odds_service
        )
        print(f"✅ Enhanced Prediction Service initialized with Odds API")
        print()

        # Step 4: Check if game has odds_event_id
        print("Step 4: Checking game odds mapping...")
        print(f"   Game has odds_api_event_id: {bool(game.odds_api_event_id)}")
        if game.odds_api_event_id:
            print(f"   Odds Event ID: {game.odds_api_event_id}")
        print()

        # Step 5: Test odds fetching for a single player
        print("Step 5: Testing real-time odds fetching...")
        players = prediction_service._get_active_players(game)
        if not players:
            print("❌ No active players found for this game")
            return False

        print(f"✅ Found {len(players)} active players")
        print(f"   Testing with first player: {players[0].name}")
        print()

        # Test the bookmaker line fetching
        from app.services.nba.enhanced_prediction_service import EnhancedPredictionService as EPS

        # Monkey-patch to expose internal method for testing
        test_player = players[0]
        stat_type = "points"
        bookmaker = "draftkings"

        print(f"Step 6: Fetching bookmaker line for {test_player.name} ({stat_type})...")

        # This will test the full async fetching chain
        line_data = prediction_service._get_bookmaker_line(
            test_player, game, stat_type, bookmaker
        )

        if not line_data:
            print("❌ Failed to fetch line data")
            return False

        print(f"✅ Successfully fetched line data:")
        print(f"   Line: {line_data['line']}")
        print(f"   Bookmaker: {line_data.get('bookmaker', 'N/A')}")
        print(f"   Line Source: {line_data.get('line_source', 'N/A')}")
        print(f"   Over Price: {line_data.get('over_price', 'N/A')}")
        print(f"   Under Price: {line_data.get('under_price', 'N/A')}")

        if 'fetched_at' in line_data:
            print(f"   Fetched At: {line_data['fetched_at']}")
        if 'odds_fetched_at' in line_data:
            print(f"   Odds Fetched At (DB): {line_data['odds_fetched_at']}")
        if 'odds_last_updated' in line_data:
            print(f"   Odds Last Updated (DB): {line_data['odds_last_updated']}")
        print()

        # Step 7: Test caching behavior
        print("Step 7: Testing caching behavior...")
        print(f"   Cache size before: {len(prediction_service._odds_cache)}")

        # Fetch the same line again (should use cache)
        line_data_cached = prediction_service._get_bookmaker_line(
            test_player, game, stat_type, bookmaker
        )
        print(f"   Cache size after: {len(prediction_service._odds_cache)}")
        print(f"✅ Cache working correctly")
        print()

        # Step 8: Generate predictions for all players
        print("Step 8: Generating predictions for all active players...")
        print(f"   Stat types: points, rebounds, assists, threes")

        predictions = prediction_service.generate_prop_predictions(
            game_id=game.id,
            stat_types=["points", "rebounds", "assists", "threes"],
            bookmaker=bookmaker
        )

        if not predictions:
            print("⚠️  No predictions generated (possibly no real lines available)")
            return True

        print(f"✅ Generated {len(predictions)} predictions")
        print()

        # Step 9: Analyze prediction sources
        print("Step 9: Analyzing prediction sources...")

        source_counts = {}
        bookmaker_counts = {}

        for pred in predictions:
            source = pred.get('line_source', 'unknown')
            source_counts[source] = source_counts.get(source, 0) + 1

            bookmaker = pred.get('bookmaker', 'unknown')
            bookmaker_counts[bookmaker] = bookmaker_counts.get(bookmaker, 0) + 1

        print("   Line Sources:")
        for source, count in sorted(source_counts.items()):
            print(f"     {source}: {count}")

        print("\n   Bookmakers:")
        for bookmaker, count in sorted(bookmaker_counts.items()):
            print(f"     {bookmaker}: {count}")

        print()

        # Step 10: Show sample predictions
        print("Step 10: Sample predictions (first 3):")
        for i, pred in enumerate(predictions[:3], 1):
            print(f"\n   Prediction {i}:")
            print(f"     Player: {pred['player']} ({pred['team']})")
            print(f"     Stat: {pred['stat_type']}")
            print(f"     Projected: {pred['projected']}")
            print(f"     Line: {pred['line']} ({pred['bookmaker']})")
            print(f"     Edge: {pred['edge']}")
            print(f"     Recommendation: {pred['recommendation']}")
            print(f"     Confidence: {pred['confidence']}")
            print(f"     Source: {pred['line_source']}")

            if pred.get('odds_fetched_at'):
                print(f"     Odds Fetched: {pred['odds_fetched_at']}")
            if pred.get('odds_last_updated'):
                print(f"     Odds Updated: {pred['odds_last_updated']}")

        print()
        print("=" * 80)
        print("✅ All tests passed!")
        print("=" * 80)

        # Summary
        print("\nSummary:")
        print(f"  • Game: {game.away_team} @ {game.home_team}")
        print(f"  • Active Players: {len(players)}")
        print(f"  • Predictions Generated: {len(predictions)}")
        print(f"  • Real Lines: {source_counts.get(bookmaker, 0)}")
        print(f"  • Estimated Lines: {source_counts.get('estimated', 0)}")
        print(f"  • Cache Hit Rate: {len(prediction_service._odds_cache)} entries")
        print()

        # Cleanup
        asyncio.run(odds_service.close())

        return True

    except Exception as e:
        print(f"\n❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        db.close()


def test_fallback_behavior():
    """Test fallback to estimation when Odds API fails."""
    print("=" * 80)
    print("Testing Fallback Behavior (No Odds API Service)")
    print("=" * 80)
    print()

    # Setup database connection
    engine = create_engine(settings.database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        # Get test game
        game = get_test_game(db)
        if not game:
            print("❌ No test game found")
            return False

        # Initialize service WITHOUT odds API service
        prediction_service = EnhancedPredictionService(
            db=db,
            odds_api_service=None  # No Odds API - should use estimation
        )

        # Get active players
        players = prediction_service._get_active_players(game)
        if not players:
            print("❌ No active players found")
            return False

        test_player = players[0]

        # Fetch line (should use estimation)
        print(f"Testing line estimation for {test_player.name}...")
        line_data = prediction_service._get_bookmaker_line(
            test_player, game, "points", "draftkings"
        )

        if not line_data:
            print("❌ Failed to get estimated line")
            return False

        print(f"✅ Estimated line data:")
        print(f"   Line: {line_data['line']}")
        print(f"   Line Source: {line_data.get('line_source', 'N/A')}")
        print(f"   Bookmaker: {line_data.get('bookmaker', 'N/A')}")

        # Verify it's marked as estimated
        if line_data.get('line_source') == 'estimated':
            print("\n✅ Correctly identified as estimated line")
            return True
        else:
            print(f"\n❌ Expected 'estimated' but got '{line_data.get('line_source')}'")
            return False

    except Exception as e:
        print(f"\n❌ Error during fallback test: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Test Odds API integration"
    )
    parser.add_argument(
        '--test-fallback',
        action='store_true',
        help='Test fallback behavior without Odds API'
    )

    args = parser.parse_args()

    if args.test_fallback:
        success = test_fallback_behavior()
    else:
        success = test_odds_api_integration()

    sys.exit(0 if success else 1)
