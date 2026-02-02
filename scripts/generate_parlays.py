#!/usr/bin/env python3
"""
Daily 2-Leg Parlay Generation Script (Phase 4).

This script generates 2-leg parlays from the top 10 single bets.

Strategy:
- Source: Top 10 single bets from SingleBetService
- Type: 2-leg parlays ONLY
- Same-game: ALLOWED (any combination)
- Cross-game: ALLOWED
- Filter: Parlay EV ≥ 8%
- Limit: Top 5 parlays
- Rank: By EV (descending)

Usage:
    python scripts/generate_parlays.py                    # Generate for today
    python scripts/generate_parlays.py --date 2026-01-27  # Specific date
    python scripts/generate_parlays.py --sport nba        # Specific sport
    python scripts/generate_parlays.py --display          # Display format
    python scripts/generate_parlays.py --dry-run         # Show what would be generated
    python scripts/generate_parlays.py --output parlays.json  # Write to file
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
    """Main entry point for parlay generation."""
    parser = argparse.ArgumentParser(
        description="Generate daily 2-leg parlay recommendations from top single bets"
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
    parser.add_argument(
        '--min-ev',
        type=float,
        default=8.0,
        help='Minimum EV percentage (default: 8.0)'
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

    logger.info(f"Generating 2-leg parlays for {target_date}")
    if args.sport:
        logger.info(f"Sport: {args.sport}")

    # Initialize database session
    from app.core.database import SessionLocal
    from app.services.core.enhanced_parlay_service import EnhancedParlayService

    db = SessionLocal()

    try:
        # Create service
        service = EnhancedParlayService(db)

        # Set custom EV threshold if provided
        if args.min_ev != 8.0:
            service.MIN_PARLAY_EV = args.min_ev / 100

        # Generate parlays
        logger.info("Fetching top single bets and generating 2-leg combinations...")
        parlays = service.generate_daily_parlays(
            target_date=target_date,
            sport_id=args.sport
        )

        if not parlays:
            logger.warning("No parlays generated!")
            print("\n❌ No parlays meet the minimum thresholds")
            print("   This could mean:")
            print("   - No single bets available (need 10 single bets first)")
            print("   - No parlay combinations meet the EV threshold")
            print(f"   - Current EV threshold: {args.min_ev}%")
            return

        # Format output
        if args.display:
            output = service.format_parlays_for_display(parlays)
        else:
            # JSON format
            import json
            parlays_data = []
            for parlay in parlays:
                parlay_dict = {
                    'id': parlay.id,
                    'type': parlay.parlay_type,
                    'legs': [
                        {
                            'player': leg['player_name'],
                            'team': leg['team'],
                            'stat': leg['stat_type'],
                            'line': leg['line'],
                            'rec': leg['recommendation'],
                            'odds': leg['odds_american']
                        }
                        for leg in parlay.legs
                    ],
                    'odds': parlay.calculated_odds,
                    'ev': round(parlay.ev_percent, 1),
                    'confidence': round(parlay.confidence_score, 2),
                    'correlation': round(parlay.correlation_score, 2)
                }
                parlays_data.append(parlay_dict)

            output = json.dumps({
                'date': target_date.isoformat(),
                'sport': args.sport or 'all',
                'count': len(parlays),
                'parlays': parlays_data
            }, indent=2)

        # Print output
        print()
        print("=" * 70)
        if args.display:
            print(output)
        else:
            print("🎯 DAILY 2-LEG PARLAYS")
            print("=" * 70)
            print(output)
        print("=" * 70)

        # Write to file if specified
        if args.output:
            with open(args.output, 'w') as f:
                f.write(output)
            logger.info(f"Output written to {args.output}")

        if not args.dry_run:
            logger.info("Parlays generated successfully")
        else:
            logger.info("DRY RUN - No parlays stored")

    except Exception as e:
        logger.error(f"Error generating parlays: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        db.close()


if __name__ == '__main__':
    main()
