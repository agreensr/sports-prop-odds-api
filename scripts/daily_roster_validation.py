#!/usr/bin/env python3
"""
Daily roster validation script for detecting trades and team changes.

This script compares the database team assignments against the current
nba_api data to detect trades, signings, and roster changes.

Usage:
    python scripts/daily_roster_validation.py [--auto-update] [--alert]

Cron scheduling (daily at 1 AM CST = 7 AM UTC):
    0 7 * * * cd /opt/sports-bet-ai-api && venv/bin/python scripts/daily_roster_validation.py >> /tmp/roster_validation.log 2>&1
"""
import asyncio
import logging
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import SessionLocal
from app.models.nba.models import Player
from app.services.nba.nba_api_service import NbaApiService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/roster_validation.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


class RosterValidator:
    """Validates roster data against nba_api to detect trades and changes."""

    def __init__(self, db, auto_update: bool = False, send_alerts: bool = False):
        """
        Initialize the roster validator.

        Args:
            db: Database session
            auto_update: If True, automatically update detected changes
            send_alerts: If True, send alerts for detected changes
        """
        self.db = db
        self.auto_update = auto_update
        self.send_alerts = send_alerts
        self.nba_service = NbaApiService(db)

    async def validate_all_active_players(
        self,
        hours_threshold: int = 24
    ) -> Dict:
        """
        Validate all active players against nba_api current data.

        Args:
            hours_threshold: Only validate players checked more than this many hours ago

        Returns:
            Dict with validation results
        """
        logger.info("=" * 60)
        logger.info("Daily Roster Validation Started")
        logger.info("=" * 60)

        start_time = datetime.now()

        # Get all active players
        players = self.db.query(Player).filter(Player.active == True).all()

        if not players:
            logger.warning("No active players found")
            return {
                "timestamp": start_time.isoformat(),
                "total_players": 0,
                "validated": 0,
                "discrepancies": [],
                "errors": []
            }

        logger.info(f"Found {len(players)} active players to validate")

        discrepancies = []
        validated = 0
        errors = []

        for player in players:
            try:
                # Check if player was recently validated
                if player.last_roster_check:
                    hours_since_check = (datetime.now() - player.last_roster_check).total_seconds() / 3600
                    if hours_since_check < hours_threshold:
                        validated += 1
                        continue

                # Fetch current team from nba_api
                result = await self._validate_player(player)

                if result.get('discrepancy'):
                    discrepancies.append(result)
                    logger.warning(f"Discrepancy found: {player.name} - {result['message']}")

                validated += 1

                # Progress logging every 50 players
                if validated % 50 == 0:
                    logger.info(f"Validated {validated}/{len(players)} players...")

            except Exception as e:
                error_msg = f"Error validating {player.name}: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        summary = {
            "timestamp": start_time.isoformat(),
            "total_players": len(players),
            "validated": validated,
            "discrepancies_found": len(discrepancies),
            "discrepancies": discrepancies,
            "errors": len(errors),
            "error_details": errors,
            "duration_seconds": duration,
            "status": "discrepancies_found" if discrepancies else "success"
        }

        # Log summary
        logger.info("=" * 60)
        logger.info("Roster Validation Summary")
        logger.info("=" * 60)
        logger.info(f"Total players: {summary['total_players']}")
        logger.info(f"Validated: {summary['validated']}")
        logger.info(f"Discrepancies found: {summary['discrepancies_found']}")
        logger.info(f"Errors: {summary['errors']}")
        logger.info(f"Duration: {duration:.2f} seconds")
        logger.info(f"Status: {summary['status']}")
        logger.info("=" * 60)

        # Handle auto-update if enabled
        if self.auto_update and discrepancies:
            await self._auto_update_discrepancies(discrepancies)

        # Handle alerts if enabled
        if self.send_alerts and discrepancies:
            await self._send_alert(summary)

        return summary

    async def _validate_player(self, player: Player) -> Dict:
        """
        Validate a single player against nba_api data.

        Args:
            player: Player model instance

        Returns:
            Dict with validation result
        """
        try:
            # Import here to avoid circular imports
            from nba_api.stats.endpoints import commonplayerinfo

            # Fetch player info from nba_api
            player_info = commonplayerinfo.CommonPlayerInfo(
                player_id=player.external_id
            )

            df = player_info.get_data_frames()[0] if player_info.get_data_frames() else None

            if df is None or df.empty:
                return {
                    'player_id': player.id,
                    'player_name': player.name,
                    'discrepancy': False,
                    'message': 'No data found in nba_api'
                }

            # Get current team from nba_api
            nba_team = df.iloc[0].get('TEAM_ABBREVIATION')

            if not nba_team:
                return {
                    'player_id': player.id,
                    'player_name': player.name,
                    'discrepancy': False,
                    'message': 'No team data in nba_api'
                }

            # Normalize team abbreviations for comparison
            db_team = player.team.upper() if player.team else None
            nba_team = nba_team.upper()

            # Update last_roster_check timestamp
            player.last_roster_check = datetime.now()
            self.db.commit()

            # Check for discrepancy
            if db_team != nba_team:
                return {
                    'player_id': player.id,
                    'player_name': player.name,
                    'external_id': player.external_id,
                    'old_team': player.team,
                    'new_team': nba_team,
                    'discrepancy': True,
                    'message': f"Team mismatch: DB={player.team}, NBA={nba_team}",
                    'confidence': 'high'  # nba_api is authoritative
                }

            return {
                'player_id': player.id,
                'player_name': player.name,
                'discrepancy': False,
                'message': 'Team matches'
            }

        except Exception as e:
            logger.error(f"Error validating player {player.name}: {e}")
            return {
                'player_id': player.id,
                'player_name': player.name,
                'discrepancy': False,
                'message': f'Validation error: {e}'
            }

    async def _auto_update_discrepancies(self, discrepancies: List[Dict]) -> None:
        """
        Automatically update player teams for high-confidence discrepancies.

        Args:
            discrepancies: List of discrepancy dicts
        """
        updated = 0

        for disc in discrepancies:
            if disc.get('confidence') == 'high' and disc.get('discrepancy'):
                try:
                    player = self.db.query(Player).filter(
                        Player.id == disc['player_id']
                    ).first()

                    if player:
                        old_team = player.team
                        player.team = disc['new_team']
                        player.last_roster_check = datetime.now()
                        player.data_source = 'nba_api_auto'
                        self.db.commit()

                        logger.info(f"Auto-updated {player.name}: {old_team} → {disc['new_team']}")
                        updated += 1

                except Exception as e:
                    logger.error(f"Error auto-updating {disc.get('player_name')}: {e}")

        logger.info(f"Auto-updated {updated} player teams")

    async def _send_alert(self, summary: Dict) -> None:
        """
        Send alert for detected discrepancies.

        Args:
            summary: Validation summary dict
        """
        # In production, this could send email, Slack message, etc.
        alert_msg = f"""
Roster Validation Alert - {summary['timestamp']}

Detected {summary['discrepancies_found']} roster discrepancies:

"""

        for disc in summary['discrepancies']:
            alert_msg += f"\n- {disc['player_name']}: {disc['old_team']} → {disc['new_team']}"

        alert_msg += f"\n\nTotal players validated: {summary['validated']}"
        alert_msg += f"\nDuration: {summary['duration_seconds']:.2f} seconds"

        logger.warning(alert_msg)

        # Write to alert file for monitoring
        with open('/tmp/roster_validation_alerts.log', 'a') as f:
            f.write("\n" + "="*60 + "\n")
            f.write(alert_msg + "\n")

    async def validate_specific_player(
        self,
        external_id: str
    ) -> Optional[Dict]:
        """
        Validate a specific player by external_id.

        Args:
            external_id: Player's nba_api external_id

        Returns:
            Validation result dict or None if not found
        """
        player = self.db.query(Player).filter(
            Player.external_id == external_id
        ).first()

        if not player:
            logger.error(f"Player with external_id {external_id} not found")
            return None

        result = await self._validate_player(player)

        if result.get('discrepancy'):
            logger.warning(f"Discrepancy: {result['message']}")

        return result


