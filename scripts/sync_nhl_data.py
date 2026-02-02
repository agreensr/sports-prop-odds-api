#!/usr/bin/env python
"""
NHL Data Sync Script

This script syncs NHL data from ESPN API to the database:
1. Sync teams (32 NHL teams)
2. Sync games (upcoming and recent)
3. Sync player rosters for each team

Usage:
    python scripts/sync_nhl_data.py --teams
    python scripts/sync_nhl_data.py --games --days 14
    python scripts/sync_nhl_data.py --rosters
    python scripts/sync_nhl_data.py --all

Requirements:
    - Database connection string in DATABASE_URL env var
    - ESPN API (no key required)
"""
import argparse
import asyncio
import logging
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from app.core.database import get_db, engine
from app.models.nhl.models import Team, Player, Game, Base
from app.services.nhl.nhl_adapter import NhlApiAdapter

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# NHL team data for abbreviation mapping
NHL_TEAMS = {
    'Anaheim Ducks': {'abbr': 'ANA', 'conference': 'Western', 'division': 'Pacific'},
    'Arizona Coyotes': {'abbr': 'ARI', 'conference': 'Western', 'division': 'Central'},
    'Boston Bruins': {'abbr': 'BOS', 'conference': 'Eastern', 'division': 'Atlantic'},
    'Buffalo Sabres': {'abbr': 'BUF', 'conference': 'Eastern', 'division': 'Atlantic'},
    'Calgary Flames': {'abbr': 'CGY', 'conference': 'Western', 'division': 'Pacific'},
    'Carolina Hurricanes': {'abbr': 'CAR', 'conference': 'Eastern', 'division': 'Metropolitan'},
    'Chicago Blackhawks': {'abbr': 'CHI', 'conference': 'Western', 'division': 'Central'},
    'Colorado Avalanche': {'abbr': 'COL', 'conference': 'Western', 'division': 'Central'},
    'Columbus Blue Jackets': {'abbr': 'CBJ', 'conference': 'Eastern', 'division': 'Metropolitan'},
    'Dallas Stars': {'abbr': 'DAL', 'conference': 'Western', 'division': 'Central'},
    'Detroit Red Wings': {'abbr': 'DET', 'conference': 'Eastern', 'division': 'Atlantic'},
    'Edmonton Oilers': {'abbr': 'EDM', 'conference': 'Western', 'division': 'Pacific'},
    'Florida Panthers': {'abbr': 'FLA', 'conference': 'Eastern', 'division': 'Atlantic'},
    'Los Angeles Kings': {'abbr': 'LAK', 'conference': 'Western', 'division': 'Pacific'},
    'Minnesota Wild': {'abbr': 'MIN', 'conference': 'Western', 'division': 'Central'},
    'Montreal Canadiens': {'abbr': 'MTL', 'conference': 'Eastern', 'division': 'Atlantic'},
    'Nashville Predators': {'abbr': 'NSH', 'conference': 'Western', 'division': 'Central'},
    'New Jersey Devils': {'abbr': 'NJD', 'conference': 'Eastern', 'division': 'Metropolitan'},
    'New York Islanders': {'abbr': 'NYI', 'conference': 'Eastern', 'division': 'Metropolitan'},
    'New York Rangers': {'abbr': 'NYR', 'conference': 'Eastern', 'division': 'Metropolitan'},
    'Ottawa Senators': {'abbr': 'OTT', 'conference': 'Eastern', 'division': 'Atlantic'},
    'Philadelphia Flyers': {'abbr': 'PHI', 'conference': 'Eastern', 'division': 'Metropolitan'},
    'Pittsburgh Penguins': {'abbr': 'PIT', 'conference': 'Eastern', 'division': 'Metropolitan'},
    'San Jose Sharks': {'abbr': 'SJS', 'conference': 'Western', 'division': 'Pacific'},
    'Seattle Kraken': {'abbr': 'SEA', 'conference': 'Western', 'division': 'Pacific'},
    'St. Louis Blues': {'abbr': 'STL', 'conference': 'Western', 'division': 'Central'},
    'Tampa Bay Lightning': {'abbr': 'TBL', 'conference': 'Eastern', 'division': 'Atlantic'},
    'Toronto Maple Leafs': {'abbr': 'TOR', 'conference': 'Eastern', 'division': 'Atlantic'},
    'Vancouver Canucks': {'abbr': 'VAN', 'conference': 'Western', 'division': 'Pacific'},
    'Vegas Golden Knights': {'abbr': 'VGK', 'conference': 'Western', 'division': 'Pacific'},
    'Washington Capitals': {'abbr': 'WSH', 'conference': 'Eastern', 'division': 'Metropolitan'},
    'Winnipeg Jets': {'abbr': 'WPG', 'conference': 'Western', 'division': 'Central'},
}

