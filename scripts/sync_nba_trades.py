#!/usr/bin/env python3
"""
Sync NBA Trades Script

Fetches recent NBA trades from web sources and updates the database.
Can be run manually or via cron during trade season.

Usage:
    python scripts/sync_nba_trades.py [--dry-run] [--source manual]

Sources:
    - manual: Use hardcoded trade list (default, most reliable)
    - nba: NBA.com official trade tracker (not yet implemented)
"""
import argparse
import logging
import os
import sys
from datetime import datetime
from typing import Dict, List

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.models import Player

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_recent_manual_trades() -> List[Dict]:
    """
    Return manually verified recent trades.
    Update this list when new trades are announced.

    Last updated: Feb 3, 2026
    """
    trades = [
        # 2026 NBA Trade Deadline Deals
        {'player': 'James Harden', 'to_team': 'CLE', 'from_team': 'LAC'},
        {'player': 'Darius Garland', 'to_team': 'LAC', 'from_team': 'CLE'},
        {'player': 'Nikola Vucevic', 'to_team': 'BOS', 'from_team': 'CHI'},
        {'player': 'Mike Conley', 'to_team': 'CHI', 'from_team': 'MIN'},
        {'player': 'Jaden Ivey', 'to_team': 'CHI', 'from_team': 'DET'},
        {'player': 'Jaren Jackson Jr.', 'to_team': 'UTA', 'from_team': 'MEM'},
    ]
    return trades


def find_player_by_name(db, name: str):
    """Find player by name with fuzzy matching."""
    # Exact match
    player = db.query(Player).filter(Player.name == name).first()
    if player:
        return player

    # Case-insensitive
    player = db.query(Player).filter(Player.name.ilike(name)).first()
    if player:
        return player

    # Partial match
    player = db.query(Player).filter(Player.name.ilike(f'%{name}%')).first()
    return player


def apply_trade(db, player_name: str, new_team: str, old_team: str = None) -> bool:
    """Apply a single trade to the database."""
    player = find_player_by_name(db, player_name)

    if not player:
        logger.warning(f"Player not found: {player_name}")
        return False

    old_team_name = player.team
    player.team = new_team

    logger.info(f"  {player_name}: {old_team_name} -> {new_team}")
    return True


def sync_trades(dry_run: bool = False, source: str = 'manual') -> Dict:
    """Main sync function."""
    result = {
        'timestamp': datetime.utcnow().isoformat(),
        'source': source,
        'dry_run': dry_run,
        'trades_found': 0,
        'trades_applied': 0,
        'not_found': 0
    }

    all_trades = []

    if source == 'manual':
        all_trades = get_recent_manual_trades()

    result['trades_found'] = len(all_trades)

    if not all_trades:
        logger.info("No trades found to sync")
        return result

    logger.info(f"Found {len(all_trades)} trades:")

    if not dry_run:
        db = SessionLocal()
        try:
            for trade in all_trades:
                if apply_trade(db, trade['player'], trade['to_team'], trade.get('from_team')):
                    result['trades_applied'] += 1
                else:
                    result['not_found'] += 1
            db.commit()
        finally:
            db.close()
        logger.info(f"Applied {result['trades_applied']} trades")
    else:
        for trade in all_trades:
            logger.info(f"  [DRY RUN] {trade['player']}: {trade.get('from_team', '?')} -> {trade['to_team']}")
        logger.info("DRY RUN - No trades applied")

    return result


def main():
    parser = argparse.ArgumentParser(description='Sync NBA trades to database')
    parser.add_argument('--dry-run', action='store_true', help='Show trades without applying')
    parser.add_argument('--source', choices=['manual', 'nba'], default='manual',
                        help='Data source (default: manual)')

    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("NBA Trade Sync")
    logger.info(f"Source: {args.source} | Dry Run: {args.dry_run}")
    logger.info("=" * 60)

    result = sync_trades(dry_run=args.dry_run, source=args.source)

    logger.info(f"Found: {result['trades_found']} | Applied: {result['trades_applied']} | Not Found: {result.get('not_found', 0)}")
    logger.info("=" * 60)

    return 0


if __name__ == '__main__':
    sys.exit(main())
