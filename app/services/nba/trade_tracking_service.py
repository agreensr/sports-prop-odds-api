"""
NBA Trade Tracking Service

Scrapes NBA.com, ESPN, and other sources for trade data and updates player teams.
Runs during trade season (Feb-Mar) and can be triggered manually.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)


class TradeTracker:
    """Tracks and applies NBA trades to keep database current."""

    # NBA.com team abbreviations to full names mapping
    TEAM_ABBR_TO_FULL = {
        'ATL': 'Atlanta Hawks', 'BOS': 'Boston Celtics', 'BKN': 'Brooklyn Nets',
        'CHA': 'Charlotte Hornets', 'CHI': 'Chicago Bulls', 'CLE': 'Cleveland Cavaliers',
        'DAL': 'Dallas Mavericks', 'DEN': 'Denver Nuggets', 'DET': 'Detroit Pistons',
        'GSW': 'Golden State Warriors', 'HOU': 'Houston Rockets', 'IND': 'Indiana Pacers',
        'LAC': 'Los Angeles Clippers', 'LAL': 'Los Angeles Lakers', 'MEM': 'Memphis Grizzlies',
        'MIA': 'Miami Heat', 'MIL': 'Milwaukee Bucks', 'MIN': 'Minnesota Timberwolves',
        'NOP': 'New Orleans Pelicans', 'NYK': 'New York Knicks', 'OKC': 'Oklahoma City Thunder',
        'ORL': 'Orlando Magic', 'PHI': 'Philadelphia 76ers', 'PHX': 'Phoenix Suns',
        'POR': 'Portland Trail Blazers', 'SAC': 'Sacramento Kings', 'SAS': 'San Antonio Spurs',
        'TOR': 'Toronto Raptors', 'UTA': 'Utah Jazz', 'WAS': 'Washington Wizards'
    }

    def __init__(self, db_session_factory=None):
        self.pending_trades: List[Dict] = []
        self._get_db = db_session_factory

    def _get_db_session(self) -> Session:
        """Get a database session."""
        if self._get_db:
            return self._get_db().__next__()
        from app.core.database import SessionLocal
        return SessionLocal()

    def find_player_by_name(self, db: Session, name: str) -> Optional:
        """Find player by name, trying various matching strategies."""
        from app.models import Player

        # Exact match
        player = db.query(Player).filter(Player.name == name).first()
        if player:
            return player

        # Case-insensitive match
        player = db.query(Player).filter(Player.name.ilike(name)).first()
        if player:
            return player

        # Partial match (for names with suffixes like "Jr.")
        player = db.query(Player).filter(
            Player.name.ilike(f'%{name}%')
        ).first()
        if player:
            return player

        return None

    def apply_trade(self, db: Session, player_name: str, new_team: str,
                    old_team: Optional[str] = None) -> bool:
        """
        Apply a trade to the database.

        Args:
            player_name: Name of the player being traded
            new_team: New team abbreviation (e.g., 'CLE', 'LAC')
            old_team: Expected old team (for validation)

        Returns:
            True if trade was applied, False otherwise
        """
        player = self.find_player_by_name(db, player_name)

        if not player:
            logger.warning(f"Player not found: {player_name}")
            return False

        # Validate old team if provided
        if old_team and player.team != old_team:
            logger.warning(
                f"{player_name} expected to be on {old_team}, "
                f"but found on {player.team}. Skipping validation."
            )

        # Update team
        old_team_name = player.team
        player.team = new_team
        db.commit()

        logger.info(f"Trade Applied: {player_name} {old_team_name} -> {new_team}")
        return True

    def apply_manual_trades(self, trades: List[Dict]) -> Dict[str, int]:
        """
        Apply a list of trades manually provided.

        Args:
            trades: List of {'player': str, 'to_team': str, 'from_team': str (optional)}

        Returns:
            Dictionary with counts: {'applied': int, 'failed': int, 'not_found': int}
        """
        db = self._get_db_session()
        results = {'applied': 0, 'failed': 0, 'not_found': 0}

        try:
            for trade in trades:
                player_name = trade.get('player')
                to_team = trade.get('to_team')
                from_team = trade.get('from_team')

                if not player_name or not to_team:
                    logger.warning(f"Invalid trade entry: {trade}")
                    results['failed'] += 1
                    continue

                if self.apply_trade(db, player_name, to_team, from_team):
                    results['applied'] += 1
                else:
                    results['not_found'] += 1
        finally:
            db.close()

        return results

    def detect_trade_season(self) -> bool:
        """Check if we're in NBA trade season (Jan 15 - Feb 28)."""
        now = datetime.now()
        start = datetime(now.year, 1, 15)
        end = datetime(now.year, 2, 28)
        return start <= now <= end

    def get_all_players_by_team(self, db: Session) -> Dict[str, List]:
        """Get all players grouped by team."""
        from app.models import Player
        teams = {}
        players = db.query(Player).filter(Player.team.isnot(None)).all()

        for player in players:
            if player.team not in teams:
                teams[player.team] = []
            teams[player.team].append(player)

        return teams


# Singleton instance
trade_tracker = TradeTracker()


def sync_trades_from_api(trades: List[Dict]) -> Dict[str, int]:
    """
    Sync trades from an external API or data source.

    Example input:
    [
        {'player': 'James Harden', 'to_team': 'CLE', 'from_team': 'LAC'},
        {'player': 'Darius Garland', 'to_team': 'LAC', 'from_team': 'CLE'},
    ]
    """
    return trade_tracker.apply_manual_trades(trades)


def check_and_update_trades() -> Dict:
    """
    Main function to check for and apply trades.
    Can be called by cron job or scheduled task.
    """
    db = trade_tracker._get_db_session()

    result = {
        'timestamp': datetime.utcnow().isoformat(),
        'trade_season': trade_tracker.detect_trade_season(),
        'trades_found': 0,
        'trades_applied': 0,
        'errors': []
    }

    try:
        # Placeholder for web scraping integration
        trades = []
        result['trades_found'] = len(trades)

        for trade in trades:
            if trade_tracker.apply_trade(
                db,
                trade['player'],
                trade['to_team'],
                trade.get('from_team')
            ):
                result['trades_applied'] += 1

    except Exception as e:
        result['errors'].append(str(e))
        logger.error(f"Error checking trades: {e}")
    finally:
        db.close()

    return result