async def main():
    """Main entry point for the script."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate roster data against nba_api to detect trades"
    )
    parser.add_argument(
        '--auto-update',
        action='store_true',
        help='Automatically update detected team changes'
    )
    parser.add_argument(
        '--alert',
        action='store_true',
        help='Send alerts for detected discrepancies'
    )
    parser.add_argument(
        '--player-id',
        type=str,
        default=None,
        help='Validate a specific player by external_id'
    )
    parser.add_argument(
        '--hours-threshold',
        type=int,
        default=24,
        help='Only validate players checked more than this many hours ago (default: 24)'
    )

    args = parser.parse_args()

    db = SessionLocal()
    validator = RosterValidator(
        db,
        auto_update=args.auto_update,
        send_alerts=args.alert
    )

    try:
        if args.player_id:
            # Validate specific player
            result = await validator.validate_specific_player(args.player_id)

            if result:
                if result.get('discrepancy'):
                    logger.info("✗ Discrepancy found")
                    sys.exit(1)
                else:
                    logger.info("✓ Validation passed")
                    sys.exit(0)
            else:
                logger.error("Player not found")
                sys.exit(1)
        else:
            # Validate all active players
            summary = await validator.validate_all_active_players(
                hours_threshold=args.hours_threshold
            )

            if summary['status'] == 'success':
                logger.info("✓ All validations passed")
                sys.exit(0)
            else:
                logger.info(f"✗ Found {summary['discrepancies_found']} discrepancies")
                sys.exit(1)

    except Exception as e:
        logger.error(f"Error during roster validation: {e}", exc_info=True)
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