# Arena information
NHL_ARENAS = {
    'ANA': 'Honda Center',
    'ARI': 'Mullett Arena',
    'BOS': 'TD Garden',
    'BUF': 'KeyBank Center',
    'CGY': 'Scotiabank Saddledome',
    'CAR': 'PNC Arena',
    'CHI': 'United Center',
    'COL': 'Ball Arena',
    'CBJ': 'Nationwide Arena',
    'DAL': 'American Airlines Center',
    'DET': 'Little Caesars Arena',
    'EDM': 'Rogers Place',
    'FLA': 'Amerant Bank Arena',
    'LAK': 'Crypto.com Arena',
    'MIN': 'Xcel Energy Center',
    'MTL': 'Bell Centre',
    'NSH': 'Bridgestone Arena',
    'NJD': 'Prudential Center',
    'NYI': 'UBS Arena',
    'NYR': 'Madison Square Garden',
    'OTT': 'Canadian Tire Centre',
    'PHI': 'Wells Fargo Center',
    'PIT': 'PPG Paints Arena',
    'SJS': 'SAP Center',
    'SEA': 'Climate Pledge Arena',
    'STL': 'Enterprise Center',
    'TBL': 'Amalie Arena',
    'TOR': 'Scotiabank Arena',
    'VAN': 'Rogers Arena',
    'VGK': 'T-Mobile Arena',
    'WSH': 'Capital One Arena',
    'WPG': 'Canada Life Centre',
}


async def sync_teams(db: Session, adapter: NhlApiAdapter) -> dict:
    """Sync NHL teams from ESPN to database."""
    logger.info("Syncing NHL teams...")

    # Get teams from ESPN
    espn_teams = await adapter.fetch_teams()

    if not espn_teams:
        logger.warning("No teams returned from ESPN, using static data")
        # Use static team data
        for team_name, info in NHL_TEAMS.items():
            abbr = info['abbr']
            existing = db.query(Team).filter(Team.abbreviation == abbr).first()

            if not existing:
                team = Team(
                    id=uuid.uuid4(),
                    espn_id=None,  # Will update if we get ESPN ID
                    abbreviation=abbr,
                    name=team_name,
                    city=team_name.split()[-1] if team_name.endswith('s') else ' '.join(team_name.split()[:-1]),
                    mascot=None,
                    conference=info['conference'],
                    division=info['division'],
                    arena=NHL_ARENAS.get(abbr)
                )
                db.add(team)
                logger.info(f"Added team: {abbr} - {team_name}")
            else:
                logger.debug(f"Team already exists: {abbr}")

        db.commit()
        return {'synced': len(NHL_TEAMS), 'source': 'static'}

    # Process ESPN teams
    synced = 0
    for espn_team in espn_teams:
        abbr = espn_team.get('abbreviation')
        name = espn_team.get('name')

        if not abbr:
            logger.warning(f"No abbreviation found for: {name}")
            continue

        info = NHL_TEAMS.get(name, {})
        existing = db.query(Team).filter(Team.abbreviation == abbr).first()

        if not existing:
            # Get venue name
            arena = NHL_ARENAS.get(abbr)
            venue_info = espn_team.get('venue')
            if venue_info and venue_info.get('full_name'):
                arena = venue_info['full_name']

            team = Team(
                id=uuid.uuid4(),
                espn_id=espn_team.get('id'),
                abbreviation=abbr,
                name=name,
                city=espn_team.get('location', ''),
                mascot=None,
                conference=info.get('conference'),
                division=info.get('division'),
                arena=arena
            )
            db.add(team)
            synced += 1
            logger.info(f"Added team: {abbr} - {name}")
        else:
            # Update ESPN ID if missing
            if not existing.espn_id:
                existing.espn_id = espn_team.get('id')
            synced += 1

    db.commit()
    logger.info(f"Synced {synced} NHL teams")

    return {'synced': synced, 'source': 'espn'}


async def sync_games(db: Session, adapter: NhlApiAdapter, days: int = 14) -> dict:
    """Sync NHL games from ESPN to database."""
    logger.info(f"Syncing NHL games ({days} days ahead)...")

    # Fetch games
    games_data = await adapter.fetch_games(
        lookback_days=7,
        lookahead_days=days
    )

    if not games_data:
        logger.warning("No games returned from ESPN")
        return {'synced': 0, 'source': 'espn'}

    synced = 0
    for game_data in games_data:
        # Check if game already exists
        existing = db.query(Game).filter(Game.espn_id == game_data.get('id')).first()

        if not existing:
            # Verify teams exist
            home_team = db.query(Team).filter(
                Team.abbreviation == game_data.get('home_team')
            ).first()
            away_team = db.query(Team).filter(
                Team.abbreviation == game_data.get('away_team')
            ).first()

            if not home_team:
                logger.warning(f"Home team not found: {game_data.get('home_team')}")
                continue
            if not away_team:
                logger.warning(f"Away team not found: {game_data.get('away_team')}")
                continue

            game = Game(
                id=uuid.uuid4(),
                espn_id=game_data.get('id'),
                nhl_id=None,
                season=game_data.get('season', datetime.now().year),
                season_type='REG',
                game_date=game_data.get('game_date'),
                home_team=game_data.get('home_team'),
                away_team=game_data.get('away_team'),
                home_score=game_data.get('home_score', 0) or 0,
                away_score=game_data.get('away_score', 0) or 0,
                status=game_data.get('status', 'scheduled')
            )
            db.add(game)
            synced += 1
            logger.info(
                f"Added game: {game_data.get('away_team')} @ "
                f"{game_data.get('home_team')} on {game_data.get('game_date')}"
            )
        else:
            # Update scores if game is in progress or final
            if existing.status in ['in_progress', 'final']:
                existing.home_score = game_data.get('home_score', 0) or 0
                existing.away_score = game_data.get('away_score', 0) or 0
                existing.status = game_data.get('status', existing.status)
            synced += 1

    db.commit()
    logger.info(f"Synced {synced} NHL games")

    return {'synced': synced, 'source': 'espn'}


