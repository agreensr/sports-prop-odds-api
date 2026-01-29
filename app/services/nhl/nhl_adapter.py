"""
NHL API adapter for normalizing data from various NHL sources.

This adapter provides a consistent interface for NHL data:
- ESPN API: Scores, news, team data, rosters
- The Odds API: Betting odds and player props
- NHL Stats API (future): Historical stats

Sport: NHL
Teams: 32 teams
Season: October - April
Playoffs: April - June
Stanley Cup: June
"""
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class NhlApiAdapter:
    """
    Adapter for NHL data sources.

    Normalizes data from:
    - ESPN API (for scores, news, teams, rosters)
    - The Odds API (for betting odds)
    - NHL Stats API (future, for historical stats)
    """

    def __init__(self, db: Session):
        """
        Initialize the NHL API adapter.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self.sport_id = 'nhl'

    async def fetch_games(
        self,
        lookback_days: int = 7,
        lookahead_days: int = 14,
        season: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Fetch NHL games from ESPN API.

        Args:
            lookback_days: Days to look back
            lookahead_days: Days to look ahead
            season: NHL season year (e.g., 2025 for 2025-26 season)

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
                games = await espn_service.get_scores('nhl', date_str)

                for game in games:
                    normalized = self._normalize_game(game)
                    if normalized:
                        all_games.append(normalized)

            except Exception as e:
                logger.error(f"Error fetching NHL games for {date_str}: {e}")

        await espn_service.close()
        logger.info(f"Fetched {len(all_games)} NHL games")

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
            logger.error(f"Error normalizing NHL game: {e}")
            return None

    def _get_season_from_date(self, game_date: Optional[datetime]) -> int:
        """
        Determine NHL season from game date.

        NHL season starts in October. Games in Jan-Jun
        belong to the previous year's season.

        Args:
            game_date: Game datetime

        Returns:
            Season year
        """
        if not game_date:
            return datetime.now().year

        if game_date.month >= 10:
            return game_date.year
        else:
            # Jan-Jun games belong to previous season
            return game_date.year - 1

    async def fetch_teams(self) -> List[Dict[str, Any]]:
        """
        Fetch NHL teams from ESPN API.

        Returns:
            List of normalized team dicts
        """
        from app.services.core.espn_service import ESPNApiService

        espn_service = ESPNApiService()

        try:
            teams = await espn_service.get_teams('nhl')

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
            logger.info(f"Fetched {len(normalized)} NHL teams")
            return normalized

        except Exception as e:
            logger.error(f"Error fetching NHL teams: {e}")
            await espn_service.close()
            return []

    async def fetch_roster(
        self,
        team_id: str,
        espn_team_id: str
    ) -> List[Dict[str, Any]]:
        """
        Fetch roster for an NHL team.

        Args:
            team_id: Internal team ID
            espn_team_id: ESPN team ID

        Returns:
            List of normalized player dicts
        """
        from app.services.core.espn_service import ESPNApiService

        espn_service = ESPNApiService()

        try:
            roster = await espn_service.get_team_roster('nhl', espn_team_id)

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
        Get NHL team abbreviation from full name.

        Args:
            team_name: Full team name

        Returns:
            3-letter abbreviation or None
        """
        # NHL team abbreviations
        abbreviations = {
            'Anaheim Ducks': 'ANA',
            'Arizona Coyotes': 'ARI',
            'Boston Bruins': 'BOS',
            'Buffalo Sabres': 'BUF',
            'Calgary Flames': 'CGY',
            'Carolina Hurricanes': 'CAR',
            'Chicago Blackhawks': 'CHI',
            'Colorado Avalanche': 'COL',
            'Columbus Blue Jackets': 'CBJ',
            'Dallas Stars': 'DAL',
            'Detroit Red Wings': 'DET',
            'Edmonton Oilers': 'EDM',
            'Florida Panthers': 'FLA',
            'Los Angeles Kings': 'LAK',
            'Minnesota Wild': 'MIN',
            'Montreal Canadiens': 'MTL',
            'Nashville Predators': 'NSH',
            'New Jersey Devils': 'NJD',
            'New York Islanders': 'NYI',
            'New York Rangers': 'NYR',
            'Ottawa Senators': 'OTT',
            'Philadelphia Flyers': 'PHI',
            'Pittsburgh Penguins': 'PIT',
            'San Jose Sharks': 'SJS',
            'Seattle Kraken': 'SEA',
            'St. Louis Blues': 'STL',
            'Tampa Bay Lightning': 'TBL',
            'Toronto Maple Leafs': 'TOR',
            'Vancouver Canucks': 'VAN',
            'Vegas Golden Knights': 'VGK',
            'Washington Capitals': 'WSH',
            'Winnipeg Jets': 'WPG',
        }

        return abbreviations.get(team_name)


# Convenience function
def get_nhl_adapter(db: Session) -> NhlApiAdapter:
    """Get NHL adapter instance."""
    return NhlApiAdapter(db)
