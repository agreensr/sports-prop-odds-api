#!/usr/bin/env python3
"""
Daily Single Bet Generation Script.

This script runs daily to generate the top 10 single bets
across all sports based on predictions.

Usage:
    python scripts/generate_single_bets.py                    # Generate for today
    python scripts/generate_single_bets.py --date 2026-01-27  # Specific date
    python scripts/generate_single_bets.py --sport nba        # Specific sport
    python scripts/generate_single_bets.py --display          # Display format
    python scripts/generate_single_bets.py --dry-run         # Show what would be generated

Output:
    - Generates top 10 single bets
    - Stores in database (optional)
    - Prints formatted output
    - Can send notifications (future)

Schedule:
    Run daily at 9:00 AM ET (before games start)
"""
import argparse
import logging
import os
import sys
from datetime import date, datetime

# Add parent directory to path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def main():
    """Main entry point for single bet generation."""
    parser = argparse.ArgumentParser(
        description="Generate daily single bet recommendations"
    )
    parser.add_argument(
        '--date',
        type=str,
        help='Target date (YYYY-MM-DD format, default: today)'
    )
    parser.add_argument(
        '--sport',
        type=str,
        choices=['nba', 'nfl', 'mlb', 'nhl'],
        help='Filter by sport (default: all sports)'
    )
    parser.add_argument(
        '--display',
        action='store_true',
        help='Output in display format (human-readable)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be generated without storing'
    )
    parser.add_argument(
        '--output',
        type=str,
        help='Write output to file'
    )

    args = parser.parse_args()

    # Parse target date
    if args.date:
        try:
            target_date = datetime.strptime(args.date, '%Y-%m-%d').date()
        except ValueError:
            logger.error(f"Invalid date format: {args.date}. Use YYYY-MM-DD.")
            sys.exit(1)
    else:
        target_date = date.today()

    logger.info(f"Generating single bets for {target_date}")
    if args.sport:
        logger.info(f"Sport: {args.sport}")

    # Initialize database session
    from app.core.database import SessionLocal
    from app.services.core.single_bet_service import SingleBetService

    db = SessionLocal()

    try:
        # Create service
        service = SingleBetService(db)

        # Generate bets
        logger.info("Fetching predictions and calculating edge/EV...")
        bets = service.generate_daily_bets(
            target_date=target_date,
            sport_id=args.sport
        )

        if not bets:
            logger.warning("No bets generated!")
            print("\n❌ No bets meet the minimum thresholds (60% confidence, 5% edge)")
            return

        # Format output
        if args.display:
            output = service.format_bets_for_display(bets)
        else:
            # JSON format
            import json
            bets_data = [
                {
                    'id': bet.id,
                    'sport': bet.sport_id,
                    'player': bet.player_name,
                    'team': bet.team,
                    'opponent': bet.opponent,
                    'game_date': bet.game_date.isoformat(),
                    'stat': bet.stat_type,
                    'line': bet.bookmaker_line,
                    'recommendation': bet.recommendation.value,
                    'odds': bet.odds_american,
                    'confidence': round(bet.confidence * 100, 1),
                    'edge': round(bet.edge_percent, 1),
                    'ev': round(bet.ev_percent, 1),
                }
                for bet in bets
            ]
            output = json.dumps({
                'date': target_date.isoformat(),
                'sport': args.sport or 'all',
                'count': len(bets),
                'bets': bets_data
            }, indent=2)

        # Print output
        print()
        print("=" * 70)
        if args.display:
            print(output)
        else:
            print("🎯 DAILY SINGLE BETS")
            print("=" * 70)
            print(output)
        print("=" * 70)

        # Write to file if specified
        if args.output:
            with open(args.output, 'w') as f:
                f.write(output)
            logger.info(f"Output written to {args.output}")

        # TODO: Store bets in database for tracking
        # This would be useful for:
        # - Historical performance analysis
        # - Hit rate tracking
        # - EV vs actual results

        if not args.dry_run:
            logger.info("Bets generated successfully")
            logger.info(f"Next steps: Place bets at {', '.join(set(b.bookmaker_name for b in bets))}")
        else:
            logger.info("DRY RUN - No bets stored")

    except Exception as e:
        logger.error(f"Error generating bets: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        db.close()


if __name__ == '__main__':
    main()