async def sync_rosters(db: Session, adapter: NhlApiAdapter) -> dict:
    """Sync NHL player rosters from ESPN to database."""
    logger.info("Syncing NHL player rosters...")

    # Get all teams
    teams = db.query(Team).all()

    if not teams:
        logger.error("No teams found. Sync teams first.")
        return {'synced': 0, 'error': 'no_teams'}

    total_players = 0
    for team in teams:
        if not team.espn_id:
            logger.warning(f"Skipping {team.abbreviation}: no ESPN ID")
            continue

        try:
            roster = await adapter.fetch_roster(str(team.id), str(team.espn_id))

            for player_data in roster:
                # Check if player exists
                existing = db.query(Player).filter(
                    Player.espn_id == player_data.get('espn_id')
                ).first()

                if not existing:
                    player = Player(
                        id=uuid.uuid4(),
                        espn_id=player_data.get('espn_id'),
                        nhl_id=None,
                        name=player_data.get('name'),
                        full_name=player_data.get('name'),
                        position=player_data.get('position'),
                        jersey_number=player_data.get('jersey'),
                        team_id=team.id,
                        team=team.abbreviation,
                        status='active' if player_data.get('active') else 'inactive'
                    )
                    db.add(player)
                    total_players += 1
                    logger.debug(
                        f"Added player: {player_data.get('name')} "
                        f"({player_data.get('position')}) - {team.abbreviation}"
                    )
                else:
                    # Update team if changed
                    if existing.team != team.abbreviation:
                        existing.team = team.abbreviation
                        existing.team_id = team.id

        except Exception as e:
            logger.error(f"Error syncing roster for {team.abbreviation}: {e}")
            continue

    db.commit()
    logger.info(f"Synced {total_players} NHL players")

    return {'synced': total_players, 'source': 'espn'}


async def main():
    parser = argparse.ArgumentParser(description='Sync NHL data from ESPN API')
    parser.add_argument('--teams', action='store_true', help='Sync teams')
    parser.add_argument('--games', action='store_true', help='Sync games')
    parser.add_argument('--rosters', action='store_true', help='Sync player rosters')
    parser.add_argument('--all', action='store_true', help='Sync everything')
    parser.add_argument('--days', type=int, default=14, help='Days ahead for games')
    parser.add_argument('--stats', action='store_true', help='Show database stats')

    args = parser.parse_args()

    # Create database session
    db = next(get_db())

    # Create adapter
    adapter = NhlApiAdapter(db)

    try:
        if args.stats:
            # Show current database stats
            print("\n=== NHL Database Stats ===")
            print(f"Teams: {db.query(Team).count()}")
            print(f"Players: {db.query(Player).count()}")
            print(f"Games: {db.query(Game).count()}")

            # Show upcoming games
            upcoming = db.query(Game).filter(
                Game.status == 'scheduled',
                Game.game_date > datetime.now()
            ).order_by(Game.game_date).limit(10).all()

            print(f"\nUpcoming Games (next 10):")
            for game in upcoming:
                print(f"  {game.game_date}: {game.away_team} @ {game.home_team}")

            return

        if args.all:
            args.teams = True
            args.games = True
            args.rosters = True

        if not any([args.teams, args.games, args.rosters]):
            parser.print_help()
            print("\nNo action specified. Use --teams, --games, --rosters, or --all")
            return

        results = {}

        if args.teams:
            results['teams'] = await sync_teams(db, adapter)

        if args.games:
            results['games'] = await sync_games(db, adapter, args.days)

        if args.rosters:
            results['rosters'] = await sync_rosters(db, adapter)

        # Print summary
        print("\n=== Sync Summary ===")
        for key, value in results.items():
            print(f"{key.capitalize()}: {value}")

    finally:
        db.close()


if __name__ == '__main__':
    asyncio.run(main())
