"""Fix player team assignments from authoritative NBA.com data.

This script:
1. Fetches all active NBA players from NBA.com API
2. Updates player.team with current team assignment
3. Deactivates players not found in NBA.com (G-League, retired, etc.)
4. Logs all changes for audit trail
"""
import asyncio
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from app.core.database import SessionLocal
from app.services.nba.nba_service import NBAService


async def fix_player_team_assignments():
    """Update all player team assignments from NBA.com."""
    db = SessionLocal()

    try:
        # Fetch authoritative player data from NBA.com
        nba_service = NBAService()
        # Use current season (2025-26 since we're in Jan 2026)
        nba_players = await nba_service.get_all_players(season="2025-26")

        print(f"Fetched {len(nba_players)} players from NBA.com")
        print("=" * 80)

        # Build lookup: PERSON_ID -> TEAM_ABBREVIATION
        nba_player_map = {}
        for p in nba_players:
            player_id = p.get('PERSON_ID')
            team = p.get('TEAM_ABBREVIATION', '')
            roster_status = p.get('ROSTERSTATUS', 1)
            name = p.get('DISPLAY_FIRST_LAST', '')

            nba_player_map[player_id] = {
                'team': team,
                'roster_status': roster_status,
                'name': name
            }

        # Get all players from our database
        result = db.execute(text("""
            SELECT id, external_id, name, team, active, sport_id
            FROM players
            WHERE sport_id = 'nba'
        """))

        db_players = result.fetchall()
        print(f"Found {len(db_players)} players in database\n")

        # Track changes
        updates = []
        deactivations = []
        not_found_in_nba = []
        team_changes = []

        for db_player in db_players:
            player_id, external_id, name, current_team, active, sport_id = db_player

            # Find in NBA.com data
            nba_data = nba_player_map.get(external_id)

            if not nba_data:
                not_found_in_nba.append((name, external_id, current_team))
                # Deactivate if not in NBA.com roster (G-League, retired, etc.)
                if active:
                    deactivations.append((player_id, name, current_team))
                continue

            nba_team = nba_data['team']
            nba_status = nba_data['roster_status']
            nba_name = nba_data['name']

            # Check if team changed
            if current_team != nba_team and nba_team:
                team_changes.append({
                    'player_id': player_id,
                    'name': name,
                    'old_team': current_team,
                    'new_team': nba_team,
                    'nba_name': nba_name
                })
                updates.append((player_id, nba_team))

            # Deactivate if not on active roster
            if active and nba_status != 1:
                deactivations.append((player_id, name, current_team))

        # Apply updates
        print(f"TEAM CHANGES: {len(team_changes)}")
        print("-" * 80)
        for change in sorted(team_changes, key=lambda x: x['new_team']):
            print(f"  {change['name']:25} | {change['old_team']:3} -> {change['new_team']:3}")

        print(f"\nDEACTIVATING: {len(deactivations)} (not on active NBA roster)")
        print("-" * 80)
        for player_id, name, team in sorted(deactivations, key=lambda x: x[2]):
            print(f"  {name:25} | {team:3}")

        print(f"\nNOT FOUND IN NBA.COM: {len(not_found_in_nba)}")
        print("-" * 80)
        for name, external_id, team in sorted(not_found_in_nba, key=lambda x: x[2])[:20]:
            print(f"  {name:25} | {team:3} | external_id: {external_id}")
        if len(not_found_in_nba) > 20:
            print(f"  ... and {len(not_found_in_nba) - 20} more")

        # Apply team updates
        if updates:
            print("\n" + "=" * 80)
            for player_id, new_team in updates:
                db.execute(text("""
                    UPDATE players
                    SET team = :new_team,
                        updated_at = NOW()
                    WHERE id = :player_id
                """), {"player_id": player_id, "new_team": new_team})

        # Deactivate players not on NBA rosters
        if deactivations:
            for player_id, name, team in deactivations:
                db.execute(text("""
                    UPDATE players
                    SET active = false,
                        updated_at = NOW()
                    WHERE id = :player_id
                """), {"player_id": player_id})

        db.commit()

        print("\n" + "=" * 80)
        print("✅ Player team assignments updated successfully!")
        print(f"   - Team changes: {len(team_changes)}")
        print(f"   - Deactivated: {len(deactivations)}")
        print(f"   - Not found: {len(not_found_in_nba)}")

        # Show final state for each team
        print("\n" + "=" * 80)
        print("FINAL TEAM ROSTERS:")
        print("=" * 80)

        result = db.execute(text("""
            SELECT team, COUNT(*) as player_count
            FROM players
            WHERE sport_id = 'nba' AND active = true
            GROUP BY team
            ORDER BY team
        """))

        for row in result:
            team, count = row
            print(f"  {team:3} | {count:2} players")

    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(fix_player_team_assignments())
