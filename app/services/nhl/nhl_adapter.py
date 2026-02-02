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
        import httpx

        if not season:
            season = datetime.now().year

        all_games = []

        # Fetch games for each day
        base_date = datetime.now()
        date_range = range(-lookback_days, lookahead_days + 1)

        async with httpx.AsyncClient(timeout=30.0) as client:
            for offset in date_range:
                game_date = base_date + timedelta(days=offset)
                date_str = game_date.strftime('%Y%m%d')

                try:
                    # Direct ESPN API call for NHL scoreboard
                    url = f"https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard?dates={date_str}"
                    response = await client.get(url)
                    response.raise_for_status()
                    data = response.json()

                    # Normalize each event
                    for event in data.get('events', []):
                        normalized = self._normalize_game(event)
                        if normalized:
                            all_games.append(normalized)

                except Exception as e:
                    logger.error(f"Error fetching NHL games for {date_str}: {e}")

        logger.info(f"Fetched {len(all_games)} NHL games")

        return all_games

    def _normalize_game(self, game: Dict) -> Optional[Dict[str, Any]]:
        """
        Normalize ESPN game data to standard format.

        Args:
            game: Raw ESPN event data with 'competitions' array

        Returns:
            Normalized game dict or None
        """
        try:
            from datetime import datetime

            if not game:
                return None

            # Handle raw ESPN event format (from direct API call)
            competitions = game.get('competitions', [])
            if not competitions:
                return None

            comp = competitions[0]
            competitors = comp.get('competitors', [])
            if not competitors or len(competitors) < 2:
                return None

            # Parse home and away teams
            home_team = None
            away_team = None
            home_score = 0
            away_score = 0

            for comp_team in competitors:
                team_data = comp_team.get('team', {})
                abbreviation = team_data.get('abbreviation', '')
                score = comp_team.get('score', 0) or 0

                if comp_team.get('homeAway') == 'home':
                    home_team = abbreviation
                    home_score = int(score)
                else:
                    away_team = abbreviation
                    away_score = int(score)

            if not home_team or not away_team:
                return None

            # Parse status - handle missing data gracefully
            status_data = comp.get('status')
            if not status_data:
                status_data = {}

            # Try multiple possible status structures
            status_type = status_data.get('type') if isinstance(status_data, dict) else None
            if not status_type:
                # Try direct state/id from status
                status_state = status_data.get('state', 'pre') if isinstance(status_data, dict) else 'pre'
                status_id = status_data.get('id', '1') if isinstance(status_data, dict) else '1'
            else:
                status_state = status_type.get('state', 'pre')
                status_id = status_type.get('id', '1')

            # Map ESPN status to our status
            status_map = {
                '1': 'scheduled',
                '2': 'in_progress',
                '3': 'final'
            }
            status = status_map.get(str(status_id), status_state if status_state in ['scheduled', 'in_progress', 'final'] else 'scheduled')

            # Parse date
            date_str = game.get('date')
            game_date = None
            if date_str:
                try:
                    game_date = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                except:
                    pass

            # Get season year
            season_data = game.get('season', {})
            season_year = season_data.get('year', datetime.now().year)

            return {
                'id': game.get('id'),
                'sport_id': self.sport_id,
                'game_date': game_date,
                'away_team': away_team,
                'home_team': home_team,
                'away_score': away_score,
                'home_score': home_score,
                'status': status,
                'season': season_year,
                'source': 'espn',
                'raw_data': game,
            }
        except Exception as e:
            logger.error(f"Error normalizing NHL game: {e}, game keys: {list(game.keys()) if game else 'None'}")
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
            List of normalized team dicts with structure:
            {
                'id': team ESPN ID,
                'abbreviation': 'ANA',
                'name': 'Anaheim Ducks',
                'short_name': 'Ducks',
                'location': 'Anaheim',
                'logo': logo_url,
                'color': hex_color,
                'venue': venue_info
            }
        """
        from app.services.core.espn_service import ESPNApiService
        import httpx

        espn_service = ESPNApiService()

        try:
            # Direct API call for better control
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/teams",
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

            # Parse teams from ESPN structure: sports[0].leagues[0].teams
            teams = []
            sports = data.get('sports', [])
            if sports:
                leagues = sports[0].get('leagues', [])
                if leagues:
                    for team_item in leagues[0].get('teams', []):
                        team_data = team_item.get('team', {})
                        teams.append(team_data)

            normalized = []
            for team in teams:
                # Get venue info if available
                venue = None
                if 'venue' in team:
                    venue_data = team['venue']
                    venue = {
                        'id': venue_data.get('id'),
                        'full_name': venue_data.get('fullName'),
                        'city': venue_data.get('address', {}).get('city'),
                    }

                normalized.append({
                    'id': team.get('id'),
                    'abbreviation': team.get('abbreviation'),
                    'name': team.get('displayName'),  # Full name "Anaheim Ducks"
                    'short_name': team.get('shortDisplayName'),  # "Ducks"
                    'location': team.get('location'),  # "Anaheim"
                    'logo': team.get('logos', [{}])[0].get('href') if team.get('logos') else None,
                    'color': team.get('color'),
                    'venue': venue,
                })

            logger.info(f"Fetched {len(normalized)} NHL teams")
            return normalized

        except Exception as e:
            logger.error(f"Error fetching NHL teams: {e}")
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
