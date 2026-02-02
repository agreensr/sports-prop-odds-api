"""
MLB API adapter for normalizing data from various MLB sources.

This adapter provides a consistent interface for MLB data:
- ESPN API: Scores, news, team data, rosters
- The Odds API: Betting odds and player props
- MLB Stats API (future): Historical stats

Sport: MLB
Teams: 30 teams
Season: March - September
Playoffs: October - November
World Series: Late October/November
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class MlbApiAdapter:
    """
    Adapter for MLB data sources.

    Normalizes data from:
    - ESPN API (for scores, news, teams, rosters)
    - The Odds API (for betting odds)
    - MLB Stats API (future, for historical stats)
    """

    def __init__(self, db: Session):
        """
        Initialize the MLB API adapter.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self.sport_id = 'mlb'

    async def fetch_games(
        self,
        lookback_days: int = 7,
        lookahead_days: int = 14,
        season: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch MLB games from ESPN API.

        Args:
            lookback_days: Days to look back
            lookahead_days: Days to look ahead
            season: MLB season year (e.g., 2025)

        Returns:
            List of normalized game dicts
        """
        from app.services.core.espn_service import ESPNApiService

        if not season:
            season = datetime.now().year

        all_games = []
        espn_service = ESPNApiService()

        # Fetch games for each day
        base_date = datetime.now()
        date_range = range(-lookback_days, lookahead_days + 1)

        for offset in date_range:
            game_date = base_date + timedelta(days=offset)
            date_str = game_date.strftime('%Y%m%d')

            try:
                # Use ESPN API for scores
                games = await espn_service.get_scores('mlb', date_str)

                for game in games:
                    normalized = self._normalize_game(game)
                    if normalized:
                        all_games.append(normalized)

            except Exception as e:
                logger.error(f"Error fetching MLB games for {date_str}: {e}")

        await espn_service.close()
        logger.info(f"Fetched {len(all_games)} MLB games")

        return all_games

    def _normalize_game(self, game: Dict) -> Optional[Dict[str, Any]]:
        """
        Normalize ESPN game data to standard format.

        Args:
            game: Raw ESPN game data

        Returns:
            Normalized game dict or None
        """
        try:
            competitors = game.get('competitors', {})
            home = competitors.get('home', {})
            away = competitors.get('away', {})

            return {
                'id': game.get('id'),
                'sport_id': self.sport_id,
                'game_date': game.get('date'),
                'away_team': away.get('abbreviation', ''),
                'home_team': home.get('abbreviation', ''),
                'away_score': away.get('score'),
                'home_score': home.get('score'),
                'status': game.get('status', 'scheduled'),
                'season': self._get_season_from_date(game.get('date')),
                'source': 'espn',
                'raw_data': game,
            }
        except Exception as e:
            logger.error(f"Error normalizing MLB game: {e}")
            return None

    def _get_season_from_date(self, game_date: Optional[datetime]) -> int:
        """
        Determine MLB season from game date.

        MLB season starts in April. Games in Jan-Mar
        belong to the current year's season.

        Args:
            game_date: Game datetime

        Returns:
            Season year
        """
        if not game_date:
            return datetime.now().year

        if game_date.month >= 4:
            return game_date.year
        else:
            # Jan-Mar games belong to current season
            return game_date.year

    async def fetch_teams(self) -> List[Dict[str, Any]]:
        """
        Fetch MLB teams from ESPN API.

        Returns:
            List of normalized team dicts
        """
        from app.services.core.espn_service import ESPNApiService

        espn_service = ESPNApiService()

        try:
            teams = await espn_service.get_teams('mlb')

            normalized = []
            for team in teams:
                normalized.append({
                    'id': team.get('id'),
                    'sport_id': self.sport_id,
                    'name': team.get('name'),
                    'display_name': team.get('display_name'),
                    'abbreviation': team.get('abbreviation'),
                    'logo': team.get('logo'),
                    'color': team.get('color'),
                    'venue': team.get('venue'),
                    'source': 'espn',
                })

            await espn_service.close()
            logger.info(f"Fetched {len(normalized)} MLB teams")
            return normalized

        except Exception as e:
            logger.error(f"Error fetching MLB teams: {e}")
            await espn_service.close()
            return []

    async def fetch_roster(
        self,
        team_id: str,
        espn_team_id: str
    ) -> List[Dict[str, Any]]:
        """
        Fetch roster for an MLB team.

        Args:
            team_id: Internal team ID
            espn_team_id: ESPN team ID

        Returns:
            List of normalized player dicts
        """
        from app.services.core.espn_service import ESPNApiService

        espn_service = ESPNApiService()

        try:
            roster = await espn_service.get_team_roster('mlb', espn_team_id)

            normalized = []
            for player in roster:
                normalized.append({
                    'espn_id': player.get('id'),
                    'sport_id': self.sport_id,
                    'name': player.get('name'),
                    'first_name': player.get('first_name'),
                    'last_name': player.get('last_name'),
                    'position': player.get('position'),
                    'jersey': player.get('jersey'),
                    'team': team_id,
                    'active': player.get('status') == 'ACT',
                    'source': 'espn',
                    'raw_data': player,
                })

            await espn_service.close()
            logger.info(f"Fetched {len(normalized)} players for team {team_id}")
            return normalized

        except Exception as e:
            logger.error(f"Error fetching roster for {team_id}: {e}")
            await espn_service.close()
            return []

    def get_team_abbreviation(self, team_name: str) -> Optional[str]:
        """
        Get MLB team abbreviation from full name.

        Args:
            team_name: Full team name

        Returns:
            3-letter abbreviation or None
        """
        # MLB team abbreviations
        abbreviations = {
            'Arizona Diamondbacks': 'ARI',
            'Atlanta Braves': 'ATL',
            'Baltimore Orioles': 'BAL',
            'Boston Red Sox': 'BOS',
            'Chicago Cubs': 'CHC',
            'Chicago White Sox': 'CWS',
            'Cincinnati Reds': 'CIN',
            'Cleveland Guardians': 'CLE',
            'Colorado Rockies': 'COL',
            'Detroit Tigers': 'DET',
            'Houston Astros': 'HOU',
            'Kansas City Royals': 'KC',
            'Los Angeles Angels': 'LAA',
            'Los Angeles Dodgers': 'LAD',
            'Miami Marlins': 'MIA',
            'Milwaukee Brewers': 'MIL',
            'Minnesota Twins': 'MIN',
            'New York Mets': 'NYM',
            'New York Yankees': 'NYY',
            'Oakland Athletics': 'OAK',
            'Philadelphia Phillies': 'PHI',
            'Pittsburgh Pirates': 'PIT',
            'San Diego Padres': 'SD',
            'San Francisco Giants': 'SF',
            'Seattle Mariners': 'SEA',
            'St. Louis Cardinals': 'STL',
            'Tampa Bay Rays': 'TB',
            'Texas Rangers': 'TEX',
            'Toronto Blue Jays': 'TOR',
            'Washington Nationals': 'WSH',
        }

        return abbreviations.get(team_name)


# Convenience function
def get_mlb_adapter(db: Session) -> MlbApiAdapter:
    """Get MLB adapter instance."""
    return MlbApiAdapter(db)
