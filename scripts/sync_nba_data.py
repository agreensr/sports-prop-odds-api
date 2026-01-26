#!/usr/bin/env python3
"""
Manual NBA Data Sync Script.

Provides command-line interface for syncing NBA data from nba_api.
"""
import sys
import os
import asyncio
import argparse
from pathlib import Path

# Add project root to Python path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.core.database import SessionLocal
from app.services.nba.nba_data_service import NbaDataService, CURRENT_SEASON


async def sync_stats(season: str = None):
    """
    Sync player stats from nba_api.

    Args:
        season: Season string (e.g., "2024-25"). Defaults to CURRENT_SEASON.
    """
    if season is None:
        season = CURRENT_SEASON

    print(f"🔄 Syncing player stats for season {season}...")

    db = SessionLocal()
    try:
        service = NbaDataService(db)
        result = await service.update_player_season_stats(season=season)

        if result["status"] == "success":
            print(f"✅ Stats sync complete:")
            print(f"   Created: {result['created']}")
            print(f"   Updated: {result['updated']}")
            print(f"   Errors: {result['errors']}")
            print(f"   Total: {result['total']}")
        else:
            print(f"❌ Stats sync failed: {result['message']}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()


async def show_league_leaders(stat: str, top_n: int):
    """
    Display league leaders for a stat.

    Args:
        stat: Stat category (PTS, REB, AST, FG3M, etc.)
        top_n: Number of players to show
    """
    print(f"🏆 Top {top_n} NBA players by {stat}...")

    db = SessionLocal()
    try:
        service = NbaDataService(db)
        leaders = await service.get_league_leaders(stat=stat, top_n=top_n)

        if not leaders:
            print("No data found")
            return

        print(f"\n{'Rank':<6}{'Player':<25}{'Team':<6}{'GP':<6}{'Value':<10}")
        print("-" * 55)

        for i, player in enumerate(leaders, 1):
            name = player.get('PLAYER_NAME', 'Unknown')
            team = player.get('TEAM_ABBREVIATION', 'N/A')
            gp = player.get('GP', 0)
            value = player.get(stat, 0)

            print(f"{i:<6}{name:<25}{team:<6}{gp:<6}{value:<10.2f}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()


async def show_team_stats(team_abbr: str):
    """
    Display stats for all players on a team.

    Args:
        team_abbr: 3-letter team abbreviation (e.g., "LAL")
    """
    print(f"📊 Stats for {team_abbr}...")

    db = SessionLocal()
    try:
        service = NbaDataService(db)
        stats = await service.get_player_stats_by_team(team_abbr)

        if not stats:
            print(f"No data found for team {team_abbr}")
            return

        print(f"\n{'Player':<25}{'GP':<6}{'PTS':<8}{'REB':<8}{'AST':<8}{'3PM':<8}{'MIN':<8}")
        print("-" * 75)

        for player in sorted(stats, key=lambda x: x.get('PTS', 0), reverse=True):
            name = player.get('PLAYER_NAME', 'Unknown')
            gp = player.get('GP', 0)
            pts = player.get('PTS', 0)
            reb = player.get('REB', 0)
            ast = player.get('AST', 0)
            fg3m = player.get('FG3M', 0)
            minutes = player.get('MIN', 0)

            print(f"{name:<25}{gp:<6}{pts:<8.1f}{reb:<8.1f}{ast:<8.1f}{fg3m:<8.1f}{minutes:<8.1f}")

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

    finally:
        db.close()


async def main():
    parser = argparse.ArgumentParser(
        description="Manual NBA data sync from nba_api",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Sync player stats for current season
  python scripts/sync_nba_data.py --stats

  # Sync player stats for specific season
  python scripts/sync_nba_data.py --stats --season 2024-25

  # Show top 20 scorers
  python scripts/sync_nba_data.py --leaders PTS --top 20

  # Show stats for Lakers
  python scripts/sync_nba_data.py --team LAL
        """
    )

    parser.add_argument(
        '--stats',
        action='store_true',
        help='Sync player stats from nba_api'
    )
    parser.add_argument(
        '--season',
        type=str,
        default=None,
        help='Season (e.g., 2024-25). Defaults to CURRENT_SEASON from config.'
    )
    parser.add_argument(
        '--leaders',
        type=str,
        metavar='STAT',
        help='Show league leaders for stat (PTS, REB, AST, FG3M, etc.)'
    )
    parser.add_argument(
        '--top',
        type=int,
        default=50,
        help='Number of top players to show (default: 50)'
    )
    parser.add_argument(
        '--team',
        type=str,
        metavar='ABBR',
        help='Show stats for team (3-letter abbreviation, e.g., LAL)'
    )

    args = parser.parse_args()

    # Execute requested action
    if args.stats:
        await sync_stats(args.season)
    elif args.leaders:
        await show_league_leaders(args.leaders, args.top)
    elif args.team:
        await show_team_stats(args.team.upper())
    else:
        parser.print_help()


if __name__ == "__main__":
    asyncio.run(main())
